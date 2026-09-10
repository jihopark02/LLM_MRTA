"""Strict human-authored gold dialogues for P8.4 (contract §18.11, D-035..D-037).

**Frozen legacy artifact (D-076 S11).** These 12 dialogues and their results
(``docs/P8_4_RESULTS.md``, ``data/eval_results/p8_4_*``) are the historical
evaluation of the pre-D-076 flat-slot interaction architecture — in particular
the resumable-ambiguous-``UPDATE_MISSION`` flow that D-076 S8 deliberately
removed. The YAML gold is not migrated to the Semantic Mission IR: doing so
would change what the recorded 6/12 end-to-end and 12/12 grounder-only numbers
mean. The loader below still validates the old intent shape against a frozen
key allowlist rather than the live ``IntentEnvelope`` for that reason. D-076's
own evaluation is a separate Explicit / Compositional / Contextual set, frozen
before results.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from evaluation.annotations import RefGraph, expand_graph_spec
from interaction.ground import ClarificationReason, GroundingStatus, ResolutionVia
from interaction.orchestrator import TurnOutcome
from interaction.scene_mut import register_incident
from scenarios.scene import Scene
from validator.candidate import TaskKey
from validator.validate import validate_candidate

# Frozen pre-D-076 intent shape (S11) — validated here instead of the live
# IntentEnvelope, which now carries a Semantic Mission IR these gold files predate.
_LEGACY_INTENT_KINDS = {
    "NEW_MISSION", "REPORT_INCIDENT", "UPDATE_MISSION",
    "UPDATE_RESOURCES", "QUERY_STATUS", "UNSUPPORTED",
}
_LEGACY_INTENT_SLOTS = {
    "kind", "zone_ref", "target_phrase", "up_to_step", "response_up_to",
    "incident_response_up_to", "about", "note",
}


def _legacy_intent(intent: dict, label: str) -> dict:
    if intent.get("kind") not in _LEGACY_INTENT_KINDS:
        raise ValueError(f"{label}.intent has an unknown kind {intent.get('kind')!r}")
    extra = set(intent) - _LEGACY_INTENT_SLOTS
    if extra:
        raise ValueError(f"{label}.intent has invalid keys {sorted(extra)}")
    return {key: value for key, value in intent.items() if value is not None}


_DIR = Path(__file__).resolve().parents[1] / "data" / "interaction_dialogues"
CASE_IDS = tuple(f"{family}{number}" for family in "ABC" for number in range(1, 5))
_PROFILE = {"A": "FULL_RESPONSE", "B": "AERIAL_ONLY", "C": "SELECTIVE_RESPONSE"}
_SHAPE = {
    1: "NEW_ONLY",
    2: "REPORT_UPDATE",
    3: "QUERY",
    4: "AMBIGUOUS_SELECTION",
}
_TOP_KEYS = {
    "id",
    "family",
    "profile",
    "shape",
    "rationale",
    "turns",
    "initial_graph",
    "final_graph",
}
_GROUNDING_KEYS = {"status", "entity_kind", "entity_id", "via", "reason", "candidates"}
_PATCH_KEYS = {"accepted", "added_tasks", "added_edges", "directly_released_tasks"}


@dataclass(frozen=True, slots=True)
class ExpectedGrounding:
    status: str
    entity_kind: str | None = None
    entity_id: str | None = None
    via: str | None = None
    reason: str | None = None
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExpectedPatch:
    accepted: bool
    added_tasks: tuple[str, ...]
    added_edges: tuple[tuple[str, str], ...]
    directly_released_tasks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DialogueTurn:
    input_kind: str
    outcome: str
    utterance: str | None = None
    entity_id: str | None = None
    intent: dict[str, str] | None = None
    grounding: ExpectedGrounding | None = None
    patch: ExpectedPatch | None = None


@dataclass(frozen=True, slots=True)
class DialogueAnnotation:
    id: str
    family: str
    profile: str
    shape: str
    rationale: str
    turns: tuple[DialogueTurn, ...]
    initial_graph: RefGraph
    final_graph: RefGraph


def _exact_keys(raw: object, expected: set[str], label: str) -> dict:
    if not isinstance(raw, dict) or set(raw) != expected:
        actual = sorted(raw) if isinstance(raw, dict) else type(raw).__name__
        raise ValueError(f"{label}: keys {actual!r} != {sorted(expected)!r}")
    return raw


def _strings(raw: object, label: str, *, unique: bool = True) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
        raise ValueError(f"{label} must be a list of non-empty strings")
    values = tuple(raw)
    if unique and len(set(values)) != len(values):
        raise ValueError(f"{label} contains duplicates")
    return values


def _grounding(raw: object, label: str) -> ExpectedGrounding:
    if not isinstance(raw, dict) or not set(raw) <= _GROUNDING_KEYS or "status" not in raw:
        raise ValueError(f"{label} has invalid grounding keys")
    status = GroundingStatus(raw["status"])
    kind = raw.get("entity_kind")
    if kind is not None and kind not in {"zone", "incident"}:
        raise ValueError(f"{label}.entity_kind is invalid")
    entity_id = raw.get("entity_id")
    if entity_id is not None and (not isinstance(entity_id, str) or not entity_id):
        raise ValueError(f"{label}.entity_id must be a non-empty string")
    via = raw.get("via")
    if via is not None:
        ResolutionVia(via)
    reason = raw.get("reason")
    if reason is not None:
        ClarificationReason(reason)
    candidates = _strings(raw.get("candidates", []), f"{label}.candidates")
    if status is GroundingStatus.RESOLVED:
        if entity_id is None or kind is None or via is None or reason is not None or candidates:
            raise ValueError(f"{label}: inconsistent RESOLVED grounding")
    elif reason is None or entity_id is not None or via is not None:
        raise ValueError(f"{label}: inconsistent CLARIFICATION_REQUIRED grounding")
    return ExpectedGrounding(status.value, kind, entity_id, via, reason, candidates)


def _patch(raw: object, label: str) -> ExpectedPatch:
    item = _exact_keys(raw, _PATCH_KEYS, label)
    if not isinstance(item["accepted"], bool):
        raise ValueError(f"{label}.accepted must be bool")
    tasks = _strings(item["added_tasks"], f"{label}.added_tasks")
    released = _strings(
        item["directly_released_tasks"], f"{label}.directly_released_tasks"
    )
    raw_edges = item["added_edges"]
    if not isinstance(raw_edges, list):
        raise ValueError(f"{label}.added_edges must be a list")
    edges: list[tuple[str, str]] = []
    for edge in raw_edges:
        if (
            not isinstance(edge, list)
            or len(edge) != 2
            or not all(isinstance(endpoint, str) and endpoint for endpoint in edge)
        ):
            raise ValueError(f"{label}.added_edges contains an invalid edge")
        edges.append((edge[0], edge[1]))
    if len(set(edges)) != len(edges):
        raise ValueError(f"{label}.added_edges contains duplicates")
    return ExpectedPatch(item["accepted"], tasks, tuple(edges), released)


def _turn(raw: object, label: str) -> DialogueTurn:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a mapping")
    kind = raw.get("input_kind")
    if kind == "NATURAL_LANGUAGE":
        required = {"input_kind", "utterance", "intent", "outcome"}
        allowed = required | {"grounding", "patch"}
    elif kind == "CANDIDATE_SELECTION":
        required = {"input_kind", "entity_id", "outcome", "grounding"}
        allowed = required | {"patch"}
    else:
        raise ValueError(f"{label}.input_kind is invalid")
    if not required <= set(raw) or not set(raw) <= allowed:
        raise ValueError(f"{label} has invalid keys")
    TurnOutcome(raw["outcome"])

    utterance = raw.get("utterance")
    entity_id = raw.get("entity_id")
    intent = raw.get("intent")
    if kind == "NATURAL_LANGUAGE":
        if not isinstance(utterance, str) or not utterance.strip():
            raise ValueError(f"{label}.utterance must be non-empty")
        if not isinstance(intent, dict):
            raise ValueError(f"{label}.intent must be a mapping")
        intent = _legacy_intent(intent, label)
    elif not isinstance(entity_id, str) or not entity_id:
        raise ValueError(f"{label}.entity_id must be non-empty")
    return DialogueTurn(
        input_kind=kind,
        outcome=raw["outcome"],
        utterance=utterance,
        entity_id=entity_id,
        intent=intent,
        grounding=_grounding(raw["grounding"], label) if "grounding" in raw else None,
        patch=_patch(raw["patch"], label) if "patch" in raw else None,
    )


def _checked_graph(spec: object, scene: Scene, label: str) -> RefGraph:
    if not isinstance(spec, dict):
        raise ValueError(f"{label} must be a mapping")
    graph, candidate = expand_graph_spec(spec, scene)
    result = validate_candidate(candidate, scene)
    if not result.accepted:
        raise ValueError(f"{label} fails Validator: {[str(error) for error in result.errors]}")
    return graph


def _task_ids(tasks: frozenset[TaskKey]) -> set[str]:
    from scenarios.compiler import task_id_for

    return {task_id_for(task_type, target) for task_type, target in tasks}


def _edge_ids(graph: RefGraph) -> set[tuple[str, str]]:
    from scenarios.compiler import task_id_for

    return {
        (task_id_for(*predecessor), task_id_for(*successor))
        for predecessor, successor in graph.edges
    }


def load_dialogue(path: str | Path, scene: Scene) -> DialogueAnnotation:
    path = Path(path)
    raw = _exact_keys(yaml.safe_load(path.read_text(encoding="utf-8")), _TOP_KEYS, str(path))
    case_id = raw["id"]
    if not isinstance(case_id, str) or case_id not in CASE_IDS or path.stem != case_id:
        raise ValueError(f"{path}: invalid or mismatched id {case_id!r}")
    family, number = case_id[0], int(case_id[1])
    if raw["family"] != family or raw["profile"] != _PROFILE[family]:
        raise ValueError(f"{path}: family/profile mismatch")
    if raw["shape"] != _SHAPE[number]:
        raise ValueError(f"{path}: id/shape mismatch")
    if not isinstance(raw["rationale"], str) or not raw["rationale"].strip():
        raise ValueError(f"{path}: rationale must be non-empty")
    if not isinstance(raw["turns"], list) or not 2 <= len(raw["turns"]) <= 5:
        raise ValueError(f"{path}: turns must contain 2..5 entries")
    turns = tuple(_turn(turn, f"{path}: turns[{index}]") for index, turn in enumerate(raw["turns"]))
    if turns[0].intent is None or turns[0].intent.get("kind") != "NEW_MISSION":
        raise ValueError(f"{path}: first turn must be NEW_MISSION")

    initial = _checked_graph(raw["initial_graph"], scene, f"{path}: initial_graph")
    final_scene = scene
    for turn in turns:
        committed_report = (
            turn.intent
            and turn.intent.get("kind") == "REPORT_INCIDENT"
            and turn.outcome == "COMMITTED"
        )
        if committed_report:
            if turn.grounding is None or turn.grounding.entity_kind != "zone":
                raise ValueError(f"{path}: committed REPORT needs resolved zone gold")
            final_scene, _ = register_incident(final_scene, turn.grounding.entity_id)
    final = _checked_graph(raw["final_graph"], final_scene, f"{path}: final_graph")

    expected_added_tasks = set().union(
        *(set(turn.patch.added_tasks) for turn in turns if turn.patch), set()
    )
    expected_added_edges = set().union(
        *(set(turn.patch.added_edges) for turn in turns if turn.patch), set()
    )
    actual_added_tasks = _task_ids(final.tasks) - _task_ids(initial.tasks)
    actual_added_edges = _edge_ids(final) - _edge_ids(initial)
    if expected_added_tasks != actual_added_tasks:
        raise ValueError(f"{path}: patch task gold does not equal initial/final diff")
    if expected_added_edges != actual_added_edges:
        raise ValueError(f"{path}: patch edge gold does not equal initial/final diff")

    return DialogueAnnotation(
        case_id,
        family,
        raw["profile"],
        raw["shape"],
        " ".join(raw["rationale"].split()),
        turns,
        initial,
        final,
    )


def load_all_dialogues(
    scene: Scene, *, directory: str | Path = _DIR
) -> list[DialogueAnnotation]:
    directory = Path(directory)
    dialogues = [load_dialogue(directory / f"{case_id}.yaml", scene) for case_id in CASE_IDS]
    if [dialogue.id for dialogue in dialogues] != list(CASE_IDS):
        raise ValueError("interaction dialogue ids are incomplete or out of order")
    return dialogues


__all__ = [
    "CASE_IDS",
    "DialogueAnnotation",
    "DialogueTurn",
    "ExpectedGrounding",
    "ExpectedPatch",
    "load_dialogue",
    "load_all_dialogues",
]
