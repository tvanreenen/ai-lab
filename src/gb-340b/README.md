# gb-340b staged CE eligibility-confirmation prioritization (synthetic, SQL-style)

`gb-340b` is a process-first simulation of how a **covered entity (CE)** might **prioritize a limited independent review** of pharmacy claims after a **TPA eligibility determination**—focused on **eligibility confirmation** (patient / payer / site / drug evidence), not on replacing the TPA or HRSA policy. It mirrors the staged Parquet pattern used in `gb-churn`.

**What this is not**

- Not a **statutory 340B eligibility engine** and not legal or compliance advice.
- **`duplicate_discount_risk_score`** is a **toy proxy** for program-attribution / carve-out tension—not a manufacturer rebate engine or Medicaid billing determination.
- **`dispense_pattern_risk_score`** is **operational** (refill overlap, multi-pharmacy, quantity)—**not** the same as duplicate-discount policy risk.

**Framing**

- The **TPA** already produces **eligible / ineligible** (or covered / not covered) determinations. Those are **inputs** (`tpa_eligible`), not the ML target.
- The CE can only **sample and independently review** a small fraction of claims. Historical **CE review outcomes** train a model to output **`p_eligibility_confirmation_finding`** and **risk buckets** to focus that budget.
- The training label is **`eligibility_confirmation_finding`**: synthetic stand-in for “material gap vs documentation / policy expectations on eligibility confirmation,” recorded when a CE review completes (`ce_audit_outcomes`).

The bundled **synthetic generator** links that label mainly to **payer / carve-out / patient documentation / site / formulary** signals, with a **smaller** weight on dispense-pattern rules. Training uses **validation ROC-AUC** for early stopping; `metrics.json` still reports **test PR-AUC** and budget metrics.

**Disclaimer:** Synthetic data and educational example only — not legal, compliance, or clinical advice.

## End product: what you leverage after the pipeline

The run does not “finish” at model training—it finishes at a **ranked work queue** auditors or analysts can pull from, plus a **short metrics brief** for governance.

### Deliverable 1: `data/output/scored_claims.parquet`

Stage **05** writes **one row per claim** in the **latest `claim_month`** cohort (the current exercise’s “next period to review”).

| Column | Role |
|--------|------|
| **`claim_id`** | Join key back to `claim_fact`, warehouse claim line, or worklist. |
| **`claim_month`** | Scoring cohort (month-end anchor used in this repo). |
| **`p_eligibility_confirmation_finding`** | Modeled probability of a **positive** CE eligibility-confirmation finding—**rank on this** when slots are limited. |
| **`risk_category`** | **`high` / `medium` / `low`** from **within-month quantiles** (default: ~top 10% `high`, next ~20% `medium`). **Relative** to that month’s score distribution—not a legal “risk grade.” |

**Illustrative rows** (fabricated; your numbers will differ):

| claim_id | claim_month | p_eligibility_confirmation_finding | risk_category |
|---------|-------------|-------------------------------------|---------------|
| 11842 | 2024-06-30 | 0.71 | high |
| 11501 | 2024-06-30 | 0.54 | high |
| 11990 | 2024-06-30 | 0.41 | medium |
| 11703 | 2024-06-30 | 0.18 | low |

**Typical use:** sort descending on **`p_eligibility_confirmation_finding`**, take the top **k** claims that match this week’s review capacity, join to source systems for context, and route to reviewers. Tiers can gate workflows (“high first”) or reporting slices.

### Deliverable 2: `artifacts/run_report.md` and `artifacts/metrics.json`

Backtest **row counts**, **precision @ top 10%** vs random at the same k, lift vs prevalence, AUCs, and the **distribution** of scores on the latest month—useful for “did this run look sane?” before anyone opens the queue.

### Carrying this into production-shaped systems

Keep the same **idea**, broaden the **metadata**:

- Add **`model_version`**, **`scored_at`**, **`feature_snapshot_id`** (or training data version) on each scored row—or store scores in a table with those columns keyed by `claim_id` + run.
- Decide whether **`risk_category`** stays **quantile-based** (adapts each month) or moves to **calibrated probability cut points** after validation.
- Join **`claim_id`** to NDC, member token, pharmacy, payer fields for the **review UI**—the model file only needs what was in training; humans need richer context.

## Features used in this exercise (what, why, and caveats)

Stage **02** builds one row per claim; stage **04** trains on every column except identifiers, time-split keys, TPA timestamp, and label fields (see `DROP_COLS` in `04_train_backtest.py`).

### Eligibility-oriented raw fields (`claim_fact`)

| Field | Role |
|-------|------|
| **`payer_category`** | Coarse payer / program bucket (commercial, MCO, Medicaid FFS, Medicare, self-pay)—for attribution and carve-out stories. |
| **`medicaid_carve_out_indicator`** | Synthetic **0/1** proxy where Medicaid / MCO rows may carry carve-out context relevant to **duplicate-discount-style** tension (not “two claims”). |
| **`patient_ce_linkage_tier`** | Documentation strength proxy: `documented_visit`, `referral_only`, `incomplete_chart` (patient–CE relationship / chart evidence). |
| **`dispense_site_role`** | Where dispensing sits vs the CE program: `contract_pharmacy`, `hospital_outpatient_rx`, `mail_order`, `child_site_dispense`. |
| **`on_ce_formulary_flag`** | Coarse **program formulary** fit (synthetic). |
| **`covered_drug_bucket`** | `standard`, `maintenance_tier`, `specialty_tier` (mapped from `drug_class`). |

### Dispensing context (supporting)

| Field | Role |
|-------|------|
| **`days_supply`**, **`quantity`**, **`fill_number`** | Utilization / therapy pattern; feeds **dispense-pattern** rules only. |
| **`is_contract_pharmacy`**, **`pharmacy_volume_band`** | 340B pharmacy context; `pharmacy_id` kept in Parquet for rules but **not** in `X`. |

### Rule-based scores ([`_rule_features.py`](src/gb-340b/_rule_features.py), computed in stage 02)

| Feature | Meaning |
|---------|---------|
| **`duplicate_discount_risk_score`** | **Primary policy-style proxy:** Medicaid/MCO + carve-out + contract pharmacy, weak patient linkage, etc. (see docstring in code). |
| **`dispense_pattern_risk_score`** | **Secondary:** refill overlap, same-day multi-pharmacy, quantity vs days’ supply (PBM-style edits). |

### Member history (derived in 02)

| Feature | Definition |
|---------|------------|
| **`member_prior_fills_same_drug_365d`** | Prior fills same member + `drug_class` in 365 days before this claim. |
| **`days_since_prior_fill_same_drug`** | Clipped / sentinel-mapped for stability (see code). |
| **`member_prior_claims_90d`** / **`member_prior_amount_90d`** | Any-drug counts / amounts in prior 90 days. |
| **`months_since_panel_start`** | Low-cardinality calendar index from first `claim_month`. |

### Other model inputs

| Feature | Notes |
|---------|--------|
| **`drug_class`**, **`channel`**, **`claim_amount`** | Same broad intent as before; real systems use NDC/GPI and allowed amounts. |
| **`tpa_eligible`** | TPA outcome as context only. |
| **`service_date`** | **Dropped before training**; time splits use `claim_month`. |

**Explicitly not fed to the model:** `claim_id`, `member_id`, `pharmacy_id`, `service_date`, `asof_date`, `claim_month`, `determination_date`, and label columns except the target in training.

## What else to consider for an effective model / result

See [Toward real data and production use](#toward-real-data-and-production-use). Additionally: align **labels** with your **written CE review policy** (what counts as a “finding” for eligibility confirmation), and add **real** payer / carve-out / NDC / site attributes only with clear **as-of** rules and governance.

## What you see after a run (and where)

Open `artifacts/run_report.md` and `artifacts/metrics.json` together.

| Output | What it tells you |
|--------|-------------------|
| Row counts (`claim_fact` vs `training_snapshots`) | Training uses **only claims with a completed CE review** in the label window. |
| `test_positive_rate` | Share of **`eligibility_confirmation_finding`** in the held-out slice. |
| `precision_at_top_10pct` vs `random_precision_at_top_10pct_mean` | **Main operational read** under fixed review budget. |
| `p_eligibility_confirmation_finding` min/max/mean | Spread of predicted risk on the **latest scored month**. |
| `risk_category` | Relative quantile buckets within that month. |

## Why it looks that way

- **Review-only labels:** Selection into CE review shapes the training distribution.
- **Time-based split:** Honest vs random split.
- **No leakage:** Features are **as of** service; review completion after anchor; stage 03 applies an audit-completion cutoff.
- **Synthetic link:** Findings are driven by **eligibility-themed** fields plus noise; real programs differ.

## Toward real data and production use

Use this repo as a **pattern**, not a plug-in model.

1. **Define the label with stakeholders** — What counts as an eligibility-confirmation **finding** for your CE program?
2. **Audit the sampling process** — How do claims enter independent review?
3. **Governance** — TPA determination remains authoritative unless your organization changes process.
4. **Backtest honestly, then validate prospectively** — Shadow / champion-challenger.
5. **Monitor and refresh** — Drift in payer mix, formulary, or audit criteria.
6. **Calibration** — If probabilities drive thresholds.
7. **Fairness and constraints** — Sites, drugs, member segments.
8. **Lineage** — Version data, features, model, and slotting policy.

None of this replaces legal, privacy, or 340B program counsel.

## Run end-to-end

```bash
uv sync --package gb-340b
uv run --directory src/gb-340b python run_pipeline.py --n-claims 12000 --n-months 42 --seed 0
```

## Run stages individually

```bash
uv run --directory src/gb-340b python 01_extract_raw.py --n-claims 12000 --n-months 42 --seed 0 --start 2021-01
uv run --directory src/gb-340b python 02_build_features_sql_style.py
uv run --directory src/gb-340b python 03_build_labels_sql_style.py
uv run --directory src/gb-340b python 04_train_backtest.py --seed 0
uv run --directory src/gb-340b python 05_score_new_period.py
uv run --directory src/gb-340b python 06_report_run.py
```

## Artifacts

- `src/gb-340b/data/stage/*.parquet` — stage contracts (raw + features + training cohort)
- `src/gb-340b/artifacts/model.joblib`
- `src/gb-340b/artifacts/metrics.json`
- `src/gb-340b/artifacts/run_report.md`
- `src/gb-340b/data/output/scored_claims.parquet` (includes `p_eligibility_confirmation_finding`)

## Stage contracts

| Stage | Reads | Writes |
|-------|--------|--------|
| 01 | — | `claim_fact`, `tpa_determination`, `ce_audit_outcomes` (`eligibility_confirmation_finding`) |
| 02 | 01 | `features_asof` (rules + aggregates; no audit outcomes) |
| 03 | 02 + `ce_audit_outcomes` | `training_snapshots` (reviewed claims only; completion before cutoff) |
| 04 | `training_snapshots` | `model.joblib`, `metrics.json` |
| 05 | `features_asof` + model | `scored_claims` (latest `claim_month`) |
| 06 | stage + output + metrics | `run_report.md` |

## Mapping to a real warehouse (illustrative)

| Synthetic table | Typical source |
|-----------------|----------------|
| `claim_fact` | Claim/line: payer, benefit, carve-out flags, site/pharmacy, NDC, days supply, amount, contract pharmacy indicators |
| `tpa_determination` | TPA adjudication outcome (already applied) |
| `ce_audit_outcomes` | CE review workflow: completed review date, **eligibility confirmation** outcome |
