from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from _common import log_stage


def run(script: Path, *args: str) -> None:
    cmd = [sys.executable, str(script), *args]
    log_stage("run_pipeline", step=script.name)
    subprocess.run(cmd, check=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Run gb-churn full staged pipeline")
    p.add_argument("--n-accounts", type=int, default=2500)
    p.add_argument("--n-months", type=int, default=30)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--start", type=str, default="2022-01")
    args = p.parse_args()

    root = Path(__file__).resolve().parent
    run(root / "01_extract_raw.py", "--n-accounts", str(args.n_accounts), "--n-months", str(args.n_months), "--seed", str(args.seed), "--start", args.start)
    run(root / "02_build_features_sql_style.py")
    run(root / "03_build_labels_sql_style.py")
    run(root / "04_train_backtest.py", "--seed", str(args.seed))
    run(root / "05_score_new_period.py")
    run(root / "06_report_run.py")
    log_stage("run_pipeline", status="complete")


if __name__ == "__main__":
    main()
