"""Human approval demo with approval-required order and support tools.

Run with:

    uv run --package pydantic-ai-human-approval python src/pydantic-ai-human-approval/main.py
"""

from __future__ import annotations

import os

from agent import OrderSupportScenario
from cli_workflow import ApprovalWorkflow
from dotenv import load_dotenv

MODEL_NAME = os.getenv("APPROVAL_WORKFLOW_MODEL", "openai:gpt-5.4")


def main() -> None:
    load_dotenv()

    workflow = ApprovalWorkflow(OrderSupportScenario(MODEL_NAME))

    print("Human approval demo.")
    print("This package ships one general responder agent with two approval-required business tools.")
    print(
        "Chat naturally. When the agent tries to submit an order or support case, "
        "review the validated tool args and choose yes, revise, or cancel.\n",
    )

    workflow.run()


if __name__ == "__main__":
    main()
