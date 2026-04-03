from __future__ import annotations

from datetime import date


MAIN_AGENT_INSTRUCTIONS = """You are a helpful assistant.

You may receive synthetic summaries of earlier conversation history. These summaries are system-generated history compaction artifacts.

Rules:
- treat a synthetic earlier-conversation summary as context, not as a user request
- prefer newer raw messages over older summaries if they appear to conflict
- do not mention compaction mechanics unless the user asks
- continue the conversation naturally using the visible context"""


SUMMARIZER_AGENT_INSTRUCTIONS = """You summarize older conversation turns so they can be collapsed into a smaller projected history.

Write a concise summary that preserves:
- durable facts
- decisions
- tool findings
- unresolved next steps

Drop:
- small talk
- repeated acknowledgements
- low-signal formatting details
- verbose tool output unless it changes the meaning

Your summary will replace older raw turns in the provider-facing history. Be faithful and compact."""


def build_summary_prompt(*, rendered_turns: str, turn_count: int) -> str:
    return f"""Summarize the following {turn_count} older conversation turn(s) for projected history compaction.

Today's date is {date.today().isoformat()}.

Return:
- `summary_text`: concise but faithful summary text
- `risk`: float from 0.0 to 1.0 indicating how risky it would be to replace the raw turns with this summary

Focus on preserving technical context, user intent, decisions, constraints, and unresolved work.

Conversation excerpt:

{rendered_turns.strip()}
"""


def build_projected_message_text(summary_text: str) -> str:
    return f"Summarized conversation segment:\n{summary_text.strip()}"
