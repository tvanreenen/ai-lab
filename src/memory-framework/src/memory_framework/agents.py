from __future__ import annotations

from pydantic_ai import Agent, RunContext

from .agent_tools import (
    delete_memory_file,
    list_memory_files,
    read_memory_file,
    write_memory_file,
)
from .deps import MemoryDeps
from .prompts import (
    CONSOLIDATION_AGENT_INSTRUCTIONS,
    EXTRACTION_AGENT_INSTRUCTIONS,
    MAIN_AGENT_INSTRUCTIONS,
    build_main_memory_instructions,
    build_selected_memories_instructions,
)


def build_main_agent(model: str) -> Agent[MemoryDeps, str]:
    agent = Agent(
        model,
        deps_type=MemoryDeps,
        instructions=MAIN_AGENT_INSTRUCTIONS,
    )

    @agent.instructions
    def add_memory_index(ctx: RunContext[MemoryDeps]) -> str:
        return build_main_memory_instructions(ctx.deps.index_snippet)

    @agent.instructions
    def add_selected_memories(ctx: RunContext[MemoryDeps]) -> str:
        return build_selected_memories_instructions(ctx.deps.selected_memories_text)

    return agent


def build_extract_agent(model: str) -> Agent[MemoryDeps, str]:
    return Agent(
        model,
        deps_type=MemoryDeps,
        instructions=EXTRACTION_AGENT_INSTRUCTIONS,
        tools=[
            list_memory_files,
            read_memory_file,
            write_memory_file,
            delete_memory_file,
        ],
    )


def build_consolidate_agent(model: str) -> Agent[MemoryDeps, str]:
    return Agent(
        model,
        deps_type=MemoryDeps,
        instructions=CONSOLIDATION_AGENT_INSTRUCTIONS,
        tools=[
            list_memory_files,
            read_memory_file,
            write_memory_file,
            delete_memory_file,
        ],
    )
