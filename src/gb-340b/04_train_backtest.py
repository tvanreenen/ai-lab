from __future__ import annotations

import argparse
import json

import joblib
import numpy as np
import pandas as pd
from _common import get_paths, log_stage
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

DROP_COLS = (
    "claim_id",
    "member_id",
    "pharmacy_id",
    "service_date",
    "asof_date",
    "claim_month",
    "eligibility_confirmation_finding",
    "audit_complete_date",
    "determination_date",
)


def time_split(df: pd.DataFrame, train_frac: float = 0.7, val_frac: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    months = np.sort(df["claim_month"].unique())
    n = len(months)
    i_train = max(1, int(train_frac * n))
    i_val = max(i_train + 1, int((train_frac + val_frac) * n))
    i_val = min(i_val, n - 1)
    train = df[df["claim_month"].isin(months[:i_train])].copy()
    val = df[df["claim_month"].isin(months[i_train:i_val])].copy()
    test = df[df["claim_month"].isin(months[i_val:])].copy()
    return train, val, test


def preprocess_fit(X_train: pd.DataFrame) -> ColumnTransformer:
    num_cols = X_train.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = X_train.select_dtypes(exclude=[np.number]).columns.tolist()
    return ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median"), num_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
        ],
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Stage 04: train backtest model")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()
    paths = get_paths()

    df = pd.read_parquet(paths.stage / "training_snapshots.parquet")
    df["claim_month"] = pd.to_datetime(df["claim_month"])
    train_df, val_df, test_df = time_split(df)

    X_train = train_df.drop(columns=list(DROP_COLS))
    y_train = train_df["eligibility_confirmation_finding"].astype(int)
    X_val = val_df.drop(columns=list(DROP_COLS))
    y_val = val_df["eligibility_confirmation_finding"].astype(int)
    X_test = test_df.drop(columns=list(DROP_COLS))
    y_test = test_df["eligibility_confirmation_finding"].astype(int)

    pre = preprocess_fit(X_train)
    X_train_t = pre.fit_transform(X_train)
    X_val_t = pre.transform(X_val)
    X_test_t = pre.transform(X_test)

    model = XGBClassifier(
        n_estimators=2000,
        learning_rate=0.03,
        max_depth=5,
        min_child_weight=1,
        subsample=0.9,
        colsample_bytree=0.85,
        objective="binary:logistic",
        eval_metric="auc",
        random_state=args.seed,
        n_jobs=-1,
        early_stopping_rounds=150,
    )
    model.fit(X_train_t, y_train, eval_set=[(X_val_t, y_val)], verbose=False)
    proba_test = model.predict_proba(X_test_t)[:, 1]
    y_arr = y_test.to_numpy()
    baseline_rate = float(y_test.mean()) if len(y_test) else 0.0

    def _topk_metrics(frac: float) -> dict[str, float]:
        k = max(1, int(frac * len(y_arr)))
        idx = np.argsort(proba_test)[-k:]
        precision = float(np.mean(y_arr[idx])) if k else float("nan")
        positives = float(np.sum(y_arr))
        recall = float(np.sum(y_arr[idx]) / positives) if positives > 0 else float("nan")
        lift_vs_prevalence = precision / baseline_rate if baseline_rate > 0 else float("nan")
        return {
            "k": float(k),
            "precision": precision,
            "recall": recall,
            "lift_vs_prevalence": lift_vs_prevalence,
        }

    budget_fracs = [0.01, 0.05, 0.10, 0.20, 0.30]
    budget_metrics = {str(int(f * 100)): _topk_metrics(f) for f in budget_fracs}

    # Keep random-vs-model comparison at 10% (existing behavior).
    topk = max(1, int(0.1 * len(y_test)))
    top_idx = np.argsort(proba_test)[-topk:]
    rng = np.random.default_rng(args.seed)
    random_trials = 400
    random_precisions = []
    for _ in range(random_trials):
        rand_idx = rng.choice(len(y_test), size=topk, replace=False)
        random_precisions.append(float(np.mean(y_arr[rand_idx])))
    random_precision_mean = float(np.mean(random_precisions))

    precision_topk = float(np.mean(y_arr[top_idx]))
    lift_vs_random_mean = (
        precision_topk / random_precision_mean if random_precision_mean > 0 else float("nan")
    )
    lift_vs_prevalence = precision_topk / baseline_rate if baseline_rate > 0 else float("nan")

    # Proper scoring rules / calibration-oriented metrics.
    brier = float(brier_score_loss(y_arr, proba_test)) if len(y_arr) else float("nan")
    ll = float(log_loss(y_arr, proba_test, labels=[0, 1])) if len(y_arr) else float("nan")

    # Simple reliability table by predicted-probability decile.
    cal = pd.DataFrame({"p": proba_test, "y": y_arr})
    try:
        cal["decile"] = pd.qcut(cal["p"], q=10, labels=False, duplicates="drop")
        calib_rows = []
        for d, g in cal.groupby("decile", sort=True):
            calib_rows.append(
                {
                    "decile": int(d),
                    "n": int(len(g)),
                    "p_mean": float(g["p"].mean()),
                    "y_rate": float(g["y"].mean()),
                },
            )
    except ValueError:
        # If qcut fails (e.g., too few unique probabilities), skip calibration table.
        calib_rows = []

    metrics = {
        "rows_train": int(len(train_df)),
        "rows_val": int(len(val_df)),
        "rows_test": int(len(test_df)),
        "test_positive_rate": baseline_rate,
        "roc_auc_test": float(roc_auc_score(y_test, proba_test)),
        "pr_auc_test": float(average_precision_score(y_test, proba_test)),
        "brier_test": brier,
        "log_loss_test": ll,
        "precision_at_top_10pct": precision_topk,
        "recall_at_top_10pct": budget_metrics["10"]["recall"],
        "random_precision_at_top_10pct_mean": random_precision_mean,
        "lift_vs_random_mean_at_top_10pct": lift_vs_random_mean,
        "lift_vs_prevalence_at_top_10pct": lift_vs_prevalence,
        "budget_metrics_pct": budget_metrics,
        "calibration_by_decile": calib_rows,
        "best_iteration": int(model.best_iteration),
    }

    model_artifact = {
        "preprocessor": pre,
        "model": model,
        "feature_columns": X_train.columns.tolist(),
    }
    joblib.dump(model_artifact, paths.artifacts / "model.joblib")
    (paths.artifacts / "metrics.json").write_text(json.dumps(metrics, indent=2))

    log_stage(
        "04_train_backtest",
        **{k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()},
    )


if __name__ == "__main__":
    main()
