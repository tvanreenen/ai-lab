from __future__ import annotations

import argparse

import joblib
import numpy as np
import pandas as pd
from _common import get_paths, log_stage

DROP_COLS = ("account_id", "snapshot_month", "churn_90d")


def main() -> None:
    p = argparse.ArgumentParser(description="Stage 05: score latest period")
    p.parse_args()
    paths = get_paths()

    features = pd.read_parquet(paths.stage / "features_asof.parquet")
    model_blob = joblib.load(paths.artifacts / "model.joblib")
    pre = model_blob["preprocessor"]
    model = model_blob["model"]
    cols = model_blob["feature_columns"]

    latest_month = pd.to_datetime(features["snapshot_month"]).max()
    latest = features.loc[features["snapshot_month"] == latest_month].copy()
    X = latest[cols]
    X_t = pre.transform(X)
    latest["p_churn_90d"] = model.predict_proba(X_t)[:, 1]

    high_cut = float(latest["p_churn_90d"].quantile(0.9))
    med_cut = float(latest["p_churn_90d"].quantile(0.7))
    latest["risk_category"] = np.select(
        [latest["p_churn_90d"] >= high_cut, latest["p_churn_90d"] >= med_cut],
        ["high", "medium"],
        default="low",
    )

    out = latest[["account_id", "snapshot_month", "p_churn_90d", "risk_category"]].sort_values("p_churn_90d", ascending=False)
    out_path = paths.output / "scored_accounts.parquet"
    out.to_parquet(out_path, index=False)
    log_stage(
        "05_score_new_period",
        latest_month=latest_month.date(),
        rows=len(out),
        high_count=int((out["risk_category"] == "high").sum()),
        path=out_path,
    )


if __name__ == "__main__":
    main()
