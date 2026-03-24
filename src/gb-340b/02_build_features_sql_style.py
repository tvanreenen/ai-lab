from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from _common import get_paths, log_stage
from _rule_features import (
    add_member_same_drug_history,
    compute_dispense_pattern_risk_score,
    compute_duplicate_discount_risk_score,
)


def build_features(stage_dir: Path) -> pd.DataFrame:
    stage = Path(stage_dir)
    claims = pd.read_parquet(stage / "claim_fact.parquet")
    tpa = pd.read_parquet(stage / "tpa_determination.parquet")

    claims["service_date"] = pd.to_datetime(claims["service_date"])
    tpa["determination_date"] = pd.to_datetime(tpa["determination_date"])

    ddr = compute_duplicate_discount_risk_score(claims)
    dpr = compute_dispense_pattern_risk_score(claims)
    claims = claims.copy()
    claims["duplicate_discount_risk_score"] = claims["claim_id"].map(ddr).astype("float64")
    claims["dispense_pattern_risk_score"] = claims["claim_id"].map(dpr).astype("float64")

    cte = claims.merge(tpa, on="claim_id", how="left")
    cte = add_member_same_drug_history(cte)
    cte["asof_date"] = cte["service_date"]
    cte["claim_month"] = cte["asof_date"].dt.to_period("M").dt.to_timestamp("M")
    cm0 = cte["claim_month"].min()
    cte["months_since_panel_start"] = (
        (cte["claim_month"].dt.year - cm0.year) * 12 + (cte["claim_month"].dt.month - cm0.month)
    ).astype("int64")

    cte_sorted = cte.sort_values(["member_id", "asof_date"]).copy()
    prior_counts: list[int] = []
    prior_amounts: list[float] = []
    for _, g in cte_sorted.groupby("member_id", sort=False):
        dts = g["asof_date"].to_numpy()
        amts = g["claim_amount"].to_numpy()
        n = len(g)
        pc = [0] * n
        pa = [0.0] * n
        for j in range(n):
            window_start = pd.Timestamp(dts[j]) - pd.Timedelta(days=90)
            s = 0
            tot = 0.0
            for k in range(j):
                if pd.Timestamp(dts[k]) >= window_start and pd.Timestamp(dts[k]) < pd.Timestamp(dts[j]):
                    s += 1
                    tot += float(amts[k])
            pc[j] = s
            pa[j] = round(tot, 2)
        prior_counts.extend(pc)
        prior_amounts.extend(pa)

    cte_sorted["member_prior_claims_90d"] = prior_counts
    cte_sorted["member_prior_amount_90d"] = prior_amounts

    out = cte_sorted.sort_values("claim_id").reset_index(drop=True)
    out["tpa_eligible"] = out["tpa_eligible"].astype(int)
    out["is_contract_pharmacy"] = out["is_contract_pharmacy"].astype(int)
    out["medicaid_carve_out_indicator"] = out["medicaid_carve_out_indicator"].astype(int)
    out["on_ce_formulary_flag"] = out["on_ce_formulary_flag"].astype(int)
    dsp = out["days_since_prior_fill_same_drug"].to_numpy(dtype="float64")
    out["days_since_prior_fill_same_drug"] = np.where(
        dsp >= 500.0,
        366.0,
        np.clip(dsp, 0.0, 366.0),
    )
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Stage 02: build as-of features (SQL-style)")
    p.parse_args()
    paths = get_paths()
    features = build_features(paths.stage)
    feat_path = paths.stage / "features_asof.parquet"
    features.to_parquet(feat_path, index=False)
    log_stage(
        "02_build_features",
        rows=len(features),
        min_date=features["asof_date"].min(),
        max_date=features["asof_date"].max(),
        path=feat_path,
    )


if __name__ == "__main__":
    main()
