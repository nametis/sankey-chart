import polars as pl


def _prepare_universe(
    lf_amounts, lf_centers, *,
    truth_entity, truth_code, status_col, active_value, ANCESTRY,
    amt_entity, project_col, amt_code, amt_col, amt_levels, truth_levels, unmatched,
):
    """Raw inputs -> one resolved row per (entity, project, code) in INTERNAL names:
       entity, project, code, is_active, *ANCESTRY, amount.

       Sources:
         * lf_amounts - amounts AND the full level path (assumed already propagated).
         * lf_centers - status (is_active per (entity, code)) and, if it carries the level
           columns, a SECONDARY level source. The level path per code is taken from amounts
           first, then centers. This lets an active center that holds no amount anywhere
           still get its hierarchy (from centers) and therefore still receive cascaded amount."""
    KEY = ["entity", "project", "code"]

    # collect centers ONCE; reuse for status and (optionally) levels
    centers_raw = lf_centers.rename(
        {truth_entity: "entity", truth_code: "code", status_col: "status"}
    ).collect()
    centers = (centers_raw.group_by("entity", "code")
               .agg((pl.col("status") == active_value).any().alias("is_active")))

    have           = set(lf_amounts.collect_schema().names())
    present        = [(a, l) for a, l in zip(amt_levels, ANCESTRY) if a in have]
    present_levels = [l for _, l in present]
    amt = (
        lf_amounts.rename({amt_entity: "entity", project_col: "project",
                           amt_code: "code", amt_col: "amount",
                           **{a: l for a, l in present if a != l}})
        .group_by("entity", "project", "code")
        .agg(pl.col("amount").sum(), *[pl.col(l).first() for l in present_levels])
        .collect()
    )

    # which level columns does centers carry? (its level names -> internal ANCESTRY names)
    cen_cols   = set(centers_raw.columns)
    cen_pairs  = [(t, l) for t, l in zip(truth_levels, ANCESTRY) if t in cen_cols]
    cen_levels = {l for _, l in cen_pairs}

    # one level path per code: amounts preferred, centers as fallback. Covers every code
    # in either input, so amount-less active centers still get a hierarchy.
    codes = pl.concat([amt.select("code"), centers.select("code")]).unique()
    code_levels = codes.join(
        amt.group_by("code").agg(*[pl.col(l).drop_nulls().first().alias(f"a_{l}") for l in present_levels]),
        on="code", how="left")
    if cen_pairs:
        code_levels = code_levels.join(
            centers_raw.group_by("code").agg(
                *[pl.col(t).drop_nulls().first().alias(f"c_{l}") for t, l in cen_pairs]),
            on="code", how="left")
    code_levels = code_levels.with_columns(*[
        (pl.coalesce([pl.col(f"a_{l}")] * (l in present_levels)
                     + [pl.col(f"c_{l}")] * (l in cen_levels))
         if (l in present_levels or l in cen_levels) else pl.lit(None)).alias(l)
        for l in ANCESTRY
    ]).select(["code"] + ANCESTRY)

    # amount rows with status (orphan -> inactive)
    amt_rows = (
        amt.join(centers, on=["entity", "code"],
                 how="left" if unmatched == "inactive" else "inner")
        .with_columns(pl.col("is_active").fill_null(False))
        .select(KEY + ["is_active", "amount"])
    )
    # active centers expanded into every project of their entity (amount 0) -> recipients
    ent_proj = amt.select("entity", "project").unique()
    active_expanded = (
        centers.filter(pl.col("is_active"))
        .join(ent_proj, on="entity", how="inner")
        .join(amt.select(KEY), on=KEY, how="anti")
        .with_columns(pl.lit(0.0).alias("amount"))
        .select(KEY + ["is_active", "amount"])
    )
    # one join attaches the full level path to every row (amount rows and expanded recipients)
    universe = (
        pl.concat([amt_rows, active_expanded])
        .join(code_levels, on="code", how="left")
        .select(KEY + ["is_active"] + ANCESTRY + ["amount"])
    )
    return universe


def _cascade(universe, *, ANCESTRY, FALLBACK, keep_empty):
    """Resolved universe (internal names) -> (result, audit), scoped per (entity, project),
       distributing inactive amounts to active centers using grown amounts."""
    KEY  = ["entity", "project", "code"]
    path = lambda g: ["entity", "project"] + ANCESTRY[:ANCESTRY.index(g) + 1]

    active   = universe.filter( pl.col("is_active"))
    inactive = universe.filter(~pl.col("is_active") & (pl.col("amount") != 0))

    active_current, remaining, flows = active, inactive, []
    for g in FALLBACK:
        if remaining.is_empty():                 # nothing left to distribute
            break
        keys = path(g)
        rem_keys = remaining.select(keys).unique()
        # only active rows in groups that still have pending inactive amount matter here;
        # restrict the group_by / dist build to those instead of the whole active set
        act_in = active_current.join(rem_keys, on=keys, how="semi")
        if act_in.is_empty():
            continue
        g_stats = (act_in.group_by(keys)
                   .agg(pl.col("amount").sum().alias("gtot"), pl.len().alias("gcnt")))
        resolving = remaining.join(g_stats.select(keys), on=keys, how="semi")
        if resolving.is_empty():
            continue
        tot  = resolving.group_by(keys).agg(pl.col("amount").sum().alias("inact_tot"))
        dist = (
            act_in.select(keys + ["code", "amount"])
            .join(g_stats, on=keys).join(tot, on=keys)
            .with_columns(
                pl.when(pl.col("gtot") > 0)
                  .then(pl.col("amount") * pl.col("inact_tot") / pl.col("gtot"))
                  .otherwise(pl.col("inact_tot") / pl.col("gcnt")).alias("received")
            )
        )
        active_current = (
            active_current.join(dist.select(KEY + ["received"]), on=KEY, how="left")
            .with_columns((pl.col("amount") + pl.col("received").fill_null(0.0)).alias("amount"))
            .drop("received")
        )
        flows.append(dist.select(KEY + ["received", pl.lit(g).alias("resolved_level")]))
        remaining = remaining.join(resolving.select(KEY), on=KEY, how="anti")

    audit = (pl.concat(flows) if flows else pl.DataFrame(schema={
                "entity": pl.Utf8, "project": pl.Utf8, "code": pl.Utf8,
                "received": pl.Float64, "resolved_level": pl.Utf8}))

    grown = active_current.select(KEY + [pl.col("amount").alias("_grown")])
    kept  = remaining.select(KEY).with_columns(pl.lit(True).alias("_kept"))
    result = (
        universe.join(grown, on=KEY, how="left").join(kept, on=KEY, how="left")
        .with_columns(
            pl.when(pl.col("is_active")).then(pl.col("_grown"))
              .when(pl.col("_kept").fill_null(False) | (pl.col("amount") == 0)).then(pl.col("amount"))
              .otherwise(0.0).alias("amount_active")
        )
    )
    if not keep_empty:
        result = result.filter((pl.col("amount") != 0) | (pl.col("amount_active") != 0))
    result = result.select(KEY + ANCESTRY + ["is_active", "amount", "amount_active"])
    return result, audit


def reallocate_v3(
    lf_amounts, lf_centers, *,
    truth_entity="Entity Code", truth_code="Mapped Centre", status_col="Active",
    active_value=True,
    levels=("level1", "level2", "level3", "level4", "level5", "level6", "level7"),
    fallback_levels=("level6", "level5", "level4", "level3", "level2", "level1"),
    amt_entity="Local Entity Code", project_col="Project",
    amt_code="AGG Center Code", amt_col="amount",
    amt_levels=None, truth_levels=None,
    unmatched="inactive", keep_empty=False,
):
    ANCESTRY    = list(levels)
    FALLBACK    = list(fallback_levels)
    amt_levels   = list(levels if amt_levels   is None else amt_levels)
    truth_levels = list(levels if truth_levels is None else truth_levels)

    universe = _prepare_universe(
        lf_amounts, lf_centers,
        truth_entity=truth_entity, truth_code=truth_code, status_col=status_col,
        active_value=active_value, ANCESTRY=ANCESTRY,
        amt_entity=amt_entity, project_col=project_col, amt_code=amt_code,
        amt_col=amt_col, amt_levels=amt_levels, truth_levels=truth_levels, unmatched=unmatched,
    )
    result, audit = _cascade(universe, ANCESTRY=ANCESTRY, FALLBACK=FALLBACK, keep_empty=keep_empty)

    rename_out = {"entity": truth_entity, "project": project_col, "code": truth_code}
    return (result.rename({**rename_out, "is_active": status_col}).lazy(),
            audit.rename(rename_out).lazy())
