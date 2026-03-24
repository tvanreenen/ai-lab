from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

import pandas as pd
from _common import get_paths, log_stage


def main() -> None:
    p = argparse.ArgumentParser(description="Stage 06: build run summary report")
    p.parse_args()
    paths = get_paths()

    claim_fact = pd.read_parquet(paths.stage / "claim_fact.parquet")
    tpa_determination = pd.read_parquet(paths.stage / "tpa_determination.parquet")
    ce_audit_outcomes = pd.read_parquet(paths.stage / "ce_audit_outcomes.parquet")
    features_asof = pd.read_parquet(paths.stage / "features_asof.parquet")
    training_snapshots = pd.read_parquet(paths.stage / "training_snapshots.parquet")
    scored_claims = pd.read_parquet(paths.output / "scored_claims.parquet")

    metrics = json.loads((paths.artifacts / "metrics.json").read_text())
    now = datetime.now(UTC).isoformat()

    risk_counts = scored_claims["risk_category"].value_counts(dropna=False).to_dict()
    for k in ("high", "medium", "low"):
        risk_counts.setdefault(k, 0)

    lines = [
        "# gb-340b run summary (eligibility confirmation prioritization)",
        "",
        f"- generated_at_utc: `{now}`",
        "",
        "## Stage row counts",
        "",
        f"- claim_fact: `{len(claim_fact)}`",
        f"- tpa_determination: `{len(tpa_determination)}`",
        f"- ce_audit_outcomes: `{len(ce_audit_outcomes)}`",
        f"- features_asof: `{len(features_asof)}`",
        f"- training_snapshots: `{len(training_snapshots)}`",
        f"- scored_claims: `{len(scored_claims)}`",
        "",
        "## Backtest metrics",
        "",
        f"- rows_train: `{metrics['rows_train']}`",
        f"- rows_val: `{metrics['rows_val']}`",
        f"- rows_test: `{metrics['rows_test']}`",
        f"- test_positive_rate: `{metrics['test_positive_rate']:.4f}`",
        f"- roc_auc_test: `{metrics['roc_auc_test']:.4f}`",
        f"- pr_auc_test: `{metrics['pr_auc_test']:.4f}`",
        f"- precision_at_top_10pct: `{metrics['precision_at_top_10pct']:.4f}`",
        f"- random_precision_at_top_10pct_mean: `{metrics['random_precision_at_top_10pct_mean']:.4f}`",
        f"- lift_vs_random_mean_at_top_10pct: `{metrics['lift_vs_random_mean_at_top_10pct']:.4f}`",
        f"- lift_vs_prevalence_at_top_10pct: `{metrics['lift_vs_prevalence_at_top_10pct']:.4f}`",
        f"- best_iteration: `{metrics['best_iteration']}`",
        "",
        "## Latest scoring distribution",
        "",
        f"- latest_claim_month: `{pd.to_datetime(scored_claims['claim_month']).max().date()}`",
        f"- high_count: `{risk_counts['high']}`",
        f"- medium_count: `{risk_counts['medium']}`",
        f"- low_count: `{risk_counts['low']}`",
        f"- p_eligibility_confirmation_finding_min: `{float(scored_claims['p_eligibility_confirmation_finding'].min()):.4f}`",
        f"- p_eligibility_confirmation_finding_max: `{float(scored_claims['p_eligibility_confirmation_finding'].max()):.4f}`",
        f"- p_eligibility_confirmation_finding_mean: `{float(scored_claims['p_eligibility_confirmation_finding'].mean()):.4f}`",
        "",
    ]

    out = paths.artifacts / "run_report.md"
    out.write_text("\n".join(lines))
    log_stage("06_report_run", path=out, rows_scored=len(scored_claims))


if __name__ == "__main__":
    main()
