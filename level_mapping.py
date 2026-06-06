import polars as pl


def reallocate_fast(
    lf_amounts, lf_centers, *,
    # --- truth (lf_centers) ---
    truth_entity="Entity Code", truth_code="Mapped Centre", status_col="Active",
    active_value=True, levels=("level1","level4","level5","level6","level7"),
    # --- amounts (lf_amounts) ---
    amt_entity="Local Entity Code", amt_code="AGG Center Code", amt_col="amount",
    amt_levels=None,                 # level col names in lf_amounts; defaults to `levels`
    unmatched="inactive",            # "inactive": fold orphans in as inactive | "drop"
):
    ANCESTRY = list(levels)
    FALLBACK = list(reversed(ANCESTRY[1:]))
    amt_levels = list(levels if amt_levels is None else amt_levels)

    # ---- truth: dedupe to one row per (entity, code); active if ANY row active ----
    truth = (lf_centers.rename({truth_entity:"entity", truth_code:"code", status_col:"status"})
             .select(["entity","code","status"] + ANCESTRY)
             .group_by("entity","code")
             .agg((pl.col("status") == active_value).any().alias("is_active"),
                  *[pl.col(c).first().alias(c) for c in ANCESTRY]))

    # ---- amounts: aggregate per (entity, code); carry the hierarchy ----
    ren = {amt_entity:"entity", amt_code:"code", amt_col:"amount"}
    ren.update({a: l for a, l in zip(amt_levels, ANCESTRY) if a != l})
    amt = (lf_amounts.rename(ren)
           .group_by("entity","code")
           .agg(pl.col("amount").sum(), *[pl.col(l).first().alias(l) for l in ANCESTRY]))

    # ---- universe ----
    # truth-matched centers: levels + status from truth, amount from amounts
    truth_part = (truth.join(amt.select("entity","code","amount"), on=["entity","code"], how="left")
                  .with_columns(pl.col("amount").fill_null(0.0))
                  .select(["entity","code","is_active"] + ANCESTRY + ["amount"]))
    # orphan centers (in amounts, not in truth): INACTIVE, levels inherited from amounts
    orphan_part = (amt.join(truth.select("entity","code"), on=["entity","code"], how="anti")
                   .with_columns(pl.lit(False).alias("is_active"))
                   .select(["entity","code","is_active"] + ANCESTRY + ["amount"]))

    universe = truth_part if unmatched == "drop" else pl.concat([truth_part, orphan_part])

    active = universe.filter(pl.col("is_active"))
    inactive = universe.filter(~pl.col("is_active") & (pl.col("amount") != 0))

    # ---- resolve each inactive's fallback level ----
    inact = inactive
    for g in FALLBACK:
        keys = ["entity"] + ANCESTRY[:ANCESTRY.index(g)+1]
        gt = active.group_by(keys).agg(pl.col("amount").sum().alias(f"gtot_{g}"),
                                       pl.len().alias(f"gcnt_{g}"))
        inact = inact.join(gt, on=keys, how="left")
    inact = inact.with_columns(
        pl.coalesce([pl.when(pl.col(f"gcnt_{g}") > 0).then(pl.lit(g)) for g in FALLBACK]).alias("resolved_level")
    )

    # ---- distribute inactive totals to active centers per group (no fan-out) ----
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
                  .select(["entity","code"]+ANCESTRY+["is_active","amount","amount_active"]))
    inactive_out = (inact.with_columns(
                        pl.when(pl.col("resolved_level").is_not_null()).then(pl.lit(0.0))
                          .otherwise(pl.col("amount")).alias("amount_active"))
                    .select(["entity","code"]+ANCESTRY+["is_active","amount","amount_active"]))
    zero_inactive = (universe.filter(~pl.col("is_active") & (pl.col("amount") == 0))
                     .with_columns(pl.col("amount").alias("amount_active"))
                     .select(["entity","code"]+ANCESTRY+["is_active","amount","amount_active"]))

    result = (pl.concat([active_out, inactive_out, zero_inactive])
              .rename({"entity":truth_entity, "code":truth_code, "is_active":status_col}))
    audit = pl.concat(audit_parts).rename({"entity":truth_entity, "code":truth_code})
    return result, audit
