from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from _common import get_paths, log_stage


def build_raw_sources(n_accounts: int, n_months: int, seed: int, start: str) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    month_ends = pd.period_range(start=start, periods=n_months, freq="M").to_timestamp("M")

    account_id = np.arange(1, n_accounts + 1, dtype=int)
    industry = rng.choice(
        ["software", "finance", "healthcare", "retail", "manufacturing", "services"],
        size=n_accounts,
        p=[0.22, 0.14, 0.14, 0.17, 0.16, 0.17],
    )
    region = rng.choice(["us", "eu", "uk", "apac", "latam"], size=n_accounts)
    employees = np.clip(np.exp(rng.normal(4.0, 1.0, n_accounts)).astype(int), 10, 80000)
    sales_led = rng.random(n_accounts) < 0.45
    account_dim = pd.DataFrame(
        {
            "account_id": account_id,
            "industry": industry,
            "region": region,
            "employee_count": employees,
            "sales_led": sales_led,
        },
    )

    rows_usage: list[dict[str, object]] = []
    rows_contract: list[dict[str, object]] = []
    rows_tickets: list[dict[str, object]] = []
    churn_events: list[dict[str, object]] = []

    for i in range(n_accounts):
        aid = int(account_id[i])
        vitality = rng.normal(0, 1)
        deal_quality = rng.normal(0, 1)
        discount = float(np.clip(5 + 8 * (-deal_quality) + rng.normal(0, 3), 0, 45))
        billing_annual = bool(rng.random() < 0.5 + 0.1 * np.tanh(deal_quality))
        churned = False
        for m_idx, month_end in enumerate(month_ends):
            if churned:
                break
            vitality = 0.88 * vitality + rng.normal(0, 0.4)
            macro = m_idx / max(n_months - 1, 1)

            mrr = float(np.clip(np.exp(6.0 + 0.35 * np.log(employees[i]) + 0.4 * vitality + rng.normal(0, 0.3)), 200, 500000))
            seats_purchased = int(np.clip(round(mrr / 850 + rng.normal(0, 4)), 3, 6000))
            seat_util = float(np.clip(0.55 + 0.12 * vitality - 0.004 * discount + rng.normal(0, 0.08), 0.05, 1.0))
            seats_used = int(np.clip(round(seats_purchased * seat_util), 1, seats_purchased))

            active_days_30d = int(np.clip(round(15 + 7 * vitality - 0.08 * discount + rng.normal(0, 3.5)), 0, 30))
            key_actions_30d = int(max(0, round(35 + 24 * vitality + 0.0015 * mrr + rng.normal(0, 15))))
            nps = float(np.clip(round(20 + 20 * vitality + rng.normal(0, 15)), -100, 100))
            nps = np.nan if rng.random() < 0.28 else nps

            z = (
                -1.35
                + 0.9 * (-vitality)
                + 0.55 * (discount / 30)
                + 0.45 * (1.0 - seat_util)
                - 0.2 * ((active_days_30d / 30) - 0.5)
                + 0.2 * macro
            )
            p_churn = 1 / (1 + np.exp(-z))
            if rng.random() < p_churn * 0.25:
                churned = True
                churn_events.append({"account_id": aid, "churn_date": month_end})

            rows_contract.append(
                {
                    "account_id": aid,
                    "snapshot_month": month_end,
                    "mrr": round(mrr, 2),
                    "discount_pct": round(discount, 2),
                    "billing_annual": billing_annual,
                    "seats_purchased": seats_purchased,
                    "seats_used": seats_used,
                    "seat_utilization": round(seat_util, 4),
                    "nps_score": nps,
                    "is_active": not churned,
                },
            )

            usage_start = month_end - pd.Timedelta(days=29)
            for d in pd.date_range(usage_start, month_end, freq="D"):
                rows_usage.append(
                    {
                        "account_id": aid,
                        "event_date": d,
                        "active_users": int(max(0, round((seats_used / 22) + rng.normal(0, 1.2)))),
                        "key_actions": int(max(0, round((key_actions_30d / 30) + rng.normal(0, 1.8)))),
                    },
                )

            ticket_count = int(np.clip(round(2 + 2.5 * max(-vitality, 0) + rng.poisson(1.2)), 0, 15))
            for _ in range(ticket_count):
                opened = month_end - pd.Timedelta(days=int(rng.integers(0, 30)))
                severity = str(rng.choice(["low", "medium", "high", "critical"], p=[0.38, 0.36, 0.2, 0.06]))
                rows_tickets.append(
                    {
                        "account_id": aid,
                        "opened_at": opened,
                        "severity": severity,
                        "resolution_hours": float(np.clip(rng.normal(18, 10), 1, 120)),
                    },
                )

    return {
        "account_dim": account_dim,
        "usage_daily": pd.DataFrame(rows_usage),
        "support_tickets": pd.DataFrame(rows_tickets),
        "contract_monthly": pd.DataFrame(rows_contract),
        "churn_events": pd.DataFrame(churn_events),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Stage 01: generate synthetic raw sources")
    p.add_argument("--n-accounts", type=int, default=2500)
    p.add_argument("--n-months", type=int, default=30)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--start", type=str, default="2022-01")
    args = p.parse_args()

    paths = get_paths()
    raw = build_raw_sources(args.n_accounts, args.n_months, args.seed, args.start)
    for name, df in raw.items():
        out = paths.stage / f"{name}.parquet"
        df.to_parquet(out, index=False)
        log_stage("01_extract_raw", table=name, rows=len(df), path=out)


if __name__ == "__main__":
    main()
