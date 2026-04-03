from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TurnRecord(BaseModel):
    turn_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    user_text: str
    messages: list[dict[str, Any]]
    estimated_turn_payload_tokens: int | None = None
    actual_input_tokens: int | None = None
    actual_output_tokens: int | None = None
    request_count: int | None = None


class StagedSpan(BaseModel):
    start_turn_id: str
    end_turn_id: str
    summary_text: str
    risk: float = 0.25
    staged_at: datetime = Field(default_factory=utc_now)

    @field_validator("risk")
    @classmethod
    def clamp_risk(cls, value: float) -> float:
        return max(0.0, min(1.0, value))


class CommittedSpan(BaseModel):
    collapse_id: str
    start_turn_id: str
    end_turn_id: str
    summary_text: str
    projected_message_text: str
    committed_at: datetime = Field(default_factory=utc_now)


class CollapseHealth(BaseModel):
    staging_attempts: int = 0
    staging_failures: int = 0
    empty_stage_runs: int = 0
    committed_from_staging: int = 0
    last_error: str | None = None


class CalibrationStats(BaseModel):
    samples: int = 0
    input_calibration_factor: float = 1.0
    last_estimated_request_input_tokens: int | None = None
    last_actual_input_tokens: int | None = None
    last_actual_output_tokens: int | None = None
    last_request_count: int | None = None


class RecoveryRunResult(BaseModel):
    in_progress: bool = False
    status: str | None = None
    committed_count: int = 0
    staged_count: int = 0
    starting_request_tokens: int = 0
    ending_request_tokens: int = 0
    hit_chunk_limit: bool = False
    hit_time_limit: bool = False


class CollapseState(BaseModel):
    committed_spans: list[CommittedSpan] = Field(default_factory=list)
    staged_spans: list[StagedSpan] = Field(default_factory=list)
    under_pressure: bool = False
    last_stage_check_request_tokens: int = 0
    next_collapse_id: int = 1
    health: CollapseHealth = Field(default_factory=CollapseHealth)
    calibration: CalibrationStats = Field(default_factory=CalibrationStats)
    last_recovery: RecoveryRunResult = Field(default_factory=RecoveryRunResult)


class StageSummary(BaseModel):
    summary_text: str
    risk: float = 0.25

    @field_validator("summary_text")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Summary must not be empty.")
        return cleaned

    @field_validator("risk")
    @classmethod
    def validate_risk(cls, value: float) -> float:
        return max(0.0, min(1.0, value))


class StageRunResult(BaseModel):
    status: str
    staged_count: int = 0
    estimated_savings_tokens: int = 0
    estimated_request_tokens: int = 0
    target_threshold: int = 0


@dataclass(slots=True)
class CompactionConfig:
    context_window: int = 32_000
    pressure_ratio: float = 0.80
    stage_ratio: float = 0.88
    target_ratio: float = 0.90
    guard_ratio: float = 0.95
    fail_ratio: float = 1.05
    preserve_recent_turns: int = 4
    min_stage_turns: int = 2
    max_stage_turns: int = 6
    max_emergency_stage_chunks: int = 3
    max_emergency_stage_seconds: float = 10.0

    @property
    def pressure_threshold(self) -> int:
        return max(1, int(self.context_window * self.pressure_ratio))

    @property
    def stage_threshold(self) -> int:
        return max(1, int(self.context_window * self.stage_ratio))

    @property
    def target_threshold(self) -> int:
        return max(1, int(self.context_window * self.target_ratio))

    @property
    def guard_threshold(self) -> int:
        return max(1, int(self.context_window * self.guard_ratio))

    @property
    def fail_threshold(self) -> int:
        return max(1, int(self.context_window * self.fail_ratio))
