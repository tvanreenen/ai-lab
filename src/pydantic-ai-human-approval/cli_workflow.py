"""Generic chat plus deferred-approval controller for the CLI demo."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolDenied
from pydantic_ai.messages import ModelMessage, ToolCallPart

TOP_LEVEL_COMMANDS = {"quit", "q"}
APPROVAL_DECISIONS = {"yes", "revise", "cancel"}


def normalize_command(raw_command: str) -> str:
    command = raw_command.strip().lower()
    if command == "q":
        return "quit"
    if command in {"y", "yes"}:
        return "yes"
    if command in {"c", "cancel"}:
        return "cancel"
    if command in {"r", "revise"}:
        return "revise"
    return command


class ApprovalRunResult(Protocol):
    """Minimal run result interface used by the workflow."""

    output: str | DeferredToolRequests

    def all_messages(self) -> list[ModelMessage]: ...


class ApprovalAgent(Protocol):
    """Minimal agent surface used by the workflow."""

    def run_sync(
        self,
        user_prompt: str | None = None,
        *,
        message_history: list[ModelMessage],
        deferred_tool_results: DeferredToolResults | None = None,
        output_type: object | None = None,
    ) -> ApprovalRunResult: ...


class ApprovalScenario(Protocol):
    """Scenario contract for the generic approval workflow."""

    agent: ApprovalAgent


@dataclass
class ChatSession:
    """Conversation state for the general responder plus deferred approvals."""

    message_history: list[ModelMessage] = field(default_factory=list)
    pending_requests: DeferredToolRequests | None = None

    def reset_to_chat(self) -> None:
        self.pending_requests = None


class ApprovalWorkflow:
    """Chat-first approval workflow for approval-required tools."""

    def __init__(self, scenario: ApprovalScenario) -> None:
        self.scenario = scenario
        self.session = ChatSession()

    def run(self) -> None:
        while True:
            if self.session.pending_requests is None:
                if not self._handle_chat():
                    return
                continue

            if not self._handle_approval():
                return

    def _handle_chat(self) -> bool:
        # Main conversation prompt while no approval-required tool call is pending.
        user_input = input("Chat: ").strip()
        normalized = normalize_command(user_input)

        if normalized in TOP_LEVEL_COMMANDS:
            print("Goodbye!")
            return False
        if not user_input:
            return True

        result = self.scenario.agent.run_sync(
            user_input,
            message_history=self.session.message_history,
            output_type=[str, DeferredToolRequests],
        )
        self.session.message_history = result.all_messages()

        if isinstance(result.output, DeferredToolRequests):
            self.session.pending_requests = result.output
            return True

        print("\nAgent:")
        print(result.output)
        print("")
        return True

    def _handle_approval(self) -> bool:
        requests = self.session.pending_requests
        if requests is None:
            self.session.reset_to_chat()
            return True

        print(self._render_approval_gate(requests))
        decision = self._prompt_approval_command()

        if decision == "revise":
            return self._handle_revision_feedback(requests)

        result = self.scenario.agent.run_sync(
            message_history=self.session.message_history,
            deferred_tool_results=self._build_approval_results(requests, decision),
            output_type=[str, DeferredToolRequests],
        )
        self.session.message_history = result.all_messages()

        if isinstance(result.output, DeferredToolRequests):
            self.session.pending_requests = result.output
            print("\nThe runtime is still waiting on deferred tool approval.\n")
            return True

        print("\nAgent:")
        print(result.output)
        print("")
        self.session.reset_to_chat()
        return True

    def _prompt_approval_command(self) -> str:
        while True:
            # Final execution decision for the currently deferred tool call.
            command = normalize_command(
                input(
                    "Submit? [y]es / [r]evise / [c]ancel: ",
                ),
            )
            if command in APPROVAL_DECISIONS:
                return command
            print("Unknown command. Choose yes, revise, or cancel.")

    def _handle_revision_feedback(self, requests: DeferredToolRequests) -> bool:
        # Free-text reviewer feedback used to revise the pending tool call.
        feedback = input("What should change before approval? ").strip()
        if not feedback:
            print("No revision feedback provided. The pending tool call is unchanged.\n")
            return True

        result = self.scenario.agent.run_sync(
            message_history=self.session.message_history,
            deferred_tool_results=self._build_revision_results(requests, feedback),
            output_type=[str, DeferredToolRequests],
        )
        self.session.message_history = result.all_messages()

        if isinstance(result.output, DeferredToolRequests):
            self.session.pending_requests = result.output
            print("\nThe agent updated the pending action. Review the revised payload below.\n")
            return True

        self.session.pending_requests = None
        print("\nAgent:")
        print(result.output)
        print("")
        return True

    def _build_approval_results(
        self,
        requests: DeferredToolRequests,
        decision: str,
    ) -> DeferredToolResults:
        normalized = normalize_command(decision)
        if normalized == "yes":
            return DeferredToolResults(
                approvals={call.tool_call_id: True for call in requests.approvals},
            )
        if normalized == "cancel":
            return DeferredToolResults(
                approvals={
                    call.tool_call_id: ToolDenied(
                        "Cancelled at the final tool approval gate.",
                    )
                    for call in requests.approvals
                },
            )
        raise ValueError(f"Unsupported approval command: {decision}")

    def _build_revision_results(
        self,
        requests: DeferredToolRequests,
        feedback: str,
    ) -> DeferredToolResults:
        return DeferredToolResults(
            approvals={
                call.tool_call_id: ToolDenied(
                    "The reviewer requested changes before approval. "
                    f"Apply this feedback to the pending tool call: {feedback}. "
                    "If the request is clear enough, immediately submit a revised tool call now. "
                    "Do not ask for reconfirmation unless required details are still missing or ambiguous.",
                )
                for call in requests.approvals
            },
        )

    def _render_approval_gate(self, requests: DeferredToolRequests) -> str:
        if not requests.approvals:
            return "No approval-required tool calls are pending."

        rendered_calls = "\n\n".join(
            self._render_tool_call(call) for call in requests.approvals
        )
        return (
            f"{rendered_calls}\n"
        )

    def _render_tool_call(self, call: ToolCallPart) -> str:
        args = json.dumps(call.args_as_dict(), indent=2, sort_keys=True)
        return (
            f"Tool: {call.tool_name}\n"
            f"Tool Call ID: {call.tool_call_id}\n"
            f"Args:\n{args}"
        )
