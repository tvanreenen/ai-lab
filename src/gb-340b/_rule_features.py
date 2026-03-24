"""Eligibility-oriented rule scores shared by extract (for labels) and stage 02."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_duplicate_discount_risk_score(claims: pd.DataFrame) -> pd.Series:
    """
    Proxy for **duplicate-discount / program attribution tension** (not refill overlap):
    Medicaid/MCO carve-out context, contract pharmacy, weak patient documentation, etc.
    Educational synthetic rules only—not a compliance determination.
    """
    df = claims.copy()
    pay = df["payer_category"].astype(str)
    carve = df["medicaid_carve_out_indicator"].astype(int)
    cc = df["is_contract_pharmacy"].astype(bool)
    link = df["patient_ce_linkage_tier"].astype(str)
    ch = df["channel"].astype(str)

    mco_med = pay.isin(["medicaid_ffs", "mco"])
    raw = (
        0.32 * (mco_med & (carve == 1)).astype(float)
        + 0.28 * (mco_med & (carve == 1) & cc).astype(float)
        + 0.26 * (link == "incomplete_chart").astype(float)
        + 0.12 * (link == "referral_only").astype(float)
        + 0.10 * ((pay == "medicare") & ch.isin(["specialty_pharmacy", "mail"])).astype(float)
    )
    score = raw.clip(0.0, 1.0)
    out = pd.DataFrame({"claim_id": df["claim_id"].to_numpy(), "duplicate_discount_risk_score": score})
    return out.set_index("claim_id")["duplicate_discount_risk_score"]


def compute_dispense_pattern_risk_score(claims: pd.DataFrame) -> pd.Series:
    """
    Secondary **operational** signal: refill overlap, same-day multi-pharmacy, quantity spike.
    Distinct from duplicate-discount policy risk.
    """
    df = claims.copy()
    df["service_date"] = pd.to_datetime(df["service_date"])
    df = df.sort_values(["member_id", "drug_class", "service_date"])
    g = df.groupby(["member_id", "drug_class"], sort=False)
    prev_svc = g["service_date"].shift(1)
    prev_ds = g["days_supply"].shift(1)
    prev_end = prev_svc + pd.to_timedelta(prev_ds.fillna(0).astype("int64"), unit="D")
    days_early = (prev_end - df["service_date"]).dt.days
    days_early = days_early.fillna(-1)
    refill_overlap = np.where(days_early > 0, np.minimum(days_early.astype("float64") / 22.0, 1.0), 0.0)

    df["_svc_cal"] = df["service_date"].dt.normalize()
    n_pharm = df.groupby(["member_id", "_svc_cal"], sort=False)["pharmacy_id"].transform("nunique")
    multi_pharm = (n_pharm > 1).astype("float64")

    ds = df["days_supply"].replace(0, np.nan).clip(lower=1).astype("float64")
    qty_ratio = df["quantity"].astype("float64") / ds
    qty_ratio = qty_ratio.replace([np.inf, -np.inf], np.nan).fillna(1.0)
    qty_spike = np.clip((qty_ratio - 1.0) / 1.25, 0.0, 1.0)

    raw = 0.05 + 0.38 * refill_overlap + 0.24 * multi_pharm + 0.12 * qty_spike
    score = np.clip(raw, 0.0, 1.0)
    out = pd.DataFrame({"claim_id": df["claim_id"].to_numpy(), "dispense_pattern_risk_score": score})
    return out.set_index("claim_id")["dispense_pattern_risk_score"]


def add_member_same_drug_history(df: pd.DataFrame) -> pd.DataFrame:
    """Prior fill count (365d) and days since last same-drug_class fill (same member)."""
    x = df.sort_values(["member_id", "drug_class", "service_date"]).copy()
    prior_365: list[int] = []
    days_since: list[float] = []
    for _, g in x.groupby(["member_id", "drug_class"], sort=False):
        dts = g["service_date"].to_numpy()
        n = len(g)
        pc = [0] * n
        ds_prior: list[float] = []
        for j in range(n):
            cur = pd.Timestamp(dts[j])
            window_start = cur - pd.Timedelta(days=365)
            pc[j] = sum(1 for k in range(j) if pd.Timestamp(dts[k]) >= window_start)
            if j == 0:
                ds_prior.append(999.0)
            else:
                ds_prior.append((cur - pd.Timestamp(dts[j - 1])).days)
        prior_365.extend(pc)
        days_since.extend(ds_prior)
    x["member_prior_fills_same_drug_365d"] = prior_365
    x["days_since_prior_fill_same_drug"] = days_since
    return x.sort_values("claim_id").reset_index(drop=True)
