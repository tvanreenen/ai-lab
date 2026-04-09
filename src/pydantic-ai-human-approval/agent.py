"""Order and support-case scenario wiring for the approval workflow demo."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import Agent, DeferredToolRequests
from tools.order import FakeOrderBackend, OrderItem, SubmittedOrder
from tools.support_case import FakeSupportCaseBackend, SubmittedSupportCase


@dataclass
class OrderSupportScenario:
    """Scenario wiring for the approval workflow demo."""

    model_name: str
    order_backend: FakeOrderBackend = field(default_factory=FakeOrderBackend)
    support_case_backend: FakeSupportCaseBackend = field(
        default_factory=FakeSupportCaseBackend,
    )

    def __post_init__(self) -> None:
        self.agent = self._build_agent()

    def _build_agent(self) -> Agent:
        agent = Agent(
            self.model_name,
            output_type=[str, DeferredToolRequests],
            instructions=(
                "You are a general operations assistant. "
                "Answer normal informational questions directly when no business action is needed. "
                "Assume customer identity and account context are already known by the surrounding system. "
                "Use an available tool only when the user is clearly asking to take a business action and you have enough details to do so. "
                "Do not invent missing details; ask a follow-up question instead. "
                "If reviewer feedback on a denied tool call is clear enough, revise and resubmit immediately. "
                "Only ask another follow-up question when material ambiguity remains."
            ),
        )

        @agent.tool_plain(
            requires_approval=True,
            require_parameter_descriptions=True,
        )
        def submit_order(
            items: list[OrderItem],
            shipping_method: str | None = None,
            notes: str | None = None,
        ) -> str:
            """Submit an order once a human approves it.

            Args:
                items: Line items to include in the order.
                shipping_method: Optional shipping method such as overnight or ground.
                notes: Optional order notes.
            """

            order = SubmittedOrder(
                items=items,
                shipping_method=shipping_method,
                notes=notes,
            )
            return self.order_backend.submit(order)

        @agent.tool_plain(
            requires_approval=True,
            require_parameter_descriptions=True,
        )
        def submit_support_case(
            summary: str,
            description: str,
            severity: str,
            product_area: str | None = None,
        ) -> str:
            """Submit a support case once a human approves it.

            Args:
                summary: Short issue summary.
                description: Detailed description of the problem.
                severity: Issue severity such as low, medium, high, or critical.
                product_area: Optional product area or subsystem.
            """

            support_case = SubmittedSupportCase(
                summary=summary,
                description=description,
                severity=severity,
                product_area=product_area,
            )
            return self.support_case_backend.submit(support_case)

        return agent
