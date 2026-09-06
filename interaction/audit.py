"""Typed audit records for the planning session (RESEARCH_CONTRACT.md §18.9).

Replaces the untyped ``turn_log: list[dict]`` scaffolding from P8.1a. Every
turn produces a ``TurnAudit``; pressing run will produce an ``ExecutionAudit``
(its producer arrives with the execute action in P8.3 — the schema is fixed
here because §18.9 specifies it).

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

    scene_changed: bool = False
    state_changed: bool = False
    referent_noted: str | None = None
    resolved_models: list[str] = field(default_factory=list)
    answer: str | None = None
    # A TURN_ERROR's cause must survive in the permanent record, not only in
    # the returned TurnResult (D-029).
    error_type: str | None = None
    error_detail: str | None = None

    event_type: str = "TURN"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutionAudit:
    """One press of run (§18.9, ``event_type: EXECUTION``).

    Execution is a deterministic UI action, never an LLM intent. The producer
    arrives with the execute action in P8.3; the shape is fixed here.
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
    event_type: str = "EXECUTION"

    def to_dict(self) -> dict:
        return asdict(self)


__all__ = [
    "PlanAssignmentChanges",
    "GroundingAudit",
    "PatchAudit",
    "GenerationAudit",
    "TurnAudit",
    "ExecutionAudit",
]
