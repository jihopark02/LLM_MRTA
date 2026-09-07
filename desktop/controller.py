"""Qt-independent controller for the native operator console (§21).

Every mission decision crosses an existing public boundary.  This module owns
presentation state (chat and backend instances), but never edits a task, runs
CBBA directly, or advances an executor through a private method.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from demo.animation import PlaybackSpec, build_playback_spec
from demo.mock_script import make_mock_backend
from demo.visualization import (
    MapRenderSpec,
    execution_map_spec,
    plan_map_spec,
    runtime_map_spec,
)
from execution.executor import SimExecutor, Termination
from interaction.audit import CheckpointAudit, ExecutionAudit
from interaction.audit_io import write_session_audit
from interaction.online_execute import advance_online_session
from interaction.orchestrator import (
    TurnResult,
    cancel_clarification,
    handle_turn,
    select_clarification_candidate,
)
from interaction.session import MissionSession, SessionPhase
from llm.backend import DEFAULT_MODEL, OpenAIBackend
from llm.cache import CachedBackend, RecordingBackend
from scenarios.scene import load_scene

ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "scenarios" / "industrial_park.yaml"
DEFAULT_RUNTIME_ROOT = ROOT / "data"
SUPPORTED_MODES = ("live", "cached", "mock")
DEFAULT_FRAME_COUNT = 36


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    text: str


@dataclass(frozen=True, slots=True)
class AdvancePresentation:
    audit: CheckpointAudit | ExecutionAudit
    playback: PlaybackSpec | None
    playback_error: str | None = None


class DesktopController:
    """One presentation session shared by the two desktop windows."""

    def __init__(
        self,
        *,
        scene_path: str | Path = SCENE_PATH,
        runtime_root: str | Path | None = None,
        frame_count: int = DEFAULT_FRAME_COUNT,
    ) -> None:
        self.scene_path = Path(scene_path)
        configured_root = runtime_root or os.environ.get(
            "LLM_MRTA_RUNTIME_ROOT", DEFAULT_RUNTIME_ROOT
        )
        self.runtime_root = Path(configured_root)
        if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 2:
            raise ValueError("frame_count must be an integer >= 2")
        self.frame_count = frame_count
        self.mode = "mock"
        self.backends: dict[str, object] = {}
        self.chat: list[ChatMessage] = []
        self.session = self._fresh_session()

    @property
    def audit_directory(self) -> Path:
        return self.runtime_root / "interaction_runs"

    @property
    def cache_directory(self) -> Path:
        return self.runtime_root / "llm_cache"

    def _fresh_session(self) -> MissionSession:
        return MissionSession(
            f"desktop-{uuid4().hex[:12]}",
            load_scene(self.scene_path),
        )

    def new_session(self) -> MissionSession:
        self.session = self._fresh_session()
        self.backends = {}
        self.chat = []
        return self.session

    def set_mode(self, mode: str) -> None:
        if mode not in SUPPORTED_MODES:
            raise ValueError(f"unsupported desktop mode: {mode!r}")
        self.mode = mode

    def _backend(self):
        if self.mode not in self.backends:
            if self.mode == "live":
                self.backends[self.mode] = RecordingBackend(
                    OpenAIBackend(DEFAULT_MODEL), self.cache_directory
                )
            elif self.mode == "cached":
                self.backends[self.mode] = CachedBackend(
                    DEFAULT_MODEL, self.cache_directory
                )
            else:
                self.backends[self.mode] = make_mock_backend()
        return self.backends[self.mode]

    def _record(self, operator: str, assistant: str) -> None:
        self.chat.extend(
            (ChatMessage("operator", operator), ChatMessage("assistant", assistant))
        )

    def _persist(self) -> Path:
        return write_session_audit(self.session, self.audit_directory)

    def submit(self, utterance: str) -> TurnResult:
        if not isinstance(utterance, str) or not utterance.strip():
            raise ValueError("utterance must contain text")
        result = handle_turn(self.session, utterance.strip(), self._backend())
        self._record(utterance.strip(), result.message)
        self._persist()
        return result

    def select_candidate(self, entity_id: str) -> TurnResult:
        result = select_clarification_candidate(
            self.session, entity_id, mode=self.mode
        )
        self._record(f"후보 선택: {entity_id}", result.message)
        self._persist()
        return result

    def cancel_candidate(self) -> TurnResult:
        result = cancel_clarification(self.session, mode=self.mode)
        self._record("후보 선택 취소", result.message)
        self._persist()
        return result

    def advance_checkpoint(self) -> AdvancePresentation:
        """Commit exactly one online completion event and prepare its view."""
        session = self.session
        if session.state is None or session.plan is None:
            raise ValueError("a committed mission and plan are required before execution")
        before = (
            session.runtime.checkpoint()
            if session.runtime is not None
            else SimExecutor(session.state, session.scene).checkpoint()
        )
        audit = advance_online_session(session, mode=self.mode)
        playback = None
        playback_error = None
        if session.runtime is not None:
            after = session.runtime.checkpoint()
            if after.now > before.now:
                try:
                    playback = build_playback_spec(
                        session.scene,
                        before,
                        after,
                        frame_count=self.frame_count,
                    )
                except Exception as exc:  # noqa: BLE001 - committed state is preserved
                    playback_error = f"{type(exc).__name__}: {exc}"
        if isinstance(audit, CheckpointAudit):
            completed = ", ".join(audit.completed_now) or "없음"
            response = (
                f"t={audit.simulation_time:.1f}s checkpoint · 완료: {completed}"
            )
        else:
            response = (
                f"실행 종료: {audit.execution_termination} · "
                f"makespan {audit.makespan:.1f}s"
            )
            if audit.error_type:
                response += f" · {audit.error_type}: {audit.error_detail}"
        self._record("[다음 checkpoint]", response)
        self._persist()
        return AdvancePresentation(audit, playback, playback_error)

    def current_map_spec(self) -> MapRenderSpec | None:
        """Best truthful static view for the session's current phase."""
        session = self.session
        if session.state is None:
            return None
        if (
            session.phase is SessionPhase.EXECUTED
            and session.execution is not None
            and session.execution.termination is Termination.COMPLETED
        ):
            return execution_map_spec(
                session.scene, session.state.graph, session.execution
            )
        if session.runtime is not None:
            return runtime_map_spec(session.scene, session.runtime)
        if session.plan is not None:
            return plan_map_spec(session.scene, session.state.graph, session.plan)
        return None


__all__ = [
    "AdvancePresentation",
    "ChatMessage",
    "DesktopController",
    "SUPPORTED_MODES",
]
