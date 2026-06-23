from __future__ import annotations

import numpy as np
import pandas as pd


def z_scores(values: pd.Series, reference: pd.Series | None = None) -> pd.Series:
    ref = pd.to_numeric(reference if reference is not None else values, errors="coerce")
    vals = pd.to_numeric(values, errors="coerce")
    std = ref.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return ((vals - ref.mean()) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def percentile_ranks(values: pd.Series, higher_is_better: bool = True) -> pd.Series:
    vals = pd.to_numeric(values, errors="coerce")
    if vals.nunique(dropna=True) <= 1:
        return pd.Series(50.0, index=values.index)
    pct = vals.rank(pct=True) * 100
    if not higher_is_better:
        pct = 100 - pct + (100 / vals.count())
    return pct.clip(0, 100)


def competition_season_normalize(df: pd.DataFrame, metric_cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    group_cols = [c for c in ["competition", "season"] if c in out.columns]
    if not group_cols:
        for metric in metric_cols:
            out[f"{metric}_z"] = z_scores(out[metric])
            out[f"{metric}_pctile"] = percentile_ranks(out[metric])
        return out
    for metric in metric_cols:
        out[f"{metric}_z"] = out.groupby(group_cols, group_keys=False)[metric].apply(z_scores)
        out[f"{metric}_pctile"] = out.groupby(group_cols, group_keys=False)[metric].apply(percentile_ranks)
    return out
