# gb-340b — CE contract pharmacy eligibility-confirmation prioritization

Help **covered entities (CEs)** manage their **contract pharmacy program** more effectively: not by replacing TPA eligibility determinations, but by **ranking claims for independent review** where audits are most likely to find documentation, linkage, site, or payer issues—under limited capacity.

**Disclaimer:** Synthetic data and educational example only — not legal, compliance, or clinical advice.

---

## Do / don't

| Do | Don't |
| --- | --- |
| Rank claims for **human** eligibility-confirmation review | Replace TPA adjudication or HRSA policy |
| Learn from **past audit outcomes** | Guarantee a legal or compliance outcome |
| Use **explainable** claim context + derived fields | Treat utilization alone as "proof" of 340B eligibility |

---

## Flow and source data

| Step | What | Source |
| --- | --- | --- |
| 1. Claim detail | `claim_fact` — payer, site, drug, fill economics | Claims / pharmacy system |
| | `ce_linkage_evidence` — encounter, prescriber, patient panel, referral, site status | Encounter feed, CE-shared rosters/panels, claims workflow, HRSA site data |
| 2. TPA + audits | `tpa_determination` — our eligibility outcome | TPA adjudication (already applied) |
| | `ce_audit_outcomes` — audit labels for training | CE review workflow |
| 3. Features | Derived eligibility-confirmation fields + history rollups | Computed from steps 1–2 |
| 4. Score | Probability + high / medium / low tier → work queue | Model output |

---

## 1) Source data (illustrative)

### `claim_fact`

| claim_id | member_id | service_date | payer_category | medicaid_carve_out | dispense_site_role | on_ce_formulary_flag | drug_class | days_supply | quantity | claim_amount |
| --- | --- | --- | --- | ---: | --- | ---: | --- | ---: | ---: | ---: |
| 11842 | 9001 | 2024-06-11 | mco | 1 | contract_pharmacy | 0 | specialty | 30 | 90.00 | 415.20 |
| 11501 | 1120 | 2024-06-07 | commercial | 0 | hospital_outpatient_rx | 1 | maintenance | 90 | 90.00 | 82.10 |
| 11990 | 5522 | 2024-06-14 | medicaid_ffs | 1 | contract_pharmacy | 1 | oncology | 28 | 30.00 | 1902.44 |

Payer, site, formulary fit, drug, fill economics.

### `ce_linkage_evidence`

| claim_id | encounter_match | encounter_in_window | prescriber_on_ce_roster | patient_on_ce_panel | referral_present | dispensing_site_active_340b |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 11842 | 0 | 0 | 0 | 0 | 1 | 1 |
| 11501 | 1 | 1 | 1 | 1 | 0 | 1 |
| 11990 | 0 | 0 | 0 | 0 | 1 | 1 |

Patient–CE relationship evidence from sources available to us as TPA: encounter feed (match and timing window), prescriber affiliation (NPI vs CE provider roster), patient panel match (CE-shared registered patient list), referral/order presence (claims workflow), and dispensing site 340B status at service date (HRSA database / CE contract records).

Deeper CE EHR integration (e.g. chart completeness, clinical context) would unlock additional signal but is not required for a baseline model.

---

## 2) TPA determination + CE audit labels

**TPA** (model input, not the training target)

| claim_id | determination_date | tpa_eligible |
| --- | --- | --- |
| 11842 | 2024-06-12 | 1 |
| 11501 | 2024-06-08 | 1 |
| 11990 | 2024-06-15 | 1 |

**CE audit outcomes** (training labels — from completed audits only)

| claim_id | audit_complete_date | eligibility_confirmation_finding |
| --- | --- | --- |
| 10410 | 2024-04-30 | 1 |
| 10477 | 2024-04-30 | 0 |
| 10521 | 2024-05-02 | 1 |

The label `eligibility_confirmation_finding` means "did the CE audit record a finding on eligibility confirmation?" — defined with CE stakeholders and audit policy.

---

## 3) Features (one pool per claim)

We compute one feature row per claim. The demo prioritizes **eligibility-confirmation–oriented** derived fields; the pipeline may also include optional composite or operational scores for experimentation.

### Primary derived features

| Feature | Source / how computed |
| --- | --- |
| `patient_ce_linkage_tier` | From encounter, prescriber roster, patient panel, and referral evidence (`documented_visit` / `referral_only` / `incomplete`). |
| `dispensing_site_active_340b` | Was the dispensing site in active 340B status at service date? (HRSA / CE contract records.) |
| `on_ce_formulary_fit` | Program formulary / drug-in-scope (from NDC or drug rules as of service date). |
| `contract_pharmacy_site` | Whether dispense aligns with contract pharmacy program context. |
| `payer_carve_context` | Payer + carve-out tension flag (e.g. Medicaid/MCO with carve-out present). |

### History / context rollups

These help the model learn **where audits tend to find issues** — they don't determine eligibility on their own.

| Feature | Role |
| --- | --- |
| `member_prior_fills_same_drug_365d` | Prior fills for same drug class in 365 days. Unusual patterns may flag documentation review needs. |
| `days_since_prior_fill_same_drug` | Gap since last same-drug fill. Very short gaps can signal overlapping therapy or re-dispense without new encounter evidence. |
| `member_prior_claims_90d` | Recent claim count — activity concentration. |
| `member_prior_amount_90d` | Recent dollar amount — higher-stakes claims may warrant earlier review. |
| `ce_program_tenure_months` | How long the member/site relationship has been in the CE program. Newer relationships may have weaker documentation. |
| `prior_finding_rate_by_segment` | Historical audit finding rate for similar claims (payer × site × drug bucket). Directly predictive of where audits surface issues. |

### Illustrative feature row (claim 11842)

Section 1 claim columns ride on the same row in the pipeline; only derived + rollup columns shown here.

| claim_id | patient_ce_linkage_tier | dispensing_site_active_340b | on_ce_formulary_fit | contract_pharmacy_site | payer_carve_context | member_prior_fills_same_drug_365d | days_since_prior_fill_same_drug | member_prior_claims_90d | member_prior_amount_90d | ce_program_tenure_months | prior_finding_rate_by_segment |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 11842 | incomplete | 1 | 0 | 1 | 1 | 4 | 45 | 7 | 3240.19 | 14 | 0.31 |

### Other ideas to consider

| Idea | Notes |
| --- | --- |
| Weighted composite scores (e.g. `duplicate_discount_risk_score`) | Hand-weighted policy proxies combining payer/carve-out/linkage signals into one number. Can encode SME priors early; validate against labeled outcomes before relying on them. |
| Dispense-pattern signals (e.g. refill overlap, multi-pharmacy, quantity spikes) | More operational / PBM-adjacent. Useful as secondary tie-breakers; avoid over-weighting in the eligibility-confirmation story. |
| Deeper EHR-derived features (chart completeness, diagnosis context) | Requires CE EHR integration. Strong signal if available; not required for baseline. |
| Calibrated probability thresholds | Move `risk_category` from quantile-based tiers to calibrated cut points after enough labeled data. |
| Multi-target scoring | Score `finding_severity` or `expected_financial_impact` alongside the binary finding probability for richer prioritization. |
| Richer backtest reporting | Precision/recall at multiple budget levels (top 5%, 10%, 20%, 30%), yield curves ("review 100 claims → expect X findings"), segment-level precision (by payer, site, drug bucket), calibration plots, and score stability across months. |

**Not fed to the model:** `claim_id`, `member_id`, `pharmacy_id`, `service_date`, `asof_date`, `claim_month`, `determination_date`, and label columns.

---

## 4) Scored queue

| claim_id | claim_month | p_eligibility_confirmation_finding | risk_category |
| --- | --- | ---: | --- |
| 11842 | 2024-06-30 | 0.71 | high |
| 11501 | 2024-06-30 | 0.54 | high |
| 11990 | 2024-06-30 | 0.41 | medium |
| 11703 | 2024-06-30 | 0.18 | low |

- `p_eligibility_confirmation_finding` = estimated P(finding if audited).
- `risk_category` = relative within-month tier (top ~10% = high, next ~20% = medium, rest = low).
- **Use:** sort desc., take top *k* for this week's capacity, keep a random slice across all tiers for QC.

---

## Understanding the artifacts

### `scored_claims.parquet`

**What:** One row per claim in the latest month, ranked by predicted audit-finding probability.

| Column | Meaning |
| --- | --- |
| `claim_id` | Join key back to source claim detail. |
| `claim_month` | Which month cohort was scored. |
| `p_eligibility_confirmation_finding` | Estimated probability (0–1) of a positive finding if audited. |
| `risk_category` | `high` / `medium` / `low` — relative tier for triage. |

**Why:** This is the work queue.  
**Read:** Higher probability = more likely to surface an issue. Tier is a convenience label; probability is the primary signal.

### `metrics.json`

**What:** Machine-readable backtest results from the held-out test period.

| Metric | What it tells you |
| --- | --- |
| `rows_train` / `rows_val` / `rows_test` | How data was split across time periods. |
| `test_positive_rate` | Baseline finding rate ("if you picked at random"). |
| `roc_auc_test` | Overall ranking quality (0.5 = random, 1.0 = perfect). |
| `pr_auc_test` | Precision-recall summary — more relevant when findings are uncommon. |
| `brier_test` | Mean squared error of predicted probabilities (lower = better calibrated). |
| `log_loss_test` | Proper scoring rule that penalizes overconfident wrong predictions (lower = better). |
| `precision_at_top_10pct` | **Key metric.** Share of actual findings in the model's top 10%. |
| `recall_at_top_10pct` | Of all actual findings, what share did the model's top 10% capture? |
| `random_precision_at_top_10pct_mean` | Same budget, random pick — the "do nothing" baseline. |
| `lift_vs_random_mean_at_top_10pct` | How many times better the model is vs random. >1 = adds value; >1.5 is a good signal. |
| `lift_vs_prevalence_at_top_10pct` | Model's top 10% vs overall finding rate. |
| `best_iteration` | When training stopped (early stopping). Lower = simpler model. |

**Budget metrics** (`budget_metrics_pct`): precision, recall, and lift at **1%, 5%, 10%, 20%, 30%** of the test set. Shows how model performance degrades as you widen review capacity — essential for capacity planning.

**Calibration by decile** (`calibration_by_decile`): for each score decile, the average predicted probability (`p_mean`) vs the actual finding rate (`y_rate`). If these track closely, the probabilities are trustworthy for threshold-based routing. Large gaps mean probabilities need recalibration.

**Why:** Answers "is the model doing better than random?", "how much better at different budgets?", and "can we trust the probabilities?"  
**Read:** Focus on `precision_at_top_10pct` vs `random_precision_at_top_10pct_mean`. Use budget metrics to match model performance to your actual review capacity. Check calibration if probabilities will drive hard routing rules.

### `run_report.md`

**What:** Human-readable summary: stage row counts, backtest metrics, latest scoring distribution.

| Section | What it tells you |
| --- | --- |
| Stage row counts | How many claims flowed through each stage. Spot data drops or pipeline issues. |
| Backtest metrics | Core metrics including Brier score, log loss, precision/recall at 10%, and lift. |
| Budget metrics (test slice) | Precision, recall, and lift at 1% / 5% / 10% / 20% / 30% — match to your actual review capacity. |
| Latest scoring distribution | Scored month, tier counts (high / medium / low), score min / max / mean. |

**Why:** Quick "did this run look sane?" check.  
**Read:** Scan row counts for drops. Check precision > random. Use budget metrics to see how performance changes at different review volumes. If score min ≈ max, the model isn't differentiating.

### `model.joblib`

**What:** Serialized bundle: trained XGBoost classifier, preprocessing pipeline (imputer + encoder), feature column list.  
**Why:** Loaded by stage 05 to score new claims; versioned record of what was trained.  
**Read:** Not opened directly. Track alongside run date, seed, training data version, and `metrics.json` for governance.

---

## Labels and ongoing upkeep

Model quality depends on **labeled audits** (`eligibility_confirmation_finding`) from CE workflows or client-sampled reviews, aligned to a clear "finding" definition.

Ongoing work:

- Define the label with stakeholders — what counts as a finding for your CE program?
- Audit the sampling process — how do claims enter independent review?
- Backtest honestly, then validate prospectively (shadow / champion-challenger).
- Monitor drift in payer mix, formulary, audit criteria; retrain on cadence.
- Governance: TPA determination remains authoritative; version data, features, model, and thresholds.

---

## Why results look the way they do

- **Review-only labels:** Only audited claims have labels — selection shapes the distribution.
- **Time-based split:** Honest forward split, not random.
- **No leakage:** Features are as-of service date; audit completion comes after; stage 03 applies a cutoff.
- **Synthetic link:** Findings are driven by eligibility-themed fields plus noise; real programs will differ.

---

## Carrying this into production

- Add `model_version`, `scored_at`, `feature_snapshot_id` on each scored row.
- Decide if `risk_category` stays quantile-based or moves to calibrated probability cut points.
- Join `claim_id` to NDC, member, pharmacy, payer fields for the review UI.
- Calibrate if probabilities drive hard thresholds.
- Fairness: monitor across sites, drugs, member segments.

---

## Run

```bash
uv sync --package gb-340b
uv run --directory src/gb-340b python run_pipeline.py --n-claims 12000 --n-months 42 --seed 0
```

### Run stages individually

```bash
uv run --directory src/gb-340b python 01_extract_raw.py --n-claims 12000 --n-months 42 --seed 0 --start 2021-01
uv run --directory src/gb-340b python 02_build_features_sql_style.py
uv run --directory src/gb-340b python 03_build_labels_sql_style.py
uv run --directory src/gb-340b python 04_train_backtest.py --seed 0
uv run --directory src/gb-340b python 05_score_new_period.py
uv run --directory src/gb-340b python 06_report_run.py
```

---

## Stage contracts

| Stage | Reads | Writes |
| --- | --- | --- |
| 01 | — | `claim_fact`, `tpa_determination`, `ce_audit_outcomes` |
| 02 | 01 | `features_asof` (rules + aggregates; no audit outcomes) |
| 03 | 02 + `ce_audit_outcomes` | `training_snapshots` (reviewed claims only; completion before cutoff) |
| 04 | `training_snapshots` | `model.joblib`, `metrics.json` |
| 05 | `features_asof` + model | `scored_claims` (latest `claim_month`) |
| 06 | stage + output + metrics | `run_report.md` |
