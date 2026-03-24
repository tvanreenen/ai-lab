from __future__ import annotations

import argparse
import json

import joblib
import numpy as np
import pandas as pd
from _common import get_paths, log_stage
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

DROP_COLS = ("account_id", "snapshot_month", "churn_90d")


def time_split(df: pd.DataFrame, train_frac: float = 0.7, val_frac: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    months = np.sort(df["snapshot_month"].unique())
    n = len(months)
    i_train = max(1, int(train_frac * n))
    i_val = max(i_train + 1, int((train_frac + val_frac) * n))
    i_val = min(i_val, n - 1)
    train = df[df["snapshot_month"].isin(months[:i_train])].copy()
    val = df[df["snapshot_month"].isin(months[i_train:i_val])].copy()
    test = df[df["snapshot_month"].isin(months[i_val:])].copy()
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
    train_df, val_df, test_df = time_split(df)

    X_train = train_df.drop(columns=list(DROP_COLS))
    y_train = train_df["churn_90d"].astype(int)
    X_val = val_df.drop(columns=list(DROP_COLS))
    y_val = val_df["churn_90d"].astype(int)
    X_test = test_df.drop(columns=list(DROP_COLS))
    y_test = test_df["churn_90d"].astype(int)

    pre = preprocess_fit(X_train)
    X_train_t = pre.fit_transform(X_train)
    X_val_t = pre.transform(X_val)
    X_test_t = pre.transform(X_test)

    model = XGBClassifier(
        n_estimators=2000,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=2,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="binary:logistic",
        eval_metric="aucpr",
        random_state=args.seed,
        n_jobs=-1,
        early_stopping_rounds=80,
    )
    model.fit(X_train_t, y_train, eval_set=[(X_val_t, y_val)], verbose=False)
    proba_test = model.predict_proba(X_test_t)[:, 1]
    topk = max(1, int(0.1 * len(y_test)))
    top_idx = np.argsort(proba_test)[-topk:]

    metrics = {
        "rows_train": int(len(train_df)),
        "rows_val": int(len(val_df)),
        "rows_test": int(len(test_df)),
        "test_churn_rate": float(y_test.mean()),
        "roc_auc_test": float(roc_auc_score(y_test, proba_test)),
        "pr_auc_test": float(average_precision_score(y_test, proba_test)),
        "precision_at_top_10pct": float(np.mean(y_test.to_numpy()[top_idx])),
        "best_iteration": int(model.best_iteration),
    }

    model_artifact = {
        "preprocessor": pre,
        "model": model,
        "feature_columns": X_train.columns.tolist(),
    }
    joblib.dump(model_artifact, paths.artifacts / "model.joblib")
    (paths.artifacts / "metrics.json").write_text(json.dumps(metrics, indent=2))

    log_stage("04_train_backtest", **{k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()})


if __name__ == "__main__":
    main()
