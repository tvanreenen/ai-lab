from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from _common import get_paths, log_stage
from _rule_features import (
    add_member_same_drug_history,
    compute_dispense_pattern_risk_score,
    compute_duplicate_discount_risk_score,
)


def _assign_days_supply(rng: np.random.Generator, drug_classes: np.ndarray) -> np.ndarray:
    out = np.zeros(len(drug_classes), dtype=int)
    for i, d in enumerate(drug_classes):
        if d in ("acute", "vaccine"):
            out[i] = int(rng.integers(3, 22))
        elif d == "maintenance":
            out[i] = int(rng.choice([28, 30, 90], p=[0.35, 0.45, 0.2]))
        elif d == "specialty":
            out[i] = int(rng.integers(14, 31))
        elif d == "oncology":
            out[i] = int(rng.integers(21, 29))
        else:
            out[i] = int(rng.integers(7, 31))
    return out


def build_raw_sources(n_claims: int, n_months: int, seed: int, start: str) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    month_starts = pd.period_range(start=start, periods=n_months, freq="M").to_timestamp()

    drug_choices = np.array(["specialty", "maintenance", "acute", "vaccine", "oncology"])
    drug_to_idx = {d: i for i, d in enumerate(drug_choices)}
    channels = np.array(["retail", "mail", "specialty_pharmacy", "hospital_outpatient"])
    bands = np.array(["low_script_pharmacy", "medium_script_pharmacy", "high_script_pharmacy"])
    payer_opts = np.array(["commercial", "mco", "medicaid_ffs", "medicare", "self_pay"])
    payer_p = np.array([0.36, 0.2, 0.14, 0.22, 0.08])
    linkage_opts = np.array(["documented_visit", "referral_only", "incomplete_chart"])
    linkage_p = np.array([0.66, 0.2, 0.14])

    claim_ids = np.arange(1, n_claims + 1, dtype=int)
    member_ids = rng.integers(1, max(2, n_claims // 6), size=n_claims)

    rows_claim: list[dict[str, object]] = []
    for i in range(n_claims):
        cid = int(claim_ids[i])
        mid = int(member_ids[i])
        m_start = month_starts[int(rng.integers(0, n_months))]
        service_date = m_start + pd.Timedelta(days=int(rng.integers(0, 27)))
        d_idx = int(rng.choice(len(drug_choices), p=[0.28, 0.32, 0.22, 0.1, 0.08]))
        drug = str(drug_choices[d_idx])
        channel = str(rng.choice(channels, p=[0.42, 0.28, 0.22, 0.08]))

        base_amt = float(np.clip(rng.lognormal(5.2, 1.1), 15, 85000))
        if drug == "oncology":
            base_amt *= float(rng.uniform(1.2, 2.8))
        claim_amount = round(base_amt, 2)

        payer = str(rng.choice(payer_opts, p=payer_p))
        linkage = str(rng.choice(linkage_opts, p=linkage_p))
        carve = int(payer in ("medicaid_ffs", "mco") and rng.random() < 0.42)
        on_form = int(rng.random() < 0.9 - 0.07 * int(drug in ("oncology", "specialty")))
        if drug in ("acute", "vaccine"):
            cdb = "standard"
        elif drug in ("oncology", "specialty"):
            cdb = "specialty_tier"
        else:
            cdb = "maintenance_tier"

        rows_claim.append(
            {
                "claim_id": cid,
                "member_id": mid,
                "service_date": service_date,
                "drug_class": drug,
                "claim_amount": claim_amount,
                "channel": channel,
                "payer_category": payer,
                "medicaid_carve_out_indicator": carve,
                "patient_ce_linkage_tier": linkage,
                "on_ce_formulary_flag": bool(on_form),
                "covered_drug_bucket": cdb,
            },
        )

    df = pd.DataFrame(rows_claim)
    df = df.sort_values(["member_id", "drug_class", "service_date"])
    df["fill_number"] = df.groupby(["member_id", "drug_class"], sort=False).cumcount() + 1

    drug_arr = df["drug_class"].to_numpy()
    df["days_supply"] = _assign_days_supply(rng, drug_arr)
    unit_per_day = rng.uniform(0.75, 1.45, size=len(df))
    df["quantity"] = np.round(df["days_supply"].to_numpy() * unit_per_day, 2)

    n_pharm = 55
    pharm_ids: list[int] = []
    for _, g in df.groupby("member_id", sort=False):
        pid = int(rng.integers(1, n_pharm))
        for _ in range(len(g)):
            pharm_ids.append(pid)
            if rng.random() < 0.12:
                pid = int(rng.integers(1, n_pharm))
    df["pharmacy_id"] = pharm_ids

    df["is_contract_pharmacy"] = rng.random(len(df)) < 0.74
    df["pharmacy_volume_band"] = [str(bands[int(pid) % 3]) for pid in df["pharmacy_id"].to_numpy()]

    icc = df["is_contract_pharmacy"].to_numpy()
    ch = df["channel"].astype(str).to_numpy()
    role = np.where(
        icc,
        "contract_pharmacy",
        np.where(
            ch == "hospital_outpatient",
            "hospital_outpatient_rx",
            np.where(ch == "mail", "mail_order", "child_site_dispense"),
        ),
    )
    df["dispense_site_role"] = role

    df = df.sort_values("claim_id").reset_index(drop=True)

    ddr_by_claim = compute_duplicate_discount_risk_score(df)
    dpr_by_claim = compute_dispense_pattern_risk_score(df)
    df_lbl = add_member_same_drug_history(df)

    rows_tpa: list[dict[str, object]] = []
    rows_audit: list[dict[str, object]] = []
    risky_drug_idx = {3, 4}

    for row in df_lbl.itertuples(index=False):
        cid = int(row.claim_id)
        d_idx = drug_to_idx[str(row.drug_class)]
        ddr = float(ddr_by_claim.loc[cid])
        dpr = float(dpr_by_claim.loc[cid])
        incomplete = int(str(row.patient_ce_linkage_tier) == "incomplete_chart")
        referral = int(str(row.patient_ce_linkage_tier) == "referral_only")
        medicaidish = int(str(row.payer_category) in ("medicaid_ffs", "mco"))
        carve = int(row.medicaid_carve_out_indicator)
        contract = int(bool(row.is_contract_pharmacy))
        on_form = int(bool(row.on_ce_formulary_flag))
        specialty_bucket = int(str(row.covered_drug_bucket) == "specialty_tier")
        contract_role = int(str(row.dispense_site_role) == "contract_pharmacy")

        tpa_eligible = bool(rng.random() < 0.88 - 0.05 * int(d_idx in risky_drug_idx))
        det_date = row.service_date + pd.Timedelta(days=int(rng.integers(0, 5)))
        rows_tpa.append(
            {
                "claim_id": cid,
                "tpa_eligible": tpa_eligible,
                "determination_date": det_date,
            },
        )

        if rng.random() < 0.26:
            lag_days = int(rng.integers(10, 95))
            audit_complete = row.service_date + pd.Timedelta(days=lag_days)
            amt_norm = np.log1p(row.claim_amount) / 11.0
            z = (
                -2.02
                + 1.85 * ddr
                + 0.28 * dpr
                + 0.48 * incomplete
                + 0.18 * referral
                + 0.42 * float(medicaidish & carve & contract)
                + 0.35 * (1 - on_form)
                + 0.12 * contract_role
                + 0.2 * specialty_bucket
                + 0.38 * amt_norm
                + 0.24 * int(str(row.channel) == "mail")
                + 0.32 * int(str(row.channel) == "hospital_outpatient")
                + 0.45 * int(d_idx in risky_drug_idx)
                + 0.08 * min(int(row.member_prior_fills_same_drug_365d), 10)
                + rng.normal(0, 0.34)
            )
            p_find = float(1 / (1 + np.exp(-z)))
            finding = int(rng.random() < p_find)
            rows_audit.append(
                {
                    "claim_id": cid,
                    "audit_complete_date": audit_complete,
                    "eligibility_confirmation_finding": finding,
                },
            )

    return {
        "claim_fact": df,
        "tpa_determination": pd.DataFrame(rows_tpa),
        "ce_audit_outcomes": pd.DataFrame(rows_audit),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Stage 01: generate synthetic raw sources")
    p.add_argument("--n-claims", type=int, default=12000)
    p.add_argument("--n-months", type=int, default=42)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--start", type=str, default="2021-01")
    args = p.parse_args()

    paths = get_paths()
    raw = build_raw_sources(args.n_claims, args.n_months, args.seed, args.start)
    for name, df in raw.items():
        out = paths.stage / f"{name}.parquet"
        df.to_parquet(out, index=False)
        log_stage("01_extract_raw", table=name, rows=len(df), path=out)


if __name__ == "__main__":
    main()
