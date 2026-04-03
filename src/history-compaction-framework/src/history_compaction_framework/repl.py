from __future__ import annotations

from pathlib import Path

from .session import CompactedSession


HELP_TEXT = "\n".join(
    [
        "Commands:",
        "  /help       Show this help text",
        "  /clear      Start fresh by wiping raw history and collapse state",
        "  /raw        Print the canonical raw history",
        "  /projected  Print the current projected provider-facing history",
        "  /staged     Print staged spans",
        "  /committed  Print committed spans",
        "  /state      Print thresholds, estimates, and health counters",
        "  quit        Exit the REPL",
    ]
)


def run_repl(*, session: CompactedSession, state_root: Path) -> None:
    print(f"State root: {state_root}")
    print(f"Demo context window: {session.manager.config.context_window}")
    print("Type your message and press Enter. Type '/help' for commands. Type 'quit' to exit.")

    while True:
        try:
            user_text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return

        if not user_text:
            continue
        if user_text.lower() in {"quit", "/quit"}:
            print("Exiting.")
            return
        if user_text.startswith("/") and handle_command(session, user_text):
            continue

        try:
            assistant_text = session.run_sync(user_text)
        except Exception as exc:
            print(f"\nError: {exc}")
            continue

        print(f"\nAssistant: {assistant_text}")


def handle_command(session: CompactedSession, command: str) -> bool:
    manager = session.manager
    if command == "/help":
        print(HELP_TEXT)
        return True
    if command == "/clear":
        session.clear()
        print("Cleared raw history and collapse state.")
        return True
    if command == "/raw":
        print(manager.render_raw_history())
        return True
    if command == "/projected":
        print(manager.render_projected_history())
        return True
    if command == "/staged":
        print(manager.render_staged_spans())
        return True
    if command == "/committed":
        print(manager.render_committed_spans())
        return True
    if command == "/state":
        print(manager.render_state())
        return True
    return False
