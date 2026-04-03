from __future__ import annotations

import argparse
from pathlib import Path

from .models import CompactionConfig
from .repl import run_repl
from .session import CompactedSession


DEFAULT_MODEL = "openai:gpt-5.2"
DEFAULT_DEMO_CONTEXT_WINDOW = 4_000


def main() -> None:
    args = parse_args()
    state_root = args.state_root.resolve()
    config = CompactionConfig(context_window=args.context_window)
    session = CompactedSession.create(
        state_root=state_root,
        model=args.model,
        summary_model=args.summary_model,
        config=config,
    )
    session.set_recovery_notifier(lambda message: print(f"\n{message}"))
    try:
        run_repl(session=session, state_root=state_root)
    finally:
        session.close()


def parse_args() -> argparse.Namespace:
    package_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Run the standalone Pydantic AI history compaction REPL.",
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=package_root / "state",
        help="Directory used for the append-only raw history and collapse state.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Pydantic AI model string used for the main conversation agent.",
    )
    parser.add_argument(
        "--summary-model",
        default=None,
        help="Optional model override for the background summarizer agent.",
    )
    parser.add_argument(
        "--context-window",
        type=int,
        default=DEFAULT_DEMO_CONTEXT_WINDOW,
        help=(
            "Estimated context window used for compaction thresholds in the demo. "
            "Defaults lower than the library default so collapse is easier to trigger."
        ),
    )
    return parser.parse_args()
