from __future__ import annotations

import argparse

import joblib
import numpy as np
import pandas as pd
from _common import get_paths, log_stage


def main() -> None:
    p = argparse.ArgumentParser(description="Stage 05: score latest claim month")
    p.parse_args()
    paths = get_paths()

    features = pd.read_parquet(paths.stage / "features_asof.parquet")
    features["claim_month"] = pd.to_datetime(features["claim_month"])
    model_blob = joblib.load(paths.artifacts / "model.joblib")
    pre = model_blob["preprocessor"]
    model = model_blob["model"]
    cols = model_blob["feature_columns"]

    latest_month = features["claim_month"].max()
    latest = features.loc[features["claim_month"] == latest_month].copy()
    X = latest[[c for c in cols if c in latest.columns]]
    missing = [c for c in cols if c not in latest.columns]
    if missing:
        for c in missing:
            X[c] = np.nan
        X = X[cols]
    X_t = pre.transform(X)
    latest["p_eligibility_confirmation_finding"] = model.predict_proba(X_t)[:, 1]

    high_cut = float(latest["p_eligibility_confirmation_finding"].quantile(0.9))
    med_cut = float(latest["p_eligibility_confirmation_finding"].quantile(0.7))
    latest["risk_category"] = np.select(
        [latest["p_eligibility_confirmation_finding"] >= high_cut, latest["p_eligibility_confirmation_finding"] >= med_cut],
        ["high", "medium"],
        default="low",
    )

    out = latest[
        ["claim_id", "claim_month", "p_eligibility_confirmation_finding", "risk_category"]
    ].sort_values("p_eligibility_confirmation_finding", ascending=False)
    out_path = paths.output / "scored_claims.parquet"
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
