"""Planning-session state (RESEARCH_CONTRACT.md §18.5, §18.8).

A ``MissionSession`` is the whole operator-facing state of one pre-execution
planning conversation: the (possibly incident-augmented) scene, the committed
mission state, the last plan-time analysis, the execution result once the
operator has pressed run, and the structured referents the deterministic
grounder needs to resolve "그 화재".

Two things are deliberately **derived, never stored** (D-027): the known
incident ids come from ``scene.incidents``, and the LLM-facing context is built
from the structured session on every turn. Keeping copies of either would be a
second source of truth.

``fresh_session_state`` lives here rather than in ``core`` on purpose: ``core``
must not learn about ``Scene`` (§18.8). It exists because a long-lived session
must not share a mutable ``Agent`` with the scene — the P6.5 fork is unaffected
because ``allocate``/``SimExecutor`` clone their input immediately.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType

from allocation.allocate import AllocationResult
from core.enums import TaskStatus, TaskType
from core.mission_state import MissionState
from core.task_graph import TaskGraph
from execution.executor import ExecutionResult, SimExecutor
from interaction.audit import (
    CheckpointAudit,
    ExecutionAudit,
    IncidentObservationAudit,
    TurnAudit,
)
from interaction.directive import MissionDirective
from interaction.resources import ResourceRequest
from interaction.workflow import WORKFLOW_CHAIN
from scenarios.scene import Scene

#: A referent stays resolvable for this many turns, counting the current one
#: (§18.5). Small on purpose: an operator saying "거기" means something they
#: just mentioned, not something from five turns ago.
REFERENT_WINDOW_TURNS = 3


#: §18.9 / D-030. The session id becomes the audit filename, so a free string
#: would let "../" or an absolute path write outside the directory the contract
#: pins. Leading char is alphanumeric so an id can never be ".", ".." or look
#: like a flag; 64 chars keeps it inside filename limits.
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def valid_session_id(value: object) -> bool:
    """Whether ``value`` is a usable session id (D-030).

    ``fullmatch``, not ``match``: Python anchors ``$`` before a trailing
    newline too, so ``"S1\n"`` would otherwise pass and D-030 rules out
    whitespace. Shared by the ``MissionSession`` constructor and
    ``audit_path`` so the rule cannot drift between them.
    """
    return isinstance(value, str) and SESSION_ID_PATTERN.fullmatch(value) is not None


class SessionPhase(str, Enum):
    PLANNING = "PLANNING"
    EXECUTION_PAUSED = "EXECUTION_PAUSED"
    EXECUTED = "EXECUTED"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class ReferentKind(str, Enum):
    INCIDENT = "incident"
    ZONE = "zone"


@dataclass(frozen=True, slots=True)
class PendingClarification:
    """A resumable entity ambiguity (contract §18.13, D-031/D-032)."""

    source_turn_id: str
    intent_kind: str
    extracted_slots: Mapping[str, str]
    unresolved_slot: str
    entity_kind: ReferentKind
    candidates: tuple[str, ...]
    original_utterance: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"t[1-9][0-9]*", self.source_turn_id):
            raise ValueError(f"invalid source_turn_id: {self.source_turn_id!r}")
        if self.intent_kind not in {
            "REPORT_INCIDENT",
            "UPDATE_MISSION",
            "QUERY_STATUS",
        }:
            raise ValueError(f"intent cannot resume a clarification: {self.intent_kind!r}")
        if self.unresolved_slot not in {"zone_ref", "target_phrase"}:
            raise ValueError(f"invalid unresolved_slot: {self.unresolved_slot!r}")
        if not isinstance(self.entity_kind, ReferentKind):
            raise ValueError("entity_kind must be a ReferentKind")
        if len(self.candidates) < 2 or len(set(self.candidates)) != len(self.candidates):
            raise ValueError("candidates must contain at least two distinct entity ids")
        if not all(isinstance(candidate, str) and candidate for candidate in self.candidates):
            raise ValueError("every clarification candidate must be a non-empty str")
        if not isinstance(self.original_utterance, str):
            raise ValueError("original_utterance must be a str")
        slots = dict(self.extracted_slots)
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in slots.items()):
            raise ValueError("extracted_slots must map strings to strings")
        expected = (
            ("zone_ref", ReferentKind.ZONE)
            if self.intent_kind == "REPORT_INCIDENT"
            else ("target_phrase", ReferentKind.INCIDENT)
        )
        if (self.unresolved_slot, self.entity_kind) != expected:
            raise ValueError("intent, unresolved_slot and entity_kind do not agree")
        if self.unresolved_slot not in slots:
            raise ValueError("the unresolved slot must be preserved in extracted_slots")
        if self.intent_kind == "UPDATE_MISSION" and "up_to_step" not in slots:
            raise ValueError("an UPDATE clarification also needs up_to_step")
        object.__setattr__(self, "candidates", tuple(sorted(self.candidates)))
        object.__setattr__(self, "extracted_slots", MappingProxyType(slots))


def _require_turn(value: object, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative int, got {value!r}")


@dataclass(frozen=True, slots=True)
class Referent:
    """An entity the operator can later point at with a pronoun.

    Validated on construction: whatever ends up here is quoted verbatim into
    the LLM context (§18.3), so a made-up kind or id must never get this far.
    Scene membership is checked by ``MissionSession.note_referent``, which is
    the only place that knows the scene.
    """

    entity_kind: ReferentKind
    entity_id: str
    introduced_turn: int

    def __post_init__(self) -> None:
        if not isinstance(self.entity_kind, ReferentKind):
            raise ValueError(f"entity_kind must be a ReferentKind, got {self.entity_kind!r}")
        if not isinstance(self.entity_id, str) or not self.entity_id:
            raise ValueError(f"entity_id must be a non-empty str, got {self.entity_id!r}")
        _require_turn(self.introduced_turn, "introduced_turn")


def fresh_session_state(graph: TaskGraph, scene: Scene) -> MissionState:
    """A ``MissionState`` that shares no mutable object with ``scene`` (§18.8).

    The scene's ``fleet`` is a template; the session gets its own ``Agent``
    copies (with their own bundle/path lists) and its own graph clone, so a
    later allocation can never write back into the scene.
    """
    return MissionState(
        graph=graph.clone(),
        agents={
            a.agent_id: replace(a, bundle=list(a.bundle), path=list(a.path))
            for a in scene.fleet
        },
    )


class ApprovalDecision(str, Enum):
    APPROVE = "APPROVE"
    DECLINE = "DECLINE"


@dataclass(frozen=True, slots=True)
class PendingFireApproval:
    """A revealed sensor fire and the operator's recorded answer (§22.8, D-065/D-066).

    A resumable pending interaction like :class:`PendingClarification`: it gates
    autoplay and the free-text queue without introducing a new ``SessionPhase``.
    The observation fields mirror ``scenarios.latent.FireDetectedObservation``.
    ``decision`` stays ``None`` until the operator answers; the answer is applied
    at the next task-completion boundary (D-066), never mid-segment.
    """

    fixture_id: str
    zone_id: str
    trigger_task_id: str
    detecting_agent_id: str
    simulation_time: float
    decision: ApprovalDecision | None = None
    approved_scope: TaskType | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("fixture_id", self.fixture_id),
            ("zone_id", self.zone_id),
            ("trigger_task_id", self.trigger_task_id),
            ("detecting_agent_id", self.detecting_agent_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be a non-empty str")
        if (
            not isinstance(self.simulation_time, (int, float))
            or isinstance(self.simulation_time, bool)
            or self.simulation_time < 0.0
        ):
            raise ValueError("simulation_time must be a non-negative number")
        if self.decision is not None and not isinstance(self.decision, ApprovalDecision):
            raise ValueError("decision must be an ApprovalDecision or None")
        if self.decision is ApprovalDecision.APPROVE:
            if self.approved_scope not in WORKFLOW_CHAIN:
                raise ValueError("an approved fire needs a workflow scope")
        elif self.approved_scope is not None:
            raise ValueError("only an APPROVE decision carries a scope")

    @property
    def decided(self) -> bool:
        return self.decision is not None


@dataclass(slots=True)
class MissionSession:
    session_id: str
    scene: Scene
    state: MissionState | None = None            # None until the first NEW_MISSION
    plan: AllocationResult | None = None         # last plan-time re-analysis
    execution: ExecutionResult | None = None     # set once the operator runs it
    runtime: SimExecutor | None = field(default=None, repr=False)
    online_started_at: str | None = None
    phase: SessionPhase = SessionPhase.PLANNING
    directive: MissionDirective = field(default_factory=MissionDirective)
    resource_request: ResourceRequest = field(default_factory=ResourceRequest)
    active_team: tuple[str, ...] = ()
    recent_referents: list[Referent] = field(default_factory=list)
    turn_count: int = 0
    pending_clarification: PendingClarification | None = None
    pending_approvals: tuple[PendingFireApproval, ...] = ()
    _event_log: list[
        TurnAudit | ExecutionAudit | CheckpointAudit | IncidentObservationAudit
    ] = field(
        default_factory=list, init=False, repr=False
    )

    def __post_init__(self) -> None:
        # An input boundary, not a formatting preference (D-030): this value is
        # the audit filename and is copied into every TurnAudit, so it is
        # checked once here rather than at each use.
        if not valid_session_id(self.session_id):
            raise ValueError(
                f"session_id must match {SESSION_ID_PATTERN.pattern!r} exactly, "
                f"got {self.session_id!r}"
            )
        if not isinstance(self.resource_request, ResourceRequest):
            raise ValueError("resource_request must be a ResourceRequest")
        self.resource_request.validate_scene(self.scene)
        if self.active_team:
            if not isinstance(self.active_team, tuple) or not all(
                isinstance(agent_id, str) and agent_id for agent_id in self.active_team
            ):
                raise ValueError("active_team must be a tuple of non-empty agent ids")
            if len(self.active_team) != len(set(self.active_team)):
                raise ValueError("active_team contains duplicate agent ids")
            unknown = set(self.active_team) - {agent.agent_id for agent in self.scene.fleet}
            if unknown:
                raise ValueError(f"active_team contains unknown agents: {sorted(unknown)}")
            if self.state is not None and not set(self.active_team) <= set(self.state.agents):
                raise ValueError("active_team must be a subset of the mission-state roster")
            self.active_team = tuple(sorted(self.active_team))
        elif self.state is not None:
            # Legacy/test constructors predate P13. Their state already owns
            # the authoritative executable team, so adopt it deterministically.
            self.active_team = tuple(sorted(self.state.agents))

    # -- derived (never stored, D-027) ---------------------------------
    @property
    def known_incident_ids(self) -> list[str]:
        return sorted(self.scene.incidents)

    def context_for_llm(self) -> str:
        return build_context_summary(self)

    # -- chronological audit stream (§18.9, D-031/D-032) -------------
    @property
    def event_log(
        self,
    ) -> tuple[TurnAudit | ExecutionAudit | CheckpointAudit | IncidentObservationAudit, ...]:
        return tuple(self._event_log)

    @property
    def turn_log(self) -> tuple[TurnAudit, ...]:
        return tuple(event for event in self._event_log if isinstance(event, TurnAudit))

    def append_event(
        self,
        event: TurnAudit | ExecutionAudit | CheckpointAudit | IncidentObservationAudit,
    ) -> None:
        if not isinstance(
            event,
            (TurnAudit, ExecutionAudit, CheckpointAudit, IncidentObservationAudit),
        ):
            raise TypeError(f"unsupported session event: {type(event).__name__}")
        if event.session_id != self.session_id:
            raise ValueError(
                f"event session_id {event.session_id!r} does not match {self.session_id!r}"
            )
        self._event_log.append(event)

    # -- referents (§18.5) ---------------------------------------------
    def note_referent(self, entity_kind: ReferentKind | str, entity_id: str) -> None:
        """Record a successfully grounded entity. Callers must only do this for
        a successful REPORT / a properly grounded UPDATE / a QUERY on an
        explicit incident — never for a clarification, an UNSUPPORTED turn, an
        ambiguous referent, or a failed operation (§18.5).

        The entity must exist in the current scene: this list is quoted into
        the LLM context, so it is an input boundary, not a scratch pad. Raises
        ``ValueError`` and leaves ``recent_referents`` untouched otherwise.
        """
        kind = ReferentKind(entity_kind)  # ValueError on anything else
        known = self.scene.incidents if kind is ReferentKind.INCIDENT else self.scene.zones
        if entity_id not in known:
            raise ValueError(f"unknown {kind.value} referent: {entity_id!r}")
        _require_turn(self.turn_count, "turn_count")

        self.recent_referents.append(Referent(kind, entity_id, self.turn_count))
        self._prune_referents()

    def _prune_referents(self) -> None:
        oldest_live = self.turn_count - (REFERENT_WINDOW_TURNS - 1)
        self.recent_referents = [
            r for r in self.recent_referents if r.introduced_turn >= oldest_live
        ]

    def live_referents(self, entity_kind: str | None = None) -> list[Referent]:
        """Referents still inside the K-turn window, oldest first."""
        oldest_live = self.turn_count - (REFERENT_WINDOW_TURNS - 1)
        return [
            r
            for r in self.recent_referents
            if r.introduced_turn >= oldest_live
            and (entity_kind is None or r.entity_kind == entity_kind)
        ]

    def latest_referent_candidates(self, entity_kind: str) -> list[str]:
        """Distinct entity ids introduced on the most recent turn that
        introduced any. Two or more means the referent is ambiguous and the
        grounder must ask instead of picking one (§18.5)."""
        live = self.live_referents(entity_kind)
        if not live:
            return []
        newest = max(r.introduced_turn for r in live)
        return sorted({r.entity_id for r in live if r.introduced_turn == newest})


# -- deterministic LLM-facing context (§18.3) --------------------------


def _mission_lines(state: MissionState | None) -> list[str]:
    if state is None:
        return ["MISSION: none"]
    graph = state.graph
    lines = [f"MISSION: {len(graph)} tasks, {len(graph.edges)} edges"]

    recon = sorted(t.target for t in graph.tasks if t.task_type is TaskType.AREA_RECON)
    if recon:
        lines.append("  AREA_RECON: " + ", ".join(recon))

    per_incident: dict[str, set[TaskType]] = {}
    for task in graph.tasks:
        if task.task_type is not TaskType.AREA_RECON:
            per_incident.setdefault(task.target, set()).add(task.task_type)
    for target in sorted(per_incident):
        steps = [s.value for s in WORKFLOW_CHAIN if s in per_incident[target]]
        lines.append(f"  {target}: " + " -> ".join(steps))

    counts = [
        f"{status.value} {len(graph.ids_with_status(status))}"
        for status in TaskStatus
        if graph.ids_with_status(status)
    ]
    lines.append("  status: " + ", ".join(counts))
    return lines


def build_context_summary(session: MissionSession) -> str:
    """The only session context the LLM ever sees (§18.3, §18.7).

    Built from the structured session every turn — never the raw transcript —
    so the same session always yields the same string.
    """
    scene = session.scene
    lines = [
        f"PHASE: {session.phase.value}",
        "INCIDENT_RESPONSE_POLICY: "
        + (
            session.directive.incident_response_up_to.value
            if session.directive.incident_response_up_to is not None
            else "none"
        ),
        "RESOURCE_REQUEST: "
        + json.dumps(session.resource_request.to_dict(), sort_keys=True, ensure_ascii=False),
        "ACTIVE_TEAM: " + (", ".join(session.active_team) if session.active_team else "none"),
        "ZONES: " + ", ".join(sorted(scene.zones)),
        "INCIDENTS:",
    ]
    if session.runtime is not None:
        lines.insert(1, f"SIMULATION_TIME: {session.runtime.now:.6f}")
    if scene.incidents:
        for iid in sorted(scene.incidents):
            inc = scene.incidents[iid]
            lines.append(
                f"  {iid} (zone {inc.zone}, priority {inc.priority}, {inc.status.value})"
            )
    else:
        lines.append("  (none registered)")

    lines += _mission_lines(session.state)

    live = session.live_referents()
    if live:
        lines.append(
            "RECENT REFERENTS: "
            + ", ".join(
                f"{r.entity_id} ({r.entity_kind.value}, turn {r.introduced_turn})"
                for r in live
            )
        )
    else:
        lines.append("RECENT REFERENTS: none")
    return "\n".join(lines)


__all__ = [
    "REFERENT_WINDOW_TURNS",
    "SESSION_ID_PATTERN",
    "valid_session_id",
    "SessionPhase",
    "ReferentKind",
    "Referent",
    "PendingClarification",
    "ApprovalDecision",
    "PendingFireApproval",
    "MissionSession",
    "fresh_session_state",
    "build_context_summary",
]
