from __future__ import annotations

import argparse
from pathlib import Path
import threading
from textwrap import dedent
from typing import Any

from .agents import build_consolidate_agent, build_extract_agent, build_main_agent
from .caps import truncate_entrypoint_content
from .consolidation_runner import ConsolidationJob, ConsolidationRunner
from .deps import MemoryDeps
from .extraction_runner import ExtractionJob, ExtractionRunner
from .memory_maintenance import (
    apply_post_consolidation_hygiene,
    apply_write_hygiene,
    audit_memory_store,
    format_audit_for_prompt,
    mark_consolidated,
    record_memory_activity,
    should_run_consolidation,
)
from .memory_scan import scan_memory_headers
from .memory_select import select_relevant_memories
from .memory_surface import surface_selected_memories
from .prompts import build_consolidation_prompt, build_extract_prompt
from .store import (
    diff_touched_paths,
    ensure_memory_layout,
    read_index,
    render_memory_tree,
    snapshot_memory_files,
)


DEFAULT_MODEL = "openai:gpt-5.2"


def main() -> None:
    args = parse_args()
    memory_root = args.memory_root.resolve()
    ensure_memory_layout(memory_root)

    if args.consolidate:
        run_consolidation_only(memory_root=memory_root, model=args.model)
        return

    run_repl(memory_root=memory_root, model=args.model)


def parse_args() -> argparse.Namespace:
    package_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Run the standalone Pydantic AI memory framework REPL.",
    )
    parser.add_argument(
        "--consolidate",
        action="store_true",
        help="Run only the consolidation agent against the current memory tree.",
    )
    parser.add_argument(
        "--memory-root",
        type=Path,
        default=package_root / "memory",
        help="Override the memory directory used by the framework.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Pydantic AI model string to use for all agents.",
    )
    return parser.parse_args()


def run_repl(*, memory_root: Path, model: str) -> None:
    print(f"Using model: {model}")
    print(f"Memory root: {memory_root}")
    print("Type your message and press Enter. Type 'quit' to exit.")

    main_agent = build_main_agent(model)
    extract_agent = build_extract_agent(model)
    consolidate_agent = build_consolidate_agent(model)
    message_history: list[Any] = []
    already_surfaced: set[str] = set()
    turn_number = 0
    maintenance_lock = threading.Lock()
    consolidation_runner = ConsolidationRunner(
        run_consolidation=lambda job: run_consolidation_pass(
            memory_root=job.memory_root,
            agent=consolidate_agent,
            maintenance_lock=maintenance_lock,
        ),
    )
    extraction_runner = ExtractionRunner(
        run_extraction=lambda job: run_extract_pass(
            job=job,
            extract_agent=extract_agent,
            consolidation_runner=consolidation_runner,
            maintenance_lock=maintenance_lock,
        ),
    )

    try:
        while True:
            try:
                user_text = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break

            if not user_text:
                continue
            if user_text.lower() in {"quit", "/quit"}:
                print("Exiting.")
                break

            assistant_text, new_messages = run_main_turn(
                user_text=user_text,
                memory_root=memory_root,
                model=model,
                main_agent=main_agent,
                message_history=message_history,
                already_surfaced=already_surfaced,
            )
            print(f"\nAssistant: {assistant_text}")

            turn_number += 1
            extraction_runner.submit(
                ExtractionJob(
                    turn_number=turn_number,
                    user_text=user_text,
                    assistant_text=assistant_text,
                    memory_root=memory_root,
                ),
            )
            message_history.extend(new_messages)
    finally:
        extraction_runner.close()
        consolidation_runner.close()


def run_consolidation_only(*, memory_root: Path, model: str) -> None:
    print(f"Using model: {model}")
    print(f"Memory root: {memory_root}")

    before = snapshot_memory_files(memory_root)
    agent = build_consolidate_agent(model)
    result = run_consolidation_pass(
        memory_root=memory_root,
        agent=agent,
        maintenance_lock=threading.Lock(),
    )
    after = snapshot_memory_files(memory_root)
    touched_paths = diff_touched_paths(before, after)

    print("\n=== Consolidation Summary ===")
    print(result)
    if touched_paths:
        print("Touched paths:")
        for path in touched_paths:
            print(f"- {path}")
    else:
        print("Touched paths: (none)")

    print("\n=== Final Memory Files ===")
    print(render_memory_tree(memory_root))


def run_main_turn(
    *,
    user_text: str,
    memory_root: Path,
    model: str,
    main_agent: Any,
    message_history: list[Any],
    already_surfaced: set[str],
) -> tuple[str, list[Any]]:
    index_snippet = truncate_entrypoint_content(read_index(memory_root)).content
    headers = scan_memory_headers(memory_root)
    selected_headers = select_relevant_memories(
        model=model,
        query=user_text,
        headers=headers,
        already_surfaced=already_surfaced,
    )
    selected_memories_text = surface_selected_memories(selected_headers)
    result = main_agent.run_sync(
        user_text,
        message_history=message_history,
        deps=MemoryDeps(
            memory_root=memory_root,
            index_snippet=index_snippet,
            selected_memories_text=selected_memories_text,
        ),
    )
    already_surfaced.update(header.filename for header in selected_headers)
    return result.output, list(result.new_messages())


def run_extract_pass(
    *,
    job: ExtractionJob,
    extract_agent: Any,
    consolidation_runner: ConsolidationRunner,
    maintenance_lock: threading.Lock,
) -> None:
    transcript = render_turn_transcript(
        user_text=job.user_text,
        assistant_text=job.assistant_text,
    )
    prompt = build_extract_prompt(
        turn_transcript=transcript,
        new_message_count=2,
        existing_memories_manifest=_format_existing_memories_manifest(job.memory_root),
    )
    before = snapshot_memory_files(job.memory_root)
    with maintenance_lock:
        extract_agent.run_sync(prompt, deps=MemoryDeps(memory_root=job.memory_root))
        after_extract = snapshot_memory_files(job.memory_root)
        touched_after_extract = diff_touched_paths(before, after_extract)
        apply_write_hygiene(
            job.memory_root,
            touched_paths=touched_after_extract,
        )
        after = snapshot_memory_files(job.memory_root)
        touched_paths = diff_touched_paths(before, after)
        record_memory_activity(job.memory_root, touched_paths)
        audit = audit_memory_store(job.memory_root)
        should_schedule = should_run_consolidation(job.memory_root, audit)
    if should_schedule:
        consolidation_runner.submit(ConsolidationJob(memory_root=job.memory_root))


def run_consolidation_pass(
    *,
    memory_root: Path,
    agent: Any,
    maintenance_lock: threading.Lock,
) -> str:
    with maintenance_lock:
        audit = audit_memory_store(memory_root)
        result = agent.run_sync(
            build_consolidation_prompt(
                str(memory_root),
                audit_summary=format_audit_for_prompt(audit),
            ),
            deps=MemoryDeps(memory_root=memory_root),
        )
        apply_post_consolidation_hygiene(memory_root)
        mark_consolidated(memory_root)
    return result.output


def render_turn_transcript(*, user_text: str, assistant_text: str) -> str:
    return dedent(
        f"""\
        [user]
        {user_text}

        [assistant]
        {assistant_text}
        """
    ).strip()


def _format_existing_memories_manifest(memory_root: Path) -> str:
    from .memory_scan import format_memory_manifest

    return format_memory_manifest(scan_memory_headers(memory_root))


if __name__ == "__main__":
    main()
