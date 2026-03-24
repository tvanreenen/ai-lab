from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from _common import get_paths, log_stage


def build_features(stage_dir: Path) -> pd.DataFrame:
    stage = Path(stage_dir)
    account_dim = pd.read_parquet(stage / "account_dim.parquet")
    usage = pd.read_parquet(stage / "usage_daily.parquet")
    tickets = pd.read_parquet(stage / "support_tickets.parquet")
    contract = pd.read_parquet(stage / "contract_monthly.parquet")

    usage["event_date"] = pd.to_datetime(usage["event_date"])
    tickets["opened_at"] = pd.to_datetime(tickets["opened_at"])
    contract["snapshot_month"] = pd.to_datetime(contract["snapshot_month"])

    cte_snapshots = contract.loc[contract["is_active"]].copy()
    cte_snapshots = cte_snapshots.rename(columns={"snapshot_month": "asof_month"})

    cte_usage_30 = (
        usage.assign(asof_month=usage["event_date"].dt.to_period("M").dt.to_timestamp("M"))
        .groupby(["account_id", "asof_month"], as_index=False)
        .agg(active_users_30d=("active_users", "sum"), key_actions_30d=("key_actions", "sum"))
    )
    cte_usage_30 = cte_usage_30.sort_values(["account_id", "asof_month"])
    cte_usage_30["active_users_prev_30d"] = cte_usage_30.groupby("account_id")["active_users_30d"].shift(1)
    cte_usage_30["usage_trend_30d"] = (
        cte_usage_30["active_users_30d"] / cte_usage_30["active_users_prev_30d"].replace(0, pd.NA)
    ).astype("float64")
    cte_usage_30["usage_trend_30d"] = cte_usage_30["usage_trend_30d"].fillna(1.0).clip(lower=0.2, upper=3.0)

    cte_ticket_30 = (
        tickets.assign(asof_month=tickets["opened_at"].dt.to_period("M").dt.to_timestamp("M"))
        .groupby(["account_id", "asof_month"], as_index=False)
        .agg(
            tickets_30d=("severity", "count"),
            avg_resolution_hours=("resolution_hours", "mean"),
            high_severity_tickets_30d=("severity", lambda x: int((x.isin(["high", "critical"])).sum())),
        )
    )

    cte_ticket_90 = (
        cte_ticket_30.sort_values(["account_id", "asof_month"])
        .set_index("asof_month")
        .groupby("account_id")["high_severity_tickets_30d"]
        .rolling("90D", min_periods=1)
        .sum()
        .rename("high_severity_tickets_90d")
        .reset_index()
    )

    cte = (
        cte_snapshots.merge(account_dim, on="account_id", how="left")
        .merge(cte_usage_30, on=["account_id", "asof_month"], how="left")
        .merge(cte_ticket_30, on=["account_id", "asof_month"], how="left")
        .merge(cte_ticket_90, on=["account_id", "asof_month"], how="left")
    )
    cte = cte.rename(columns={"asof_month": "snapshot_month"})
    cte = cte.fillna(
        {
            "active_users_30d": 0,
            "key_actions_30d": 0,
            "active_users_prev_30d": 0,
            "usage_trend_30d": 1.0,
            "tickets_30d": 0,
            "avg_resolution_hours": 0.0,
            "high_severity_tickets_30d": 0,
            "high_severity_tickets_90d": 0,
        },
    )
    cte["tenure_months"] = cte.sort_values(["account_id", "snapshot_month"]).groupby("account_id").cumcount() + 1
    cte["month_index"] = cte["snapshot_month"].rank(method="dense").astype(int) - 1
    return cte


def main() -> None:
    p = argparse.ArgumentParser(description="Stage 02: build as-of features (SQL-style)")
    p.parse_args()
    paths = get_paths()
    features = build_features(paths.stage)
    out = paths.stage / "features_asof.parquet"
    features.to_parquet(out, index=False)
    log_stage(
        "02_build_features",
        rows=len(features),
        min_month=features["snapshot_month"].min(),
        max_month=features["snapshot_month"].max(),
        path=out,
    )


if __name__ == "__main__":
    main()
