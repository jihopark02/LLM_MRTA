"""Typed audit records for the planning session (RESEARCH_CONTRACT.md §18.9).

Replaces the untyped ``turn_log: list[dict]`` scaffolding from P8.1a. Every
turn produces a ``TurnAudit``; pressing run produces an ``ExecutionAudit`` via
``interaction.execute``.

The point of these records is that a reader can reconstruct *why* a turn did
what it did: which intent, which slots, how the referent resolved, which patch
against which state, what the Validator said, and how the plan moved. Hash
policy follows §14 — ``patch_hash`` is ``None`` exactly when the operations
failed the field-level schema check and had no canonical form.
"""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class PlanAssignmentChanges:
    """Difference between two plan-time analyses (§18.9).

    NOT an in-execution reallocation — nothing is running during a planning
    session. ``changed`` is a task both plans assign, to different agents.
    """

    added: dict[str, str] = field(default_factory=dict)
    removed: dict[str, str] = field(default_factory=dict)
    changed: dict[str, list[str]] = field(default_factory=dict)  # task -> [before, after]

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    @staticmethod
    def between(
        before: dict[str, str] | None, after: dict[str, str] | None
    ) -> "PlanAssignmentChanges":
        before, after = before or {}, after or {}
        return PlanAssignmentChanges(
            added={t: a for t, a in after.items() if t not in before},
            removed={t: a for t, a in before.items() if t not in after},
            changed={
                t: [before[t], after[t]]
                for t in before.keys() & after.keys()
                if before[t] != after[t]
            },
        )


@dataclass(frozen=True, slots=True)
class GroundingAudit:
    status: str
    entity_kind: str | None = None
    entity_id: str | None = None
    via: str | None = None                      # §18.5 step: explicit|referent|sole_incident
    clarification: str | None = None
    candidates: list[str] = field(default_factory=list)
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class PatchAudit:
    accepted: bool
    error_codes: list[str] = field(default_factory=list)
    added_tasks: list[str] = field(default_factory=list)
    added_edges: list[list[str]] = field(default_factory=list)
    directly_released_tasks: list[str] = field(default_factory=list)
    status_changes: list[list[str]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GenerationAudit:
    approved: bool
    failure_category: str | None = None
    graph_hash: str = ""
    error_codes: list[str] = field(default_factory=list)
    repaired: bool = False


@dataclass(frozen=True, slots=True)
class RuntimeAssignmentChanges:
    """Assignment delta produced by an in-execution CBBA epoch (§19.4)."""

    added: dict[str, str] = field(default_factory=dict)
    removed: dict[str, str] = field(default_factory=dict)
    changed: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResourceResolutionAudit:
    """Requested constraints and deterministic P13 active-team result."""

    request: dict[str, object]
    active_team: list[str] = field(default_factory=list)
    previous_active_team: list[str] = field(default_factory=list)
    candidates_tested: int = 0
    error_code: str | None = None
    simulation_time: float | None = None
    released_tasks: list[str] = field(default_factory=list)
    deferred_exclusions: list[str] = field(default_factory=list)
    before_assignments: dict[str, str] = field(default_factory=dict)
    after_assignments: dict[str, str] = field(default_factory=dict)
    assignment_changes: RuntimeAssignmentChanges = field(
        default_factory=RuntimeAssignmentChanges
    )
    consensus_rounds: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class OnlineReallocationAudit:
    """Why an accepted paused UPDATE released and reassigned work (§19.4)."""

    policy: str
    policy_version: str
    simulation_time: float
    patch_added_tasks: list[str] = field(default_factory=list)
    directly_affected_tasks: list[str] = field(default_factory=list)
    selectively_released_tasks: list[str] = field(default_factory=list)
    preserved_active_assignments: dict[str, str] = field(default_factory=dict)
    before_assignments: dict[str, str] = field(default_factory=dict)
    after_assignments: dict[str, str] = field(default_factory=dict)
    assignment_changes: RuntimeAssignmentChanges = field(
        default_factory=RuntimeAssignmentChanges
    )
    consensus_rounds: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IncidentActionAudit:
    """How a newly known incident entered and selected its response (§22.3)."""

    source: str                              # OPERATOR | SENSOR_SIMULATED
    zone_id: str
    incident_id: str
    policy_origin: str                       # EXPLICIT | SESSION_POLICY | NONE
    response_up_to: str | None = None


@dataclass(frozen=True, slots=True)
class IncidentObservationAudit:
    """A simulated sensor observation and its atomic adaptation (§22.2/§22.3)."""

    session_id: str
    fixture_id: str
    zone_id: str
    trigger_task_id: str
    detecting_agent_id: str
    simulation_time: float
    mode: str
    outcome: str
    incident_id: str | None = None
    policy_origin: str = "NONE"
    response_up_to: str | None = None
    pre_scene_hash: str = ""
    post_scene_hash: str = ""
    pre_graph_hash: str | None = None
    post_graph_hash: str | None = None
    pre_state_hash: str | None = None
    patch_hash: str | None = None
    patch: PatchAudit | None = None
    online_reallocation: OnlineReallocationAudit | None = None
    error_type: str | None = None
    error_detail: str | None = None
    source: str = "SENSOR_SIMULATED"
    event_type: str = "INCIDENT_OBSERVATION"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TimingAudit:
    """Wall-clock split for one turn (§18.9, D-071). Measurement only.

    ``llm_calls`` is a list of ``[schema_name, seconds]`` pairs in call order —
    a list of lists (not tuples) so ``asdict`` round-trips cleanly through JSON.
    """

    total_s: float
    llm_total_s: float
    deterministic_s: float
    llm_calls: list = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TurnAudit:
    """One operator turn (§18.9, ``event_type: TURN``)."""

    session_id: str
    turn_id: str
    utterance: str
    mode: str                                   # live | cached | mock
    outcome: str                                # see orchestrator.TurnOutcome
    intent_kind: str | None = None
    extracted_slots: dict = field(default_factory=dict)
    grounding: GroundingAudit | None = None

    pre_scene_hash: str = ""
    post_scene_hash: str = ""
    pre_graph_hash: str | None = None           # None before the first mission
    post_graph_hash: str | None = None
    pre_state_hash: str | None = None
    patch_hash: str | None = None               # None on a field-schema failure

    patch: PatchAudit | None = None
    generation: GenerationAudit | None = None
    plan_assignment_changes: PlanAssignmentChanges | None = None
    online_reallocation: OnlineReallocationAudit | None = None
    incident_action: IncidentActionAudit | None = None
    resource_resolution: ResourceResolutionAudit | None = None

    scene_changed: bool = False
    state_changed: bool = False
    referent_noted: str | None = None
    resolved_models: list[str] = field(default_factory=list)
    intent_repair_attempted: bool = False
    intent_repair_recovered: bool = False
    answer: str | None = None
    # A TURN_ERROR's cause must survive in the permanent record, not only in
    # the returned TurnResult (D-029).
    error_type: str | None = None
    error_detail: str | None = None

    input_kind: str = "NATURAL_LANGUAGE"
    resumed_from_turn_id: str | None = None
    selected_entity_id: str | None = None
    timing: TimingAudit | None = None

    event_type: str = "TURN"

    def __post_init__(self) -> None:
        if self.intent_repair_recovered and not self.intent_repair_attempted:
            raise ValueError("intent repair cannot recover without being attempted")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutionAudit:
    """One press of run (§18.9, ``event_type: EXECUTION``).

    Execution is a deterministic UI action, never an LLM intent. Its producer
    is ``interaction.execute.execute_session``.
    """

    session_id: str
    pre_scene_hash: str
    pre_graph_hash: str
    plan_assignments: dict[str, str]
    execution_termination: str
    execution_assignments: dict[str, str]
    makespan: float
    capability_violations: list[str]
    precedence_violations: list[str]
    mode: str
    started_at: str
    finished_at: str
    error_type: str | None = None
    error_detail: str | None = None
    event_type: str = "EXECUTION"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CheckpointAudit:
    """One deterministic task-completion pause (§19.4)."""

    session_id: str
    simulation_time: float
    completed_now: list[str]
    completed: list[str]
    running: dict[str, dict[str, object]]
    ready_tasks: list[str]
    active_assignments: dict[str, str]
    mode: str
    event_type: str = "EXECUTION_CHECKPOINT"

    def to_dict(self) -> dict:
        return asdict(self)


__all__ = [
    "PlanAssignmentChanges",
    "GroundingAudit",
    "PatchAudit",
    "GenerationAudit",
    "ResourceResolutionAudit",
    "RuntimeAssignmentChanges",
    "OnlineReallocationAudit",
    "IncidentActionAudit",
    "IncidentObservationAudit",
    "TimingAudit",
    "TurnAudit",
    "ExecutionAudit",
    "CheckpointAudit",
]
