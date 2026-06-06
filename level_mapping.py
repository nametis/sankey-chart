import polars as pl


def reallocate(
    lf_amounts,
    lf_centers,                       # source of truth
    *,
    # --- lf_centers (truth) column names ---
    truth_entity="Entity Code",
    truth_code="Mapped Centre",
    status_col="Active",
    active_value=True,                # value in `Active` that means active (True, "active", "Y", ...)
    levels=("level1", "level4", "level5", "level6", "level7"),  # broad -> granular
    # --- lf_amounts column names ---
    amt_entity="Local Entity Code",
    amt_code="AGG Center Code",
    amt_col="amount",
):
    """
    Split each inactive code's amount across the active codes sharing its most granular
    available path (level7 -> ... -> level4), proportional to each active's amount
    (even split when the group's active codes have no base amount).

    lf_centers : truth -> [truth_entity, truth_code, status_col, *levels]
    lf_amounts : amounts -> [amt_entity, amt_code, amt_col]
    Returns (result, audit).
    """
    ANCESTRY = list(levels)                       # full path, broad -> granular
    FALLBACK = list(reversed(ANCESTRY[1:]))       # granularities, granular -> coarse (stops at levels[1])

    # Normalize both frames to canonical entity / code / status / amount.
    truth = lf_centers.rename(
        {truth_entity: "entity", truth_code: "code", status_col: "status"}
    ).select(["entity", "code", "status"] + ANCESTRY)

    amt = lf_amounts.rename(
        {amt_entity: "entity", amt_code: "code", amt_col: "amount"}
    ).select("entity", "code", "amount")

    universe = (
        truth.join(amt, on=["entity", "code"], how="left")
        .with_columns(pl.col("amount").fill_null(0.0), pl.col("status").fill_null(False))
    )

    active = universe.filter(pl.col("status") == active_value)
    inactive = universe.filter((pl.col("status") != active_value) & (pl.col("amount") != 0))

    # Per-group active totals at each granularity, to resolve each inactive's fallback level.
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

    # Fan each inactive amount out to the active codes in its resolved group.
    parts = []
    for g in FALLBACK:
        keys = ["entity"] + ANCESTRY[: ANCESTRY.index(g) + 1]
        sub = (
            inact.filter(pl.col("resolved_level") == g)
            .select(keys + ["code", "amount", f"gtot_{g}", f"gcnt_{g}"])
            .rename({"code": "inactive_code", "amount": "inactive_amount",
                     f"gtot_{g}": "gtot", f"gcnt_{g}": "gcnt"})
        )
        act_g = active.select(keys + ["code", "amount"]).rename({"amount": "active_amount"})
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

    active_out = (
        active.join(received, on=["entity", "code"], how="left")
        .with_columns((pl.col("amount") + pl.col("received").fill_null(0)).alias("amount_active"))
        .select(["entity", "code"] + ANCESTRY + ["status", "amount", "amount_active"])
    )
    inactive_out = (
        inact.with_columns(
            pl.when(pl.col("resolved_level").is_not_null()).then(pl.lit(0.0))
              .otherwise(pl.col("amount")).alias("amount_active")
        )
        .select(["entity", "code"] + ANCESTRY + ["status", "amount", "amount_active"])
    )
    zero_inactive = (
        universe.filter((pl.col("status") != active_value) & (pl.col("amount") == 0))
        .with_columns(pl.col("amount").alias("amount_active"))
        .select(["entity", "code"] + ANCESTRY + ["status", "amount", "amount_active"])
    )

    result = (
        pl.concat([active_out, inactive_out, zero_inactive])
        .rename({"entity": truth_entity, "code": truth_code, "status": status_col})
    )
    audit = (
        flows.rename({"entity": truth_entity, "code": truth_code}).sort([truth_entity, "inactive_code"])
        if flows is not None else None
    )
    return result, audit
