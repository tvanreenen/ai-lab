# gb-340b run summary (eligibility confirmation prioritization)

- generated_at_utc: `2026-03-24T18:30:00.092506+00:00`

## Stage row counts

- claim_fact: `12000`
- tpa_determination: `12000`
- ce_audit_outcomes: `3046`
- features_asof: `12000`
- training_snapshots: `3004`
- scored_claims: `297`

## Backtest metrics

- rows_train: `2118`
- rows_val: `417`
- rows_test: `469`
- test_positive_rate: `0.2942`
- roc_auc_test: `0.6391`
- pr_auc_test: `0.4594`
- precision_at_top_10pct: `0.5652`
- random_precision_at_top_10pct_mean: `0.2889`
- lift_vs_random_mean_at_top_10pct: `1.9564`
- lift_vs_prevalence_at_top_10pct: `1.9209`
- best_iteration: `94`

## Latest scoring distribution

- latest_claim_month: `2024-06-30`
- high_count: `30`
- medium_count: `59`
- low_count: `208`
- p_eligibility_confirmation_finding_min: `0.1172`
- p_eligibility_confirmation_finding_max: `0.7341`
- p_eligibility_confirmation_finding_mean: `0.2858`
