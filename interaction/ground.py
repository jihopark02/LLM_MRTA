"""Deterministic grounding for the planning session (RESEARCH_CONTRACT.md §18.5, §18.7).

The LLM classifies and extracts slots; **this module decides what those slots
actually refer to**, and it is the only thing that ever produces a
``CLARIFICATION_REQUIRED`` (§18.7). That split is deliberate: clarification
quality is then a property of code we can test exhaustively, not of a prompt.

Nothing here mutates a session, a scene or a graph. Callers apply the result.

Resolution precedence for an incident referent:

1. the phrase names a known incident id           -> RESOLVED
2. the phrase has the shape of an incident id but
   names none of them                             -> CLARIFICATION (unknown)
3. no incident is registered at all               -> CLARIFICATION (§18 example 1)
4. referents introduced on the most recent live
   turn: exactly one -> RESOLVED, two or more     -> CLARIFICATION (§18 example 4)
5. no live referent: exactly one incident exists   -> RESOLVED (nothing to
   choose between); two or more                    -> CLARIFICATION

Rule 5 is the one judgement call: with a single registered incident there is no
ambiguity to resolve, so asking would be pedantic. Every resolution is reported
with the concrete id so the operator sees which one was used (§18 example 2).
"""

import re
from dataclasses import dataclass
from enum import Enum

from core.enums import TaskType
from core.task_graph import TaskGraph
from interaction.schemas import UpToStep
from interaction.session import MissionSession, ReferentKind
from interaction.workflow import WORKFLOW_CHAIN
from scenarios.scene import Scene
from validator.patch import AddEdge, AddTask, MissionPatch

_INCIDENT_SHAPE = re.compile(r"^FIRE[_ ]?SITE[_ ]?[0-9]*$", re.IGNORECASE)
_ZONE_SUFFIXES = ("구역", "지역")


class GroundingStatus(str, Enum):
    RESOLVED = "RESOLVED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class GroundingOutcome:
    status: GroundingStatus
    entity_kind: ReferentKind | None = None
    entity_id: str | None = None
    clarification: str | None = None
    candidates: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.status is GroundingStatus.RESOLVED


def _resolved(kind: ReferentKind, entity_id: str) -> GroundingOutcome:
    return GroundingOutcome(GroundingStatus.RESOLVED, kind, entity_id)


def _clarify(question: str, candidates: tuple[str, ...] = ()) -> GroundingOutcome:
    return GroundingOutcome(
        GroundingStatus.CLARIFICATION_REQUIRED, clarification=question, candidates=candidates
    )


def _normalize(text: str) -> str:
    """Uppercase, drop everything but letters and digits.

    A trailing Korean zone word is removed first so "A 구역" and "ZONE_A" and
    "Warehouse" all reduce to something matchable.
    """
    stripped = text.strip()
    for suffix in _ZONE_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)]
            break
    return "".join(ch for ch in stripped.upper() if ch.isalnum())


# -- zones -------------------------------------------------------------


def _zone_aliases(scene: Scene) -> dict[str, set[str]]:
    """zone_id -> the normalized forms that name it.

    Three deterministic forms: the id ("ZONE_A" -> "ZONEA"), its bare suffix
    ("A"), and the human name ("Processing Area" -> "PROCESSINGAREA").
    """
    aliases: dict[str, set[str]] = {}
    for zone_id, zone in scene.zones.items():
        forms = {_normalize(zone_id), _normalize(zone.name)}
        _, _, suffix = zone_id.partition("_")
        if suffix:
            forms.add(_normalize(suffix))
        aliases[zone_id] = {f for f in forms if f}
    return aliases


def resolve_zone(scene: Scene, zone_ref: str | None) -> GroundingOutcome:
    """Match a raw zone phrase to a scene zone (§18.7). No LLM."""
    known = sorted(scene.zones)
    if not zone_ref or not _normalize(zone_ref):
        return _clarify("어느 구역입니까?", tuple(known))

    needle = _normalize(zone_ref)
    hits = sorted(zid for zid, forms in _zone_aliases(scene).items() if needle in forms)
    if len(hits) == 1:
        return _resolved(ReferentKind.ZONE, hits[0])
    if len(hits) > 1:  # no scene has this today; never guess if one ever does
        return _clarify(
            f"'{zone_ref}'에 해당하는 구역이 여러 개입니다. 어느 쪽입니까?", tuple(hits)
        )
    return _clarify(f"'{zone_ref}'에 해당하는 구역을 찾을 수 없습니다.", tuple(known))


# -- incidents ---------------------------------------------------------


def resolve_incident(session: MissionSession, target_phrase: str | None) -> GroundingOutcome:
    """Resolve an incident referent against the scene and the session (§18.5)."""
    known = session.known_incident_ids
    by_normalized = {_normalize(iid): iid for iid in known}

    if target_phrase:
        needle = _normalize(target_phrase)
        if needle in by_normalized:
            return _resolved(ReferentKind.INCIDENT, by_normalized[needle])
        if _INCIDENT_SHAPE.match(target_phrase.strip()):
            # Named something specific that does not exist — do not silently
            # fall through to whatever was mentioned last.
            return _clarify(
                f"'{target_phrase}'에 해당하는 화재 지점을 찾을 수 없습니다.", tuple(known)
            )

    if not known:
        return _clarify("현재 등록된 화재 지점이 없습니다. 먼저 화재를 보고해 주세요.")

    candidates = session.latest_referent_candidates(ReferentKind.INCIDENT)
    if len(candidates) == 1:
        return _resolved(ReferentKind.INCIDENT, candidates[0])
    if len(candidates) > 1:
        return _clarify("어느 화재 지점을 말씀하시는 것입니까?", tuple(candidates))

    if len(known) == 1:
        return _resolved(ReferentKind.INCIDENT, known[0])
    return _clarify("어느 화재 지점을 말씀하시는 것입니까?", tuple(known))


# -- canonical chain patch (§18.6) -------------------------------------


@dataclass(frozen=True, slots=True)
class PatchPlan:
    """What an UPDATE would change. ``patch is None`` means NO_CHANGE (§18.6)."""

    patch: MissionPatch | None
    added_steps: tuple[TaskType, ...] = ()
    added_edges: tuple[tuple[TaskType, TaskType], ...] = ()
    note: str = ""

    @property
    def no_change(self) -> bool:
        return self.patch is None


def chain_prefix(up_to_step: UpToStep) -> tuple[TaskType, ...]:
    """The contiguous §4 workflow prefix ending at ``up_to_step``."""
    step = TaskType(up_to_step)
    return WORKFLOW_CHAIN[: WORKFLOW_CHAIN.index(step) + 1]


def build_chain_patch(
    graph: TaskGraph, incident_id: str, up_to_step: UpToStep
) -> PatchPlan:
    """The canonical patch that extends ``incident_id``'s response to a step.

    Only ever a canonical chain extension — the one patch shape the fixed
    vocabulary admits (D-006). If every task and edge of the requested prefix
    is already there, the answer is NO_CHANGE rather than a duplicate AddTask
    that the Validator would reject, or an empty patch reported as a commit
    (§18.6). A request for a *shorter* prefix than what exists is the same
    case: nothing is removed in this scope.
    """
    prefix = chain_prefix(up_to_step)
    present = {
        task.task_type for task in graph.tasks if task.target == incident_id
    }
    existing_edges = {
        (graph[p].task_type, graph[s].task_type)
        for p, s in graph.edges
        if graph[p].target == incident_id and graph[s].target == incident_id
    }

    missing_tasks = tuple(step for step in prefix if step not in present)
    missing_edges = tuple(
        (a, b)
        for a, b in zip(prefix, prefix[1:], strict=False)
        if (a, b) not in existing_edges
    )

    if not missing_tasks and not missing_edges:
        return PatchPlan(
            patch=None,
            note=f"{incident_id}의 {TaskType(up_to_step).value}까지는 이미 계획에 포함돼 있습니다.",
        )

    operations: list = [AddTask(step, incident_id) for step in missing_tasks]
    operations += [
        AddEdge((a, incident_id), (b, incident_id)) for a, b in missing_edges
    ]
    added = ", ".join(step.value for step in missing_tasks) or "(edges only)"
    return PatchPlan(
        patch=MissionPatch(operations),
        added_steps=missing_tasks,
        added_edges=missing_edges,
        note=f"{incident_id}에 {added} 추가.",
    )


__all__ = [
    "GroundingStatus",
    "GroundingOutcome",
    "PatchPlan",
    "resolve_zone",
    "resolve_incident",
    "chain_prefix",
    "build_chain_patch",
]
