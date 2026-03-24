from __future__ import annotations

import argparse

import pandas as pd
from _common import get_paths, log_stage


def build_labels(features: pd.DataFrame, audits: pd.DataFrame) -> pd.DataFrame:
    df = features.copy()
    df["asof_date"] = pd.to_datetime(df["asof_date"])
    aud = audits.copy()
    aud["audit_complete_date"] = pd.to_datetime(aud["audit_complete_date"])

    cte = df.merge(aud, on="claim_id", how="inner")
    cte = cte.loc[cte["audit_complete_date"] >= cte["asof_date"]].copy()

    max_audit = cte["audit_complete_date"].max()
    label_cutoff = max_audit - pd.Timedelta(days=45)
    return cte.loc[cte["audit_complete_date"] <= label_cutoff].copy()


def main() -> None:
    p = argparse.ArgumentParser(
        description="Stage 03: training rows with eligibility_confirmation_finding and audit-completion cutoff",
    )
    p.parse_args()
    paths = get_paths()
    features = pd.read_parquet(paths.stage / "features_asof.parquet")
    audits = pd.read_parquet(paths.stage / "ce_audit_outcomes.parquet")
    if len(audits) == 0:
        msg = "ce_audit_outcomes is empty; increase n-claims or adjust seed"
        raise SystemExit(msg)
    labeled = build_labels(features, audits)
    out = paths.stage / "training_snapshots.parquet"
    labeled.to_parquet(out, index=False)
    log_stage(
        "03_build_labels",
        rows=len(labeled),
        positive_rate=round(float(labeled["eligibility_confirmation_finding"].mean()), 4),
        label_cutoff=str(labeled["audit_complete_date"].max().date()),
        path=out,
    )


if __name__ == "__main__":
    main()
