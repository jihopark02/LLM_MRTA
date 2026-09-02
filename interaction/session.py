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

from dataclasses import dataclass, field, replace
from enum import Enum

from allocation.allocate import AllocationResult
from core.enums import TaskStatus, TaskType
from core.mission_state import MissionState
from core.task_graph import TaskGraph
from execution.executor import ExecutionResult
from interaction.workflow import WORKFLOW_CHAIN
from scenarios.scene import Scene

#: A referent stays resolvable for this many turns, counting the current one
#: (§18.5). Small on purpose: an operator saying "거기" means something they
#: just mentioned, not something from five turns ago.
REFERENT_WINDOW_TURNS = 3


class SessionPhase(str, Enum):
    PLANNING = "PLANNING"
    EXECUTED = "EXECUTED"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class ReferentKind(str, Enum):
    INCIDENT = "incident"
    ZONE = "zone"


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


@dataclass(slots=True)
class MissionSession:
    session_id: str
    scene: Scene
    state: MissionState | None = None            # None until the first NEW_MISSION
    plan: AllocationResult | None = None         # last plan-time re-analysis
    execution: ExecutionResult | None = None     # set once the operator runs it
    phase: SessionPhase = SessionPhase.PLANNING
    recent_referents: list[Referent] = field(default_factory=list)
    turn_count: int = 0
    turn_log: list[dict] = field(default_factory=list)

    # -- derived (never stored, D-027) ---------------------------------
    @property
    def known_incident_ids(self) -> list[str]:
        return sorted(self.scene.incidents)

    def context_for_llm(self) -> str:
        return build_context_summary(self)

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
        "ZONES: " + ", ".join(sorted(scene.zones)),
        "INCIDENTS:",
    ]
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
    "SessionPhase",
    "ReferentKind",
    "Referent",
    "MissionSession",
    "fresh_session_state",
    "build_context_summary",
]
