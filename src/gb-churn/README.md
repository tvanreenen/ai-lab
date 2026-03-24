# gb-churn staged churn pipeline (synthetic, SQL-style)

`gb-churn` is a process-first simulation of a real churn ML workflow:

1. extract raw source-like tables
2. build as-of aggregates (SQL-style CTE flow)
3. build forward-horizon labels
4. train backtest model
5. score newest period with probability + risk category
6. generate a run summary report

All stage handoffs are Parquet in `data/stage/`.

## What this exercise teaches

This project is intentionally structured as a miniature production workflow:

- **Stages 1-3 (data engineering):** ingest raw source-like tables, build as-of aggregates, and attach forward labels without leakage.
- **Stage 4 (modeling):** train and backtest with a chronological split.
- **Stage 5 (operations):** score the newest period with both probability and risk category outputs.
- **Stage 6 (monitoring):** summarize run health, quality, and workload in one report.

The main educational goal is process clarity: understand each handoff and decision point you would keep when moving to real data.

## Quick start

From repository root:

```bash
uv sync --package gb-churn
uv run --directory src/gb-churn python run_pipeline.py --n-accounts 2500 --n-months 30 --seed 0
```

Outputs:

- `src/gb-churn/data/stage/*.parquet` (intermediate contracts)
- `src/gb-churn/artifacts/model.joblib`
- `src/gb-churn/artifacts/metrics.json`
- `src/gb-churn/artifacts/run_report.md`
- `src/gb-churn/data/output/scored_accounts.parquet`

## Stage-by-stage commands

```bash
uv run --directory src/gb-churn python 01_extract_raw.py --n-accounts 2500 --n-months 30 --seed 0 --start 2022-01
uv run --directory src/gb-churn python 02_build_features_sql_style.py
uv run --directory src/gb-churn python 03_build_labels_sql_style.py
uv run --directory src/gb-churn python 04_train_backtest.py --seed 0
uv run --directory src/gb-churn python 05_score_new_period.py
uv run --directory src/gb-churn python 06_report_run.py
```

## Stage contracts

### `01_extract_raw.py`
**Purpose:** Simulate upstream source systems you would normally query from a warehouse.

**Inputs:** none (seed + generation params).

**Core transforms:**
- Create account dimension table (firmographics + static attributes).
- Simulate daily product activity events.
- Simulate support tickets and monthly contract states.
- Emit churn events as a forward outcome stream.

**Outputs:**

- `account_dim.parquet`
- `usage_daily.parquet`
- `support_tickets.parquet`
- `contract_monthly.parquet`
- `churn_events.parquet`

**Success checks:**
- Row counts scale with `--n-accounts` and `--n-months`.
- Date ranges span the requested simulation window.

### `02_build_features_sql_style.py`
**Purpose:** Convert raw events into account-month as-of features (the model-ready snapshot grain).

**Inputs:** stage raw tables from `01_extract_raw.py`.

**Core transforms (SQL-style CTE flow):**
- Monthly usage aggregates and prior-period trend.
- Ticket volume / severity windows.
- Join to contract and account static attributes.
- Construct canonical keys (`account_id`, `snapshot_month`, `month_index`, `tenure_months`).

**Outputs:**

- `features_asof.parquet`

Each row is one account + snapshot month with only as-of features.

**Success checks:**
- No duplicate `account_id + snapshot_month`.
- Snapshot month coverage matches contract/activity coverage.

### `03_build_labels_sql_style.py`
**Purpose:** Build supervised labels using only future outcomes relative to each snapshot.

**Inputs:**
- `features_asof.parquet`
- `churn_events.parquet`

**Core transforms:**
- Forward join each snapshot with churn events in `(snapshot_month, snapshot_month + 90 days]`.
- Set `churn_90d`.
- Drop horizon-edge rows where a full forward window is unavailable.

**Outputs:**

- `training_snapshots.parquet`

`churn_90d = 1` if churn occurs in the next 90 days after snapshot.

**Success checks:**
- Positive labels exist and are not extreme.
- Label logic uses post-snapshot outcomes only (no leakage).

### `04_train_backtest.py`
**Purpose:** Train a baseline model and evaluate out-of-time generalization.

**Inputs:** `training_snapshots.parquet`.

**Core transforms:**
- Chronological split (`train -> val -> test`).
- Fit preprocessing and XGBoost baseline.
- Compute ROC-AUC, PR-AUC, precision@top10, and best iteration.

**Outputs:**

- `artifacts/model.joblib`
- `artifacts/metrics.json`

**Success checks:**
- Train/val/test row counts are non-empty and chronological.
- Metrics are finite and consistent with run report.

### `05_score_new_period.py`
**Purpose:** Simulate production scoring on the newest ingestion period.

**Inputs:**
- `features_asof.parquet`
- `artifacts/model.joblib`

**Core transforms:**
- Select latest `snapshot_month`.
- Apply preprocessing + model inference.
- Assign risk categories from score bands.

**Outputs:**

- `data/output/scored_accounts.parquet`

Contains:
- `p_churn_90d` (probability)
- `risk_category` (`high`, `medium`, `low`) by score quantiles

**Success checks:**
- Every scored row has both probability and category.
- Risk-band counts align with expected operational capacity.

### `06_report_run.py`
**Purpose:** Provide one diagnostic artifact summarizing the full run.

**Inputs:**
- Stage row-count artifacts
- `artifacts/metrics.json`
- `data/output/scored_accounts.parquet`

**Core transforms:**
- Collect row counts by stage.
- Pull backtest metrics.
- Summarize latest score/risk distribution.

**Outputs:**

- `artifacts/run_report.md`

Includes stage row counts, backtest metrics, and latest scoring distribution.

**Success checks:**
- Report renders with non-empty sections.
- Numbers match stage artifacts and metrics file.

## How to interpret `artifacts/run_report.md`

Read it in four passes:

1. **Pipeline health (row counts)**
   - Check stage counts are in expected ranges run-to-run.
   - Sudden drops/spikes usually mean extraction/aggregation changed, not model quality.
   - `training_snapshots` should be slightly smaller than `features_asof` because of label horizon cutoff.

2. **Model quality (backtest metrics)**
   - `test_churn_rate` is your base rate.
   - `pr_auc_test` should be meaningfully above base rate to indicate useful ranking signal.
   - `precision_at_top_10pct` should also beat base rate if top-decile prioritization is useful.
   - `best_iteration` shifts can hint at changed data complexity/drift.

3. **Operational workload (latest scoring distribution)**
   - `high_count`, `medium_count`, `low_count` determine team workload by risk band.
   - Confirm high-risk volume is feasible for intervention capacity.

4. **Score distribution sanity**
   - `p_churn_min/max/mean` catches degenerate outputs (all near same value, or extreme collapse).

Quick checklist per run:

- **Green:** stable row counts, PR-AUC and precision@top10 above base rate, manageable high-risk volume.
- **Yellow:** small metric regressions or distribution shifts; monitor next run.
- **Red:** sharp row-count anomalies, PR-AUC near base rate, or unusable high-risk volume.

Store each `run_report.md` as a dated artifact when iterating so drift and regressions are obvious.

## Analysis of current results (this simulation)

Based on the current `artifacts/metrics.json` and `artifacts/run_report.md`:

- `test_churn_rate`: `0.1347`
- `roc_auc_test`: `0.5497`
- `pr_auc_test`: `0.1734`
- `precision_at_top_10pct`: `0.2247`
- `best_iteration`: `12`
- Score range on latest period: `0.1003` to `0.2484` (mean `0.1455`)

What this says:

- The model has **modest ranking signal** (better than random, but not strong).
- PR-AUC and precision@top10 are above base rate, so there is some lift for prioritization.
- Early stopping at 12 trees and a narrow score range suggest limited separability in this synthetic setup.

Why this happens here:

- The synthetic pipeline intentionally includes noise and overlap between churn/non-churn behavior.
- Feature windows and forward label horizon are realistic enough that the task is not trivially separable.
- This is useful for process training: it teaches handling weak-to-medium signal, not just easy demos.

## What to do when it behaves like this (real-world playbook)

When metrics look similar on real data, use this order of operations:

1. **Recheck prediction contract**
   - Confirm entity, snapshot timing, and label horizon match the operational question.

2. **Audit leakage and as-of correctness**
   - Ensure every feature is computed using data available at snapshot time only.

3. **Audit data quality and coverage**
   - Missingness by segment/time, stale feeds, join drops, and schema drift.

4. **Segment diagnostics**
   - Evaluate by key cohorts (region, size, industry, plan); weak global signal often hides strong segment signal.

5. **Feature iteration before model complexity**
   - Add better behavior and momentum features before jumping to more complex models.

6. **Optimize for operational lift**
   - Use precision/recall at actionable bands (top 5/10/20%) and capacity-based thresholds.

7. **Track stability**
   - Compare run reports over time (not single-run outcomes) for drift and regressions.

Bottom line: once problem definition, leakage controls, and data quality checks are solid, weak model performance is usually a **signal problem**. In practice that means improving feature quality and adding the right source inputs (not only trying more complex models).

## How this maps to real data

Replace only stage 01 with real extraction queries (warehouse tables/API pulls). Keep stages 02-05 unchanged as much as possible. This preserves:

- feature definitions,
- anti-leakage labeling logic,
- evaluation strategy,
- scoring outputs used by downstream operations.

## Sanity checks after a run

- `training_snapshots.parquet` has non-empty `churn_90d` positives.
- train/val/test are chronological in `04_train_backtest.py`.
- `scored_accounts.parquet` includes both `p_churn_90d` and `risk_category`.
