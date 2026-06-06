import polars as pl

# Ancestry, broad -> granular (note: no level2/level3 in this schema).
ANCESTRY = ["level1", "level4", "level5", "level6", "level7"]
# Fallback granularities, most granular first; never coarser than level4.
FALLBACK = ["level7", "level6", "level5", "level4"]


def reallocate(lf_amounts, lf_truth, *, active_value="active"):
    """
    lf_truth   : SOURCE OF TRUTH -> entity, code, level1, level4..7, status  (full code universe)
    lf_amounts : entity, code, level1, level4..7, amount   (amount_active is recomputed, not read)

    Each inactive code's amount is split across the active codes sharing its most granular
    available path (level7 -> level6 -> level5 -> level4), proportional to each active code's
    amount (even split when the group's active codes have no base amount). Returns (result, audit).
    """
    amt = lf_amounts.select("entity", "code", "amount")

    universe = (
        lf_truth.select(["entity", "code", "status"] + ANCESTRY)
        .join(amt, on=["entity", "code"], how="left")
        .with_columns(pl.col("amount").fill_null(0), pl.col("status").fill_null("inactive"))
    )

    active = universe.filter(pl.col("status") == active_value)
    inactive = universe.filter((pl.col("status") != active_value) & (pl.col("amount") != 0))

    # Per-group active totals at each granularity, to resolve which level each inactive falls back to.
    inact = inactive
    for g in FALLBACK:
        keys = ["entity"] + ANCESTRY[: ANCESTRY.index(g) + 1]
        gt = active.group_by(keys).agg(
            pl.col("amount").sum().alias(f"gtot_{g}"),
            pl.len().alias(f"gcnt_{g}"),
        )
        inact = inact.join(gt, on=keys, how="left")

    inact = inact.with_columns(
        pl.coalesce([
            pl.when(pl.col(f"gcnt_{g}") > 0).then(pl.lit(g)) for g in FALLBACK
        ]).alias("resolved_level")
    )

    # For each resolved granularity, fan each inactive amount out to the active codes in its group.
    parts = []
    for g in FALLBACK:
        keys = ["entity"] + ANCESTRY[: ANCESTRY.index(g) + 1]
        sub = (
            inact.filter(pl.col("resolved_level") == g)
            .select(keys + ["code", "amount", f"gtot_{g}", f"gcnt_{g}"])
            .rename({"code": "inactive_code", "amount": "inactive_amount",
                     f"gtot_{g}": "gtot", f"gcnt_{g}": "gcnt"})
        )
        act_g = active.select(keys + ["code", "amount"]).rename(
            {"code": "code", "amount": "active_amount"}
        )
        joined = sub.join(act_g, on=keys, how="inner").with_columns(
            pl.when(pl.col("gtot") > 0)
              .then(pl.col("inactive_amount") * pl.col("active_amount") / pl.col("gtot"))
              .otherwise(pl.col("inactive_amount") / pl.col("gcnt"))
              .alias("received")
        )
        parts.append(joined.select(
            "entity", "code", "received",
            pl.col("inactive_code"), pl.lit(g).alias("resolved_level"),
        ))

    flows = pl.concat(parts) if parts else None

    received = (
        flows.group_by("entity", "code").agg(pl.col("received").sum().alias("received"))
        if flows is not None else
        active.select("entity", "code").head(0).with_columns(pl.lit(0.0).alias("received"))
    )

    # Active codes: original amount + everything redirected to them.
    active_out = (
        active.join(received, on=["entity", "code"], how="left")
        .with_columns((pl.col("amount") + pl.col("received").fill_null(0)).alias("amount_active"))
        .select(["entity", "code"] + ANCESTRY + ["status", "amount", "amount_active"])
    )

    # Inactive codes: 0 if reallocated, else keep amount (no backup down to level4).
    inactive_out = (
        inact.with_columns(
            pl.when(pl.col("resolved_level").is_not_null()).then(pl.lit(0.0))
              .otherwise(pl.col("amount")).alias("amount_active")
        )
        .select(["entity", "code"] + ANCESTRY + ["status", "amount", "amount_active"])
    )

    # Inactive codes with 0 amount (in truth but not amounts input) -> carry through untouched.
    zero_inactive = (
        universe.filter((pl.col("status") != active_value) & (pl.col("amount") == 0))
        .with_columns(pl.col("amount").alias("amount_active"))
        .select(["entity", "code"] + ANCESTRY + ["status", "amount", "amount_active"])
    )

    result = pl.concat([active_out, inactive_out, zero_inactive])
    audit = flows.sort(["entity", "inactive_code"]) if flows is not None else None
    return result, audit
