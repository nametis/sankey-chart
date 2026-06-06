import polars as pl


def reallocate_fast(
    lf_amounts, lf_centers, *,
    truth_entity="Entity Code", truth_code="Mapped Centre", status_col="Active",
    active_value=True, levels=("level1","level4","level5","level6","level7"),
    amt_entity="Local Entity Code", amt_code="AGG Center Code", amt_col="amount",
    keep_unmatched=True,          # carry amounts whose code isn't in truth -> conserves entity totals
):
    ANCESTRY = list(levels)
    FALLBACK = list(reversed(ANCESTRY[1:]))

    truth = lf_centers.rename(
        {truth_entity:"entity", truth_code:"code", status_col:"status"}
    ).select(["entity","code","status"] + ANCESTRY)

    # GUARD 1: one row per (entity, code) so amounts can't be double-counted.
    # If ANY row for that (entity, code) is active, the collapsed row is active.
    truth = truth.group_by("entity", "code").agg(
        pl.when((pl.col("status") == active_value).any())
          .then(pl.lit(active_value))
          .otherwise(pl.col("status").first())
          .alias("status"),
        *[pl.col(c).first().alias(c) for c in ANCESTRY],
    )

    # GUARD 2: collapse duplicate amount rows per (entity, code).
    amt = lf_amounts.rename(
        {amt_entity:"entity", amt_code:"code", amt_col:"amount"}
    ).group_by("entity","code").agg(pl.col("amount").sum())

    universe = (truth.join(amt, on=["entity","code"], how="left")
                .with_columns(pl.col("amount").fill_null(0.0), pl.col("status").fill_null(False)))
    active = universe.filter(pl.col("status") == active_value)
    inactive = universe.filter((pl.col("status") != active_value) & (pl.col("amount") != 0))

    inact = inactive
    for g in FALLBACK:
        keys = ["entity"] + ANCESTRY[:ANCESTRY.index(g)+1]
        gt = active.group_by(keys).agg(pl.col("amount").sum().alias(f"gtot_{g}"),
                                       pl.len().alias(f"gcnt_{g}"))
        inact = inact.join(gt, on=keys, how="left")
    inact = inact.with_columns(
        pl.coalesce([pl.when(pl.col(f"gcnt_{g}") > 0).then(pl.lit(g)) for g in FALLBACK]).alias("resolved_level")
    )

    recv_parts, audit_parts = [], []
    for g in FALLBACK:
        keys = ["entity"] + ANCESTRY[:ANCESTRY.index(g)+1]
        grp = (inact.filter(pl.col("resolved_level") == g).group_by(keys)
               .agg(pl.col("amount").sum().alias("inact_tot"),
                    pl.col(f"gtot_{g}").first().alias("gtot"),
                    pl.col(f"gcnt_{g}").first().alias("gcnt")))
        dist = (active.select(keys + ["code","amount"]).join(grp, on=keys, how="inner")
                .with_columns(pl.when(pl.col("gtot") > 0)
                              .then(pl.col("amount")*pl.col("inact_tot")/pl.col("gtot"))
                              .otherwise(pl.col("inact_tot")/pl.col("gcnt")).alias("received")))
        recv_parts.append(dist.select("entity","code","received"))
        audit_parts.append(dist.select("entity","code","received", pl.lit(g).alias("resolved_level")))

    recv = pl.concat(recv_parts).group_by("entity","code").agg(pl.col("received").sum().alias("received"))

    active_out = (active.join(recv, on=["entity","code"], how="left")
                  .with_columns((pl.col("amount")+pl.col("received").fill_null(0)).alias("amount_active"))
                  .select(["entity","code"]+ANCESTRY+["status","amount","amount_active"]))
    inactive_out = (inact.with_columns(
                        pl.when(pl.col("resolved_level").is_not_null()).then(pl.lit(0.0))
                          .otherwise(pl.col("amount")).alias("amount_active"))
                    .select(["entity","code"]+ANCESTRY+["status","amount","amount_active"]))
    zero_inactive = (universe.filter((pl.col("status") != active_value) & (pl.col("amount") == 0))
                     .with_columns(pl.col("amount").alias("amount_active"))
                     .select(["entity","code"]+ANCESTRY+["status","amount","amount_active"]))

    pieces = [active_out, inactive_out, zero_inactive]

    if keep_unmatched:
        # amounts whose (entity, code) is absent from truth -> pass through unchanged.
        unmatched = (amt.join(truth.select("entity","code"), on=["entity","code"], how="anti")
                     .with_columns([pl.lit(None, dtype=pl.Utf8).alias(c) for c in ANCESTRY]
                                   + [pl.lit(None).alias("status"),
                                      pl.col("amount").alias("amount_active")])
                     .select(["entity","code"]+ANCESTRY+["status","amount","amount_active"]))
        pieces.append(unmatched)

    result = (pl.concat(pieces)
              .rename({"entity":truth_entity, "code":truth_code, "status":status_col}))
    audit = pl.concat(audit_parts).rename({"entity":truth_entity, "code":truth_code})
    return result, audit
