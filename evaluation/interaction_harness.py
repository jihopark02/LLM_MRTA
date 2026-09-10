"""P8.4 operator-interaction evaluation harness (contract §18.11).

**Frozen legacy (D-076 S11).** The grounder-only track replays the pre-D-076
flat-slot gold intents through the orchestrator; that path (resumable ambiguous
``UPDATE_MISSION``) was removed by D-076 S8, so this harness no longer runs
against the current system. Kept for provenance of the recorded P8.4 numbers.


The two evaluation tracks deliberately share the same scoring code:

``grounder-only``
    Inject the human-authored intent/slots and initial graph through a fresh
    ``MockBackend`` for every dialogue.  The real orchestrator, deterministic
    grounder, patch builder, Validator and allocator still run.  This is a
    compiler regression gate, not an LLM metric.

``end-to-end``
    Give only the raw utterance to a fresh backend for every dialogue.  A
    structured candidate click is still deterministic and makes no LLM call.

Earlier failures never make later gold turns disappear.  If a later turn can
no longer run (for example, there is no pending clarification to select), the
turn is retained with a harness error and is scored as incorrect.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter

from core.enums import TaskType
from evaluation.interaction_annotations import (
    DialogueAnnotation,
    DialogueTurn,
    ExpectedGrounding,
    ExpectedPatch,
)
from interaction.audit import GroundingAudit, PatchAudit, TurnAudit
from interaction.audit_io import session_audit_payload
from interaction.orchestrator import (
    TurnResult,
    handle_turn,
    select_clarification_candidate,
)
from interaction.schemas import wire_intent
from interaction.session import MissionSession
from llm.backend import MockBackend
from llm.schemas import LLMEdge, LLMTask, Step1Output, Step2Output
from scenarios.scene import Scene
from validator.hashing import VALIDATOR_VERSION, scene_hash
from validator.patch import graph_edge_keys, graph_task_keys


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class TurnScore:
    turn_number: int
    input_kind: str
    utterance: str | None
    selected_entity_id: str | None
    expected_outcome: str
    actual_outcome: str | None
    expected_intent: dict[str, str] | None
    actual_intent: dict[str, str] | None
    intent_exact: bool | None
    slots_exact: bool | None
    expected_grounding: dict | None
    actual_grounding: dict | None
    grounding_exact: bool | None
    referent_exact: bool | None
    expected_patch: dict | None
    actual_patch: dict | None
    patch_exact: bool | None
    clarification_without_mutation: bool | None
    turn_exact: bool
    latency_s: float
    harness_error: str | None = None


@dataclass(frozen=True, slots=True)
class DialogueScore:
    id: str
    family: str
    profile: str
    shape: str
    turns: tuple[TurnScore, ...]
    final_graph_exact: bool
    dialogue_exact: bool
    resolved_models: tuple[str, ...]
    session_audit: dict
    harness_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InteractionRun:
    track: str
    backend_kind: str
    model: str | None
    scene_hash: str
    validator_version: str
    started_at: str
    finished_at: str
    dialogues: tuple[DialogueScore, ...] = field(default_factory=tuple)


def _task_sort_key(key: tuple[TaskType, str]) -> tuple[str, str]:
    return key[0].value, key[1]


def _generation_script(dialogue: DialogueAnnotation) -> list[object]:
    graph = dialogue.initial_graph
    tasks = [
        LLMTask(task_type=task_type.value, target=target)
        for task_type, target in sorted(graph.tasks, key=_task_sort_key)
    ]
    edges = [
        LLMEdge(
            predecessor=f"{predecessor[0].value}:{predecessor[1]}",
            successor=f"{successor[0].value}:{successor[1]}",
        )
        for predecessor, successor in sorted(
            graph.edges,
            key=lambda edge: (_task_sort_key(edge[0]), _task_sort_key(edge[1])),
        )
    ]
    return [Step1Output(tasks=tasks), Step2Output(edges=edges)]


def gold_backend(dialogue: DialogueAnnotation) -> MockBackend:
    """Fresh perfect backend for the grounder-only track."""
    script: list[object] = []
    for turn in dialogue.turns:
        if turn.input_kind != "NATURAL_LANGUAGE":
            continue
        intent = turn.intent or {}
        kind = intent.get("kind")
        if kind is None:
            raise ValueError(f"{dialogue.id}: natural-language turn has no gold intent")
        script.append(wire_intent(kind, **{k: v for k, v in intent.items() if k != "kind"}))
        if kind == "NEW_MISSION":
            script.extend(_generation_script(dialogue))
    return MockBackend(script)


def _grounding_dict(value: ExpectedGrounding | GroundingAudit | None) -> dict | None:
    if value is None:
        return None
    if isinstance(value, ExpectedGrounding):
        return {
            "status": value.status,
            "entity_kind": value.entity_kind,
            "entity_id": value.entity_id,
            "via": value.via,
            "reason": value.reason,
            "candidates": list(value.candidates),
        }
    return {
        "status": value.status,
        "entity_kind": value.entity_kind,
        "entity_id": value.entity_id,
        "via": value.via,
        "reason": value.reason,
        "candidates": list(value.candidates),
    }


def _patch_dict(value: ExpectedPatch | PatchAudit | None) -> dict | None:
    if value is None:
        return None
    if isinstance(value, ExpectedPatch):
        return {
            "accepted": value.accepted,
            "added_tasks": sorted(value.added_tasks),
            "added_edges": sorted([list(edge) for edge in value.added_edges]),
            "directly_released_tasks": sorted(value.directly_released_tasks),
        }
    return {
        "accepted": value.accepted,
        "added_tasks": sorted(value.added_tasks),
        "added_edges": sorted(value.added_edges),
        "directly_released_tasks": sorted(value.directly_released_tasks),
    }


def _intent_parts(audit: TurnAudit | None) -> tuple[dict[str, str] | None, str | None]:
    if audit is None or audit.input_kind != "NATURAL_LANGUAGE":
        return None, None
    actual = {"kind": audit.intent_kind} if audit.intent_kind is not None else None
    if actual is not None:
        actual.update(audit.extracted_slots)
    return actual, audit.intent_kind


def _score_turn(
    number: int,
    gold: DialogueTurn,
    result: TurnResult | None,
    latency_s: float,
    harness_error: str | None,
) -> TurnScore:
    audit = result.audit if result is not None else None
    actual_intent, actual_kind = _intent_parts(audit)
    natural = gold.input_kind == "NATURAL_LANGUAGE"
    expected_kind = gold.intent.get("kind") if gold.intent else None
    expected_slots = {k: v for k, v in (gold.intent or {}).items() if k != "kind"}
    actual_slots = audit.extracted_slots if audit is not None and natural else None
    intent_exact = actual_kind == expected_kind if natural else None
    slots_exact = actual_slots == expected_slots if natural else None

    expected_grounding = _grounding_dict(gold.grounding)
    actual_grounding = _grounding_dict(audit.grounding if audit else None)
    grounding_exact = actual_grounding == expected_grounding
    if gold.grounding is None:
        referent_exact = None
    elif gold.grounding.status == "RESOLVED":
        referent_exact = bool(
            actual_grounding
            and actual_grounding["status"] == "RESOLVED"
            and actual_grounding["entity_kind"] == gold.grounding.entity_kind
            and actual_grounding["entity_id"] == gold.grounding.entity_id
        )
    else:
        referent_exact = None

    expected_patch = _patch_dict(gold.patch)
    actual_patch = _patch_dict(audit.patch if audit else None)
    patch_exact = actual_patch == expected_patch
    expected_outcome = gold.outcome
    actual_outcome = result.outcome.value if result is not None else None
    clarification_without_mutation = None
    if actual_outcome == "CLARIFICATION" and audit is not None:
        clarification_without_mutation = not audit.scene_changed and not audit.state_changed

    checks = [
        harness_error is None,
        actual_outcome == expected_outcome,
        grounding_exact,
        patch_exact,
    ]
    if natural:
        checks.extend([intent_exact is True, slots_exact is True])
    return TurnScore(
        turn_number=number,
        input_kind=gold.input_kind,
        utterance=gold.utterance,
        selected_entity_id=gold.entity_id,
        expected_outcome=expected_outcome,
        actual_outcome=actual_outcome,
        expected_intent=gold.intent,
        actual_intent=actual_intent,
        intent_exact=intent_exact,
        slots_exact=slots_exact,
        expected_grounding=expected_grounding,
        actual_grounding=actual_grounding,
        grounding_exact=grounding_exact,
        referent_exact=referent_exact,
        expected_patch=expected_patch,
        actual_patch=actual_patch,
        patch_exact=patch_exact,
        clarification_without_mutation=clarification_without_mutation,
        turn_exact=all(checks),
        latency_s=latency_s,
        harness_error=harness_error,
    )


def _graph_exact(session: MissionSession, dialogue: DialogueAnnotation) -> bool:
    if session.state is None:
        return False
    graph = session.state.graph
    return (
        frozenset(graph_task_keys(graph)) == dialogue.final_graph.tasks
        and frozenset(graph_edge_keys(graph)) == dialogue.final_graph.edges
    )


def _run_dialogue(
    scene: Scene,
    dialogue: DialogueAnnotation,
    backend: object,
) -> DialogueScore:
    session = MissionSession(session_id=f"p84-{dialogue.id.lower()}", scene=scene)
    scored: list[TurnScore] = []
    errors: list[str] = []
    for number, gold in enumerate(dialogue.turns, start=1):
        started = perf_counter()
        result: TurnResult | None = None
        error: str | None = None
        try:
            if gold.input_kind == "NATURAL_LANGUAGE":
                result = handle_turn(session, gold.utterance or "", backend)
            else:
                result = select_clarification_candidate(
                    session,
                    gold.entity_id or "",
                    mode=getattr(backend, "mode", None),
                )
        except Exception as exc:  # noqa: BLE001 - retain and score later turns
            error = f"{type(exc).__name__}: {exc}"
            errors.append(f"turn {number}: {error}")
        scored.append(_score_turn(number, gold, result, perf_counter() - started, error))

    final_exact = _graph_exact(session, dialogue)
    return DialogueScore(
        id=dialogue.id,
        family=dialogue.family,
        profile=dialogue.profile,
        shape=dialogue.shape,
        turns=tuple(scored),
        final_graph_exact=final_exact,
        dialogue_exact=final_exact and not errors and all(turn.turn_exact for turn in scored),
        resolved_models=tuple(getattr(backend, "resolved_models", ())),
        session_audit=session_audit_payload(session),
        harness_errors=tuple(errors),
    )


def run_interaction_eval(
    scene: Scene,
    dialogues: Sequence[DialogueAnnotation],
    *,
    track: str,
    backend_factory: Callable[[DialogueAnnotation], object] | None = None,
    model: str | None = None,
) -> InteractionRun:
    """Run all dialogues with strict per-dialogue context isolation."""
    if track not in {"grounder-only", "end-to-end"}:
        raise ValueError("track must be 'grounder-only' or 'end-to-end'")
    if track == "grounder-only" and backend_factory is not None:
        raise ValueError("grounder-only builds its own gold backend")
    if track == "end-to-end" and backend_factory is None:
        raise ValueError("end-to-end requires a backend_factory")

    started_at = _utc_now()
    cases: list[DialogueScore] = []
    kinds: set[str] = set()
    for dialogue in dialogues:
        backend = (
            gold_backend(dialogue)
            if track == "grounder-only"
            else backend_factory(dialogue)  # type: ignore[misc]
        )
        kinds.add(str(getattr(backend, "mode", "unknown")))
        cases.append(_run_dialogue(scene, dialogue, backend))
    if len(kinds) != 1:
        raise ValueError(f"one evaluation run cannot mix backend modes: {sorted(kinds)}")
    backend_kind = kinds.pop()
    return InteractionRun(
        track=track,
        backend_kind=backend_kind,
        model=model,
        scene_hash=scene_hash(scene),
        validator_version=VALIDATOR_VERSION,
        started_at=started_at,
        finished_at=_utc_now(),
        dialogues=tuple(cases),
    )


__all__ = [
    "DialogueScore",
    "InteractionRun",
    "TurnScore",
    "gold_backend",
    "run_interaction_eval",
]
