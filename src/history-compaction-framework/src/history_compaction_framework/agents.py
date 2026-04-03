from __future__ import annotations

from pydantic_ai import Agent

from .models import StageSummary
from .prompts import MAIN_AGENT_INSTRUCTIONS, SUMMARIZER_AGENT_INSTRUCTIONS


def build_main_agent(model: str) -> Agent[None, str]:
    return Agent(
        model,
        instructions=MAIN_AGENT_INSTRUCTIONS,
    )


def build_summarizer_agent(model: str) -> Agent[None, StageSummary]:
    return Agent(
        model,
        instructions=SUMMARIZER_AGENT_INSTRUCTIONS,
        output_type=StageSummary,
    )
