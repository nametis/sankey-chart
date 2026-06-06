import polars as pl


def reallocate_fast(
    lf_amounts, lf_centers, *,
    truth_entity="Entity Code", truth_code="Mapped Centre", status_col="Active",
    active_value=True, levels=("level1", "level4", "level5", "level6", "level7"),
    amt_entity="Local Entity Code", amt_code="AGG Center Code", amt_col="amount",
    amt_levels=None, unmatched="inactive",          # "inactive" | "drop"
):
    ANCESTRY = list(levels)
    FALLBACK = list(reversed(ANCESTRY[1:]))          # level7 → level4
    amt_levels = list(levels if amt_levels is None else amt_levels)
    path = lambda g: ["entity"] + ANCESTRY[: ANCESTRY.index(g) + 1]

    # ── truth: one row per (entity, code); active if ANY row active ──────────
    truth = (
        lf_centers.rename({truth_entity: "entity", truth_code: "code", status_col: "status"})
        .group_by("entity", "code")
        .agg((pl.col("status") == active_value).any().alias("is_active"),
             *[pl.col(c).first().alias(c) for c in ANCESTRY])
        .collect()
    )

    # ── amounts: aggregate per (entity, code); carry hierarchy where present ─
    have    = set(lf_amounts.collect_schema().names())
    present = [(a, l) for a, l in zip(amt_levels, ANCESTRY) if a in have]
    missing = [l for a, l in zip(amt_levels, ANCESTRY) if a not in have]
    amt = (
        lf_amounts.rename({amt_entity: "entity", amt_code: "code", amt_col: "amount",
                           **{a: l for a, l in present if a != l}})
        .group_by("entity", "code")
        .agg(pl.col("amount").sum(), *[pl.col(l).first() for _, l in present])
        .collect()
    )

    # ── universe: every amt row kept (orphans → inactive, amt levels); truth
    #    match → truth levels + truth status; truth-only codes → amount 0.
    #    full join = inactive mode, right join = drop mode (orphans excluded).
    t = {"is_active": "t_is_active", **{l: f"t_{l}" for l in ANCESTRY}}
    universe = (
        amt.join(truth.rename(t), on=["entity", "code"], coalesce=True,
                 how="full" if unmatched == "inactive" else "right")
        .with_columns(
            pl.coalesce(pl.col("t_is_active"), pl.lit(False)).alias("is_active"),
            pl.col("amount").fill_null(0.0),
            *[(pl.coalesce(pl.col(f"t_{l}"), pl.col(l)) if l not in missing
               else pl.col(f"t_{l}")).alias(l) for l in ANCESTRY],
        )
        .select(["entity", "code", "is_active"] + ANCESTRY + ["amount"])
    )

    active   = universe.filter(pl.col("is_active"))
    inactive = universe.filter(~pl.col("is_active") & (pl.col("amount") != 0))

    # active group totals per granularity — computed once, reused twice
    stats = {g: active.group_by(path(g)).agg(pl.col("amount").sum().alias("gtot"),
                                             pl.len().alias("gcnt")) for g in FALLBACK}

    # ── resolve each inactive center to its finest level with active present ─
    inact = inactive
    for g in FALLBACK:
        inact = inact.join(stats[g].select(path(g) + [pl.col("gcnt").alias(f"h_{g}")]),
                           on=path(g), how="left")
    inact = inact.with_columns(
        pl.coalesce([pl.when(pl.col(f"h_{g}") > 0).then(pl.lit(g)) for g in FALLBACK]).alias("level")
    )

    # ── distribute each group's inactive total across its active centers ─────
    flows = []
    for g in FALLBACK:
        tot = (inact.filter(pl.col("level") == g).group_by(path(g))
               .agg(pl.col("amount").sum().alias("inact_tot")))
        flows.append(
            active.select(path(g) + ["code", "amount"])
            .join(stats[g], on=path(g)).join(tot, on=path(g))   # inner: only groups w/ inactive
            .select("entity", "code",
                    pl.when(pl.col("gtot") > 0)
                      .then(pl.col("amount") * pl.col("inact_tot") / pl.col("gtot"))
                      .otherwise(pl.col("inact_tot") / pl.col("gcnt")).alias("received"),
                    pl.lit(g).alias("resolved_level"))
        )
    audit = pl.concat(flows).rename({"entity": truth_entity, "code": truth_code})
    recv  = (pl.concat(f.select("entity", "code", "received") for f in flows)
             .group_by("entity", "code").agg(pl.col("received").sum()))

    # ── single output expression: active(+received) / reallocated(0) / kept ──
    result = (
        universe
        .join(recv, on=["entity", "code"], how="left")
        .join(inact.select("entity", "code", "level"), on=["entity", "code"], how="left")
        .with_columns(
            pl.when(pl.col("is_active"))
              .then(pl.col("amount") + pl.col("received").fill_null(0.0))
              .when(pl.col("level").is_not_null()).then(0.0)
              .otherwise(pl.col("amount")).alias("amount_active")
        )
        .select(["entity", "code"] + ANCESTRY + ["is_active", "amount", "amount_active"])
        .rename({"entity": truth_entity, "code": truth_code, "is_active": status_col})
    )
    return result.lazy(), audit.lazy()
