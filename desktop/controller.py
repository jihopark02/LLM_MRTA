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
from demo.mock_script import (
    OPERATOR_SCRIPT,
    REFERENCE_SCRIPT,
    SENSOR_SCRIPT,
    commands_for_script,
    make_mock_backend,
)
from demo.visualization import (
    MapRenderSpec,
    execution_map_spec,
    plan_map_spec,
    runtime_map_spec,
)
from execution.executor import SimExecutor, Termination
from interaction.audit import CheckpointAudit, ExecutionAudit, IncidentObservationAudit
from interaction.audit_io import write_session_audit
from interaction.observe import apply_fire_observation
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
from scenarios.latent import (
    FireDetectedObservation,
    SimulatedFireField,
    SimulatedFireSource,
    load_latent_fire_field,
    load_latent_incident_fixture,
)
from scenarios.scene import load_scene

ROOT = Path(__file__).resolve().parents[1]
SCENE_PATH = ROOT / "scenarios" / "industrial_park.yaml"
PATROL_SCENE_PATH = ROOT / "scenarios" / "patrol_park.yaml"
DISTRICT_SCENE_PATH = ROOT / "scenarios" / "response_district_patrol.yaml"
SENSOR_FIXTURE_PATH = ROOT / "scenarios" / "patrol_zone_b_fire.yaml"
DISTRICT_LATENT_FIELD_PATH = ROOT / "scenarios" / "response_district_latent.yaml"
DEFAULT_RUNTIME_ROOT = ROOT / "data"
SUPPORTED_MODES = ("live", "cached", "mock")
DEFAULT_FRAME_COUNT = 36

SENSOR_LIVE_EXAMPLES = (
    "네 개 구역을 모두 항공 정찰하고 새 화재가 감지되면 "
    "지상 로봇 진압 단계까지 완료해줘",
)
OPERATOR_LIVE_EXAMPLES = (
    "네 개 구역 전체를 항공 정찰만 해줘",
    "Warehouse 구역에 새 화재가 발생했어. 지상 로봇 진압 단계까지 대응해줘",
)
DYNAMIC_LIVE_EXAMPLES = (
    "네 개 구역 전체를 UAV 두 대로 항공 정찰해줘",
    "이제 UAV 한 대만 사용하고 S2는 제외해줘",
    "Warehouse에 화재가 났어. UAV 한 대로 열화상 확인까지 해줘",
)
DISTRICT_LIVE_EXAMPLES = (
    "여덟 개 구역 전체를 UAV로 항공 정찰해줘",
    "종합병원에 화재가 발생했어. 지상 진압 단계까지 대응해줘",
    "이제 UAV 두 대만 사용하고 S2는 제외해줘",
)


@dataclass(frozen=True, slots=True)
class ScenarioProfile:
    scenario_id: str
    label: str
    scene_path: Path
    mock_script: str | None
    latent_fixture_path: Path | None = None
    live_examples: tuple[str, ...] = ()
    latent_field_path: Path | None = None


SCENARIO_PROFILES = {
    "dynamic-world": ScenarioProfile(
        "dynamic-world",
        "Dynamic Live · world only (no mission fixture)",
        PATROL_SCENE_PATH,
        None,
        live_examples=DYNAMIC_LIVE_EXAMPLES,
    ),
    "dynamic-district": ScenarioProfile(
        "dynamic-district",
        "Dynamic Live · 8-zone district (no mission fixture)",
        DISTRICT_SCENE_PATH,
        None,
        live_examples=DISTRICT_LIVE_EXAMPLES,
    ),
    "district-latent-fire": ScenarioProfile(
        "district-latent-fire",
        "Dynamic Live · 8-zone district · seeded latent fires",
        DISTRICT_SCENE_PATH,
        None,
        live_examples=DISTRICT_LIVE_EXAMPLES,
        latent_field_path=DISTRICT_LATENT_FIELD_PATH,
    ),
    "sensor-detection": ScenarioProfile(
        "sensor-detection",
        "1 · UAV 순찰 → simulated fire detection",
        PATROL_SCENE_PATH,
        SENSOR_SCRIPT,
        SENSOR_FIXTURE_PATH,
        SENSOR_LIVE_EXAMPLES,
    ),
    "operator-report": ScenarioProfile(
        "operator-report",
        "2 · UAV 순찰 중 자연어 화재 신고",
        PATROL_SCENE_PATH,
        OPERATOR_SCRIPT,
        live_examples=OPERATOR_LIVE_EXAMPLES,
    ),
    "reference": ScenarioProfile(
        "reference",
        "기존 reference mission",
        SCENE_PATH,
        REFERENCE_SCRIPT,
        live_examples=(
            "전체 구역을 항공 정찰하고 알려진 두 화재를 지상 진압까지 대응해줘",
        ),
    ),
}
SUPPORTED_SCENARIOS = tuple(SCENARIO_PROFILES)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    text: str


@dataclass(frozen=True, slots=True)
class AdvancePresentation:
    audit: CheckpointAudit | ExecutionAudit
    playback: PlaybackSpec | None
    playback_error: str | None = None
    observation: IncidentObservationAudit | None = None


class DesktopController:
    """One presentation session shared by the two desktop windows."""

    def __init__(
        self,
        *,
        scene_path: str | Path | None = None,
        scenario_id: str = "dynamic-world",
        runtime_root: str | Path | None = None,
        frame_count: int = DEFAULT_FRAME_COUNT,
    ) -> None:
        if scenario_id not in SCENARIO_PROFILES:
            raise ValueError(f"unsupported scenario: {scenario_id!r}")
        self.scenario_id = scenario_id
        self.profile = SCENARIO_PROFILES[scenario_id]
        self.scene_path = (
            Path(scene_path) if scene_path is not None else self.profile.scene_path
        )
        configured_root = runtime_root or os.environ.get(
            "LLM_MRTA_RUNTIME_ROOT", DEFAULT_RUNTIME_ROOT
        )
        self.runtime_root = Path(configured_root)
        if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 2:
            raise ValueError("frame_count must be an integer >= 2")
        self.frame_count = frame_count
        # The scenario-free operating entry is genuinely Live. Explicit
        # scripted profiles remain mock by default for deterministic tests and
        # rehearsals; switching mode later is always an operator action.
        self.mode = "live" if self.profile.mock_script is None else "mock"
        self.backends: dict[str, object] = {}
        self.chat: list[ChatMessage] = []
        self.queued_commands: list[str] = []
        self.observation_source: SimulatedFireSource | SimulatedFireField | None = None
        self.session = self._fresh_session()

    @property
    def audit_directory(self) -> Path:
        return self.runtime_root / "interaction_runs"

    @property
    def cache_directory(self) -> Path:
        return self.runtime_root / "llm_cache"

    def _fresh_session(self) -> MissionSession:
        scene = load_scene(self.scene_path)
        if self.profile.latent_field_path is not None:
            self.observation_source = SimulatedFireField(
                load_latent_fire_field(self.profile.latent_field_path, scene)
            )
        elif self.profile.latent_fixture_path is not None:
            fixture = load_latent_incident_fixture(
                self.profile.latent_fixture_path, scene
            )
            self.observation_source = SimulatedFireSource(fixture)
        else:
            self.observation_source = None
        return MissionSession(
            f"desktop-{uuid4().hex[:12]}",
            scene,
        )

    def new_session(self, scenario_id: str | None = None) -> MissionSession:
        if scenario_id is not None:
            if scenario_id not in SCENARIO_PROFILES:
                raise ValueError(f"unsupported scenario: {scenario_id!r}")
            self.scenario_id = scenario_id
            self.profile = SCENARIO_PROFILES[scenario_id]
            self.scene_path = self.profile.scene_path
        self.session = self._fresh_session()
        self.backends = {}
        self.chat = []
        self.queued_commands = []
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
                if self.profile.mock_script is None:
                    raise ValueError(
                        "dynamic-world has no mock script; select a scripted test profile"
                    )
                self.backends[self.mode] = make_mock_backend(self.profile.mock_script)
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

    @property
    def queued_command(self) -> str | None:
        """The next command that will be consumed, or ``None`` (§23.4.1)."""
        return self.queued_commands[0] if self.queued_commands else None

    def queue_command(self, utterance: str) -> None:
        """Append one presentation command to the FIFO queue (§23.4.1).

        Queuing is deliberately outside ``MissionSession``: no LLM call or
        ``TurnAudit`` exists until :meth:`submit_queued` runs at the committed
        safe checkpoint (§22.6).  A second input never overwrites the first —
        each utterance is its own operator decision.
        """
        if not isinstance(utterance, str) or not utterance.strip():
            raise ValueError("utterance must contain text")
        clean = utterance.strip()
        self.queued_commands.append(clean)
        position = len(self.queued_commands)
        self._record(
            clean,
            f"[QUEUED #{position}] 현재 이동은 중단하지 않습니다. "
            "다음 safe checkpoint부터 순서대로 적용합니다.",
        )

    def cancel_queued(self, index: int) -> str:
        """Drop one not-yet-consumed queued command (§23.4.1).

        Cancelling touches no graph, scene, runtime or referent state — it only
        removes a presentation-layer entry that has not reached the orchestrator.
        """
        if not isinstance(index, int) or isinstance(index, bool):
            raise ValueError("index must be an int")
        if not 0 <= index < len(self.queued_commands):
            raise ValueError(f"no queued command at index {index}")
        removed = self.queued_commands.pop(index)
        self._record(removed, "[QUEUE CANCELLED] 이 명령은 적용되지 않습니다.")
        return removed

    def submit_queued(self) -> TurnResult:
        """Consume the head of the queue once through the real orchestrator."""
        if not self.queued_commands:
            raise ValueError("no command is queued")
        # Dequeue before the external call: an unexpected exception must stop
        # autoplay, not silently retry a possibly consumed LLM request.
        utterance = self.queued_commands.pop(0)
        result = handle_turn(self.session, utterance, self._backend())
        self.chat.append(ChatMessage("assistant", result.message))
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
        playback_scene = session.scene
        before = (
            session.runtime.checkpoint()
            if session.runtime is not None
            else SimExecutor(
                session.state,
                session.scene,
                active_agent_ids=session.active_team,
            ).checkpoint()
        )
        audit = advance_online_session(session, mode=self.mode)
        playback = None
        playback_error = None
        observation_audit = None
        if session.runtime is not None:
            after = session.runtime.checkpoint()
            if after.now > before.now:
                try:
                    playback = build_playback_spec(
                        playback_scene,
                        before,
                        after,
                        frame_count=self.frame_count,
                    )
                except Exception as exc:  # noqa: BLE001 - committed state is preserved
                    playback_error = f"{type(exc).__name__}: {exc}"
        observation_responses: list[str] = []
        if isinstance(audit, CheckpointAudit) and self.observation_source is not None:
            revealed = self.observation_source.inspect(
                audit,
                session.runtime.assignments,
            )
            if revealed is None:
                revealed = ()
            elif isinstance(revealed, FireDetectedObservation):
                revealed = (revealed,)
            for observation in revealed:
                observation_audit = apply_fire_observation(
                    session,
                    observation,
                    mode=self.mode,
                )
                observation_responses.append(
                    f"[SIMULATED SENSOR · {observation.fixture_id}] "
                    f"{observation.zone_id} FIRE_DETECTED → "
                    f"{observation_audit.outcome}"
                )
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
        for observation_response in observation_responses:
            self._record("[simulated sensor observation]", observation_response)
        self._persist()
        return AdvancePresentation(audit, playback, playback_error, observation_audit)

    @property
    def scenario_label(self) -> str:
        return self.profile.label

    @property
    def fixture_id(self) -> str | None:
        source = self.observation_source
        if isinstance(source, SimulatedFireField):
            return source.fire_field.field_id
        if isinstance(source, SimulatedFireSource):
            return source.fixture.fixture_id
        return None

    @property
    def mock_commands(self) -> tuple[str, ...]:
        if self.profile.mock_script is None:
            return ()
        return commands_for_script(self.profile.mock_script)

    @property
    def live_examples(self) -> tuple[str, ...]:
        return self.profile.live_examples

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
    "DYNAMIC_LIVE_EXAMPLES",
    "DesktopController",
    "OPERATOR_LIVE_EXAMPLES",
    "SCENARIO_PROFILES",
    "SENSOR_LIVE_EXAMPLES",
    "SUPPORTED_MODES",
    "SUPPORTED_SCENARIOS",
]
