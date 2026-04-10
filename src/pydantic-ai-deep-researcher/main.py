"""Graph-driven iterative web research example built on ``pydantic-ai``."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field

import typer
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool
from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from rich.console import Console
from rich.panel import Panel

load_dotenv()

app = typer.Typer(add_completion=False)
console = Console()
DEFAULT_MODEL = os.getenv("DEEP_RESEARCHER_MODEL", "openai:gpt-5.4")


class AgentResponse(BaseModel):
    """Structured response emitted on every agent cycle."""

    done: bool = Field(
        ...,
        description="True only when the user request is fully satisfied.",
    )
    answer: str | None = Field(
        None,
        description="Partial or final answer assembled so far.",
    )
    progress: str | None = Field(
        None,
        description="Short statement describing the measurable progress from this run.",
    )
    suggested_next: str | None = Field(
        None,
        description="Next action to take if the task is not complete.",
    )
    reason: str | None = Field(
        None,
        description="Reasoning behind the choices made in this run.",
    )
    plan: list[str] | None = Field(
        default=None,
        description="Ordered checklist of steps to complete the task.",
    )
    completed: list[str] | None = Field(
        default=None,
        description="Subset of plan items that are now complete.",
    )
    stalled: bool | None = Field(
        default=None,
        description="True when the agent could not make meaningful progress this run.",
    )
    should_adapt: bool | None = Field(
        default=None,
        description="True when new information requires a revised plan.",
    )


def build_agent(model: str) -> Agent:
    return Agent(
        model=model,
        tools=[duckduckgo_search_tool(max_results=10)],
        output_type=AgentResponse,
        system_prompt=(
            "You are a tool-using research agent that plans, executes, and adapts as you learn. "
            "Return only a structured AgentResponse object.\n"
            "Rules:\n"
            "- If mode == 'plan': propose a flexible research checklist in AgentResponse.plan and set done=false.\n"
            "- If mode == 'execute': choose one unchecked plan item, make measurable progress, and update AgentResponse.completed.\n"
            "- If mode == 'adapt': provide a revised AgentResponse.plan that preserves completed work but improves the remaining steps.\n"
            "- If mode == 'recover': focus on the best unblocked next step; if the current plan is weak, provide a revised AgentResponse.plan.\n"
            "- If new information changes the approach or reveals better alternatives, set AgentResponse.should_adapt=true and provide a revised plan immediately.\n"
            "- If no measurable progress is possible, set AgentResponse.stalled=true and suggest a revised plan focused on what remains unblocked.\n"
            "- When the full answer is assembled, set done=true and place the complete answer in AgentResponse.answer.\n"
            "Keep AgentResponse.progress concise and practical. Include suggested_next when not done."
        ),
    )


@dataclass
class State:
    """Shared state carried across graph iterations."""

    user_request: str
    model: str = DEFAULT_MODEL
    budget_runs: int = 10
    runs_used: int = 0
    history: list = field(default_factory=list)
    last_response: AgentResponse | None = None
    plan: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    consecutive_no_progress: int = 0
    mode: str = "plan"  # 'plan' | 'execute' | 'adapt' | 'recover'


@dataclass
class Done:
    answer: str


@dataclass
class AgentRun(BaseNode[State, None, Done]):
    """Execute one agent cycle, then hand control back to the decision node."""

    async def run(self, ctx: GraphRunContext[State, None]) -> Decide | End[Done]:
        state = ctx.state
        state.runs_used += 1
        agent = build_agent(state.model)

        current_plan = "\n".join(f"- {item}" for item in state.plan) or "(none)"
        current_completed = "\n".join(f"- {item}" for item in state.completed) or "(none)"
        user_prompt = (
            f"User request:\n{state.user_request}\n\n"
            f"Current mode: {state.mode}\n"
            f"Current plan:\n{current_plan}\n\n"
            f"Completed items:\n{current_completed}\n\n"
            "Follow the system rules. If planning, propose a flexible plan. "
            "If executing, choose one unchecked item and make measurable progress. "
            "If adapting or recovering, revise the plan when new information or blockers require it."
        )

        result = await agent.run(
            user_prompt=user_prompt,
            message_history=state.history,
        )

        response: AgentResponse = result.output
        state.history = result.new_messages()
        state.last_response = response

        previous_completed = set(state.completed)

        if isinstance(response.plan, list) and response.plan:
            state.plan = [str(item) for item in response.plan]
        elif response.should_adapt:
            console.print(
                "[yellow]Warning: agent requested adaptation without returning a revised plan.[/yellow]",
            )

        if isinstance(response.completed, list) and response.completed:
            for item in response.completed:
                item_str = str(item)
                if item_str not in state.completed:
                    state.completed.append(item_str)

        progressed = (
            len(set(state.completed)) > len(previous_completed)
            or bool((response.progress or "").strip())
        )

        if response.stalled:
            state.consecutive_no_progress += 1
        elif progressed:
            state.consecutive_no_progress = 0
        else:
            state.consecutive_no_progress += 1

        unchecked = [item for item in state.plan if item not in state.completed]
        if response.should_adapt:
            state.mode = "adapt"
        elif state.consecutive_no_progress >= 3 or response.stalled:
            state.mode = "recover"
        elif unchecked:
            state.mode = "execute"
        else:
            state.mode = "plan"

        console.rule(f"[bold]Cycle {state.runs_used}")

        summary_lines = [
            f"[b]mode[/b]: {state.mode}",
            f"[b]done[/b]: {response.done}",
            f"[b]plan items[/b]: {len(state.plan)}",
            f"[b]completed[/b]: {len(state.completed)}",
            f"[b]progress[/b]: {response.progress or '(none)'}",
            f"[b]suggested_next[/b]: {response.suggested_next or '(none)'}",
            f"[b]reason[/b]: {response.reason or '(none)'}",
        ]
        if response.stalled:
            summary_lines.append(f"[b]stalled[/b]: {response.stalled}")
        if response.should_adapt:
            summary_lines.append(f"[b]should_adapt[/b]: {response.should_adapt}")

        console.print(
            Panel.fit(
                "\n".join(summary_lines),
                title="Agent Response (this run)",
            ),
        )

        if state.plan:
            plan_lines: list[str] = []
            completed_not_in_plan = [item for item in state.completed if item not in state.plan]
            for index, item in enumerate(completed_not_in_plan, start=1):
                plan_lines.append(f"✓ {index}. {item}")

            start_index = len(completed_not_in_plan) + 1
            for index, item in enumerate(state.plan, start=start_index):
                status = "✓" if item in state.completed else "○"
                plan_lines.append(f"{status} {index}. {item}")

            console.print(Panel.fit("\n".join(plan_lines), title="Plan Progress"))

        if response.answer:
            preview = response.answer
            if len(preview) > 400:
                preview = preview[:400] + "…"
            console.print(Panel(preview, title="Answer (so far)"))

        if response.done:
            return End(Done(answer=response.answer or "[No final answer produced]"))

        return Decide()


@dataclass
class Decide(BaseNode[State, None, Done]):
    """Continue the loop until the task is done or the run budget is exhausted."""

    async def run(self, ctx: GraphRunContext[State, None]) -> AgentRun | End[Done]:
        state = ctx.state

        if state.last_response and state.last_response.done:
            return End(Done(answer=state.last_response.answer or "[No final answer produced]"))

        if state.runs_used < state.budget_runs:
            return AgentRun()

        if state.last_response and state.last_response.answer:
            answer = state.last_response.answer
            if not state.last_response.done:
                answer += (
                    f"\n\n*Note: Research stopped after {state.budget_runs} cycles. "
                    "A larger budget may produce a more complete result.*"
                )
            return End(Done(answer=answer))

        return End(
            Done(
                answer=(
                    "[No final answer produced - insufficient information gathered within "
                    f"{state.budget_runs} cycles.]"
                ),
            ),
        )


async def run_once(user_request: str, model: str, budget: int) -> str:
    state = State(user_request=user_request, model=model, budget_runs=budget)
    graph = Graph(nodes=(AgentRun, Decide))

    async with graph.iter(AgentRun(), state=state) as run:
        async for _ in run:
            pass
        result = run.result
        done: Done = result.output

    console.rule("[bold]FINAL OUTPUT")
    console.print(done.answer)
    return done.answer


@app.command(
    help="Run the research loop once and print each cycle until completion or budget exhaustion.",
)
def run(
    request: str = typer.Argument(
        ...,
        help="The research task and any task-specific completion criteria.",
    ),
    model: str = typer.Option(DEFAULT_MODEL, help="Model ID."),
    budget: int = typer.Option(10, min=1, help="Maximum number of research cycles."),
) -> None:
    asyncio.run(run_once(request, model, budget))


if __name__ == "__main__":
    app()
