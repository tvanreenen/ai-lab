from __future__ import annotations

import argparse
import os
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel

from _common import get_paths, load_repo_dotenv


INSTRUCTIONS = """You are helping a SaaS team evaluate a model for CE clients and their 340B contract pharmacy claims.

Constraints:
- This is prioritization for human review, not a legal/compliance determination.
- Do not overclaim; call out uncertainty and limits.
- Use plain language for business audiences with little ML/data science background.
- Return thoughtful markdown prose and bullets as helpful; do not force rigid sections.

Interpretation rules of thumb:
- Compare precision_at_top_10pct vs random_precision_at_top_10pct_mean and lift.
- Use budget metrics (top 1/5/10/20/30%) to give capacity guidance.
- Explain brier/log_loss as probability-quality signals, not pass/fail.
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Stage 07: assess run_report.md via OpenAI Responses API (pydantic-ai)")
    p.add_argument("--model", type=str, default="gpt-5.4", help="OpenAI model name (default: gpt-5.4)")
    p.add_argument(
        "--run-report",
        type=str,
        default="",
        help="Path to run_report.md",
    )
    p.add_argument(
        "--out",
        type=str,
        default="",
        help="Path to write assessment markdown",
    )
    p.add_argument(
        "--capacity-note",
        type=str,
        default="",
        help="Optional: e.g. 'We can review ~300 claims/week (~10% monthly)'.",
    )
    args = p.parse_args()

    load_repo_dotenv()

    paths = get_paths()
    report_path = Path(args.run_report) if args.run_report else (paths.artifacts / "run_report.md")
    out_path = Path(args.out) if args.out else (paths.artifacts / "run_report_assessment.md")
    report = report_path.read_text()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set. Export it before running stage 07 (pydantic-ai OpenAIResponsesModel).",
        )

    model = OpenAIResponsesModel(args.model)
    agent: Agent[None, str] = Agent(model, instructions=INSTRUCTIONS)

    user_prompt = (
        "Produce an open-ended markdown assessment for CE client-facing business users.\n"
        "Explain all key metrics in plain language, including how to interpret strengths, tradeoffs, and limitations.\n"
        "Assume the reader has minimal data science/ML background and is trying to build practical understanding.\n\n"
        "Optional capacity context:\n"
        f"{args.capacity_note or '(none provided)'}\n\n"
        "Run report:\n"
        f"{report}\n"
    )

    result = agent.run_sync(user_prompt)
    out_path.write_text(result.output.strip() + "\n")


if __name__ == "__main__":
    main()
