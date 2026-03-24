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

    account_dim = pd.read_parquet(paths.stage / "account_dim.parquet")
    usage_daily = pd.read_parquet(paths.stage / "usage_daily.parquet")
    support_tickets = pd.read_parquet(paths.stage / "support_tickets.parquet")
    contract_monthly = pd.read_parquet(paths.stage / "contract_monthly.parquet")
    churn_events = pd.read_parquet(paths.stage / "churn_events.parquet")
    features_asof = pd.read_parquet(paths.stage / "features_asof.parquet")
    training_snapshots = pd.read_parquet(paths.stage / "training_snapshots.parquet")
    scored_accounts = pd.read_parquet(paths.output / "scored_accounts.parquet")

    metrics = json.loads((paths.artifacts / "metrics.json").read_text())
    now = datetime.now(UTC).isoformat()

    risk_counts = scored_accounts["risk_category"].value_counts(dropna=False).to_dict()
    for k in ("high", "medium", "low"):
        risk_counts.setdefault(k, 0)

    lines = [
        "# gb-churn run summary",
        "",
        f"- generated_at_utc: `{now}`",
        "",
        "## Stage row counts",
        "",
        f"- account_dim: `{len(account_dim)}`",
        f"- usage_daily: `{len(usage_daily)}`",
        f"- support_tickets: `{len(support_tickets)}`",
        f"- contract_monthly: `{len(contract_monthly)}`",
        f"- churn_events: `{len(churn_events)}`",
        f"- features_asof: `{len(features_asof)}`",
        f"- training_snapshots: `{len(training_snapshots)}`",
        f"- scored_accounts: `{len(scored_accounts)}`",
        "",
        "## Backtest metrics",
        "",
        f"- rows_train: `{metrics['rows_train']}`",
        f"- rows_val: `{metrics['rows_val']}`",
        f"- rows_test: `{metrics['rows_test']}`",
        f"- test_churn_rate: `{metrics['test_churn_rate']:.4f}`",
        f"- roc_auc_test: `{metrics['roc_auc_test']:.4f}`",
        f"- pr_auc_test: `{metrics['pr_auc_test']:.4f}`",
        f"- precision_at_top_10pct: `{metrics['precision_at_top_10pct']:.4f}`",
        f"- best_iteration: `{metrics['best_iteration']}`",
        "",
        "## Latest scoring distribution",
        "",
        f"- latest_snapshot_month: `{pd.to_datetime(scored_accounts['snapshot_month']).max().date()}`",
        f"- high_count: `{risk_counts['high']}`",
        f"- medium_count: `{risk_counts['medium']}`",
        f"- low_count: `{risk_counts['low']}`",
        f"- p_churn_min: `{float(scored_accounts['p_churn_90d'].min()):.4f}`",
        f"- p_churn_max: `{float(scored_accounts['p_churn_90d'].max()):.4f}`",
        f"- p_churn_mean: `{float(scored_accounts['p_churn_90d'].mean()):.4f}`",
        "",
    ]

    out = paths.artifacts / "run_report.md"
    out.write_text("\n".join(lines))
    log_stage("06_report_run", path=out, rows_scored=len(scored_accounts))


if __name__ == "__main__":
    main()
