from __future__ import annotations

import argparse

import pandas as pd
from _common import get_paths, log_stage


def build_labels(features: pd.DataFrame, churn_events: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    df["snapshot_month"] = pd.to_datetime(df["snapshot_month"])
    churn = churn_events.copy()
    if len(churn) == 0:
        churn["account_id"] = pd.Series(dtype="int64")
        churn["churn_date"] = pd.Series(dtype="datetime64[ns]")
    churn["churn_date"] = pd.to_datetime(churn.get("churn_date"))

    max_snapshot = df["snapshot_month"].max()
    cutoff = max_snapshot - pd.Timedelta(days=90)
    cte_horizon = df.loc[df["snapshot_month"] <= cutoff].copy()

    cte_join = cte_horizon.merge(churn, on="account_id", how="left")
    cte_join["churn_90d"] = (
        (cte_join["churn_date"] > cte_join["snapshot_month"])
        & (cte_join["churn_date"] <= cte_join["snapshot_month"] + pd.Timedelta(days=90))
    ).astype(int)
    return cte_join.drop(columns=["churn_date"])


def main() -> None:
    p = argparse.ArgumentParser(description="Stage 03: build labels from future churn window")
    p.parse_args()
    paths = get_paths()
    features = pd.read_parquet(paths.stage / "features_asof.parquet")
    churn_events = pd.read_parquet(paths.stage / "churn_events.parquet")
    labeled = build_labels(features, churn_events)
    out = paths.stage / "training_snapshots.parquet"
    labeled.to_parquet(out, index=False)
    log_stage(
        "03_build_labels",
        rows=len(labeled),
        positive_rate=round(float(labeled["churn_90d"].mean()), 4),
        path=out,
    )


if __name__ == "__main__":
    main()
