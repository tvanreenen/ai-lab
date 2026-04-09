"""Support-case models and fake backend for the approval workflow demo."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


class SubmittedSupportCase(BaseModel):
    """Structured payload for a support case submission."""

    summary: str = Field(description="Short issue summary")
    description: str = Field(description="Detailed problem description")
    severity: str = Field(description="Severity such as low, medium, high, or critical")
    product_area: str | None = Field(
        default=None,
        description="Optional product area or subsystem",
    )


@dataclass
class FakeSupportCaseBackend:
    """In-memory store for approved support cases."""

    support_cases: list[SubmittedSupportCase] = field(default_factory=list)

    def submit(self, support_case: SubmittedSupportCase) -> str:
        self.support_cases.append(support_case)
        return f"Support case submitted with severity {support_case.severity!r}."
