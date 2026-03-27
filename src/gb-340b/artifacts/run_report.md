# gb-340b run summary (eligibility confirmation prioritization)

- generated_at_utc: `2026-03-26T22:34:23.795722+00:00`

## Stage row counts

- claim_fact: `50000`
- tpa_determination: `50000`
- ce_audit_outcomes: `13018`
- features_asof: `50000`
- training_snapshots: `12867`
- scored_claims: `1205`

## Backtest metrics

- rows_train: `8932`
- rows_val: `1832`
- rows_test: `2103`
- test_positive_rate: `0.2934`
- roc_auc_test: `0.6521`
- pr_auc_test: `0.4462`
- brier_test: `0.1939`
- log_loss_test: `0.5740`
- precision_at_top_10pct: `0.5571`
- recall_at_top_10pct: `0.1896`
- random_precision_at_top_10pct_mean: `0.2928`
- lift_vs_random_mean_at_top_10pct: `1.9031`
- lift_vs_prevalence_at_top_10pct: `1.8990`
- best_iteration: `72`

## Budget metrics (test slice)

- top_1pct: precision `0.6667`, recall `0.0227`, lift_vs_prevalence `2.27`
- top_5pct: precision `0.5619`, recall `0.0956`, lift_vs_prevalence `1.92`
- top_10pct: precision `0.5571`, recall `0.1896`, lift_vs_prevalence `1.90`
- top_20pct: precision `0.4881`, recall `0.3323`, lift_vs_prevalence `1.66`
- top_30pct: precision `0.4429`, recall `0.4522`, lift_vs_prevalence `1.51`

## Latest scoring distribution

- latest_claim_month: `2024-06-30`
- high_count: `121`
- medium_count: `241`
- low_count: `843`
- p_eligibility_confirmation_finding_min: `0.1401`
- p_eligibility_confirmation_finding_max: `0.6907`
- p_eligibility_confirmation_finding_mean: `0.2762`
