from __future__ import annotations

from pathlib import Path
import threading
from typing import Any, Callable

from pydantic_ai.messages import ModelRequest, UserPromptPart

from .agents import build_main_agent, build_summarizer_agent
from .background import StageJob, StageRunner
from .manager import HistoryCompactionManager
from .models import CompactionConfig
from .token_estimation import estimate_model_messages


class CompactedSession:
    def __init__(
        self,
        *,
        state_root: Path,
        main_agent: Any,
        summarizer_agent: Any,
        model_name: str,
        config: CompactionConfig | None = None,
    ) -> None:
        self.lock = threading.Lock()
        self.manager = HistoryCompactionManager(
            state_root,
            config=config,
            lock=self.lock,
            model_name=model_name,
        )
        self.main_agent = main_agent
        self.summarizer_agent = summarizer_agent
        self._recovery_notifier: Callable[[str], None] | None = None
        self.manager.configure_recovery(
            summarizer_agent=self.summarizer_agent,
            notifier=self._notify_recovery,
        )
        self.stage_runner = StageRunner(
            run_stage=lambda job: self._run_stage_job(job),
        )

    @classmethod
    def create(
        cls,
        *,
        state_root: Path,
        model: str,
        summary_model: str | None = None,
        config: CompactionConfig | None = None,
    ) -> "CompactedSession":
        return cls(
            state_root=state_root,
            main_agent=build_main_agent(model),
            summarizer_agent=build_summarizer_agent(summary_model or model),
            model_name=model,
            config=config,
        )

    def run_sync(self, user_text: str) -> str:
        pending_messages = [ModelRequest(parts=[UserPromptPart(content=user_text)])]
        message_history = self.manager.prepare_projected_history_for_run(
            pending_messages=pending_messages,
        )
        estimated_request_input_tokens = estimate_model_messages(
            [*message_history, *pending_messages],
            model_name=self.manager.model_name,
            calibration_factor=1.0,
        )
        if message_history:
            result = self.main_agent.run_sync(user_text, message_history=message_history)
        else:
            result = self.main_agent.run_sync(user_text)
        usage = result.usage()
        self.manager.record_turn(
            user_text,
            list(result.new_messages()),
            estimated_request_input_tokens=estimated_request_input_tokens,
            actual_input_tokens=usage.input_tokens,
            actual_output_tokens=usage.output_tokens,
            request_count=usage.requests,
        )
        self.stage_runner.submit(StageJob(reason="post-turn"))
        return result.output

    def close(self) -> None:
        self.stage_runner.close()

    def clear(self) -> None:
        self.stage_runner.clear_pending()
        self.stage_runner.close()
        self.manager.clear_state()
        self.stage_runner = StageRunner(
            run_stage=lambda job: self._run_stage_job(job),
        )

    def set_recovery_notifier(self, notifier: Callable[[str], None] | None) -> None:
        self._recovery_notifier = notifier

    def _run_stage_job(self, job: StageJob) -> None:
        self.manager.stage_if_needed(self.summarizer_agent)

    def _notify_recovery(self, message: str) -> None:
        if self._recovery_notifier is not None:
            self._recovery_notifier(message)
