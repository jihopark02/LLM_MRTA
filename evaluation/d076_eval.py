"""D-076 held-out evaluation (RESEARCH_CONTRACT.md §18.15, DECISIONS S12).

Measures the D-076 pipeline layer by layer:

    free-form utterance
    -> LLM: dialogue act + Semantic Mission IR      (metric 1: IR exact-match)
    -> deterministic Clause Resolver                (metric 2: resolved target-set exact)
    -> deterministic Mission Compiler + Validator   (metric 3: final graph / patch exact)
    -> TurnOutcome                                  (metric 4: clarification correctness)
                                                    (metric 5: unsafe commit rate)

The three exact-match metrics are scored independently so a failure is
attributable to the LLM, the resolver, or the compiler.

Annotation records live under ``data/d076_eval/{explicit,compositional,contextual}/``.
The ``final_graph`` / ``patch`` is NOT hand-authored: the loader expands the
expected IR, resolves it against the record's world/state/event snapshot,
compiles it, and self-checks the whole chain against the deterministic
Validator (the P6 ``load_annotation`` discipline). A mis-authored record fails
loudly at load, before any LLM call.

    python3 -m evaluation.d076_eval --mock                 # gold-backend self-test
    python3 -m evaluation.d076_eval --live --out data/eval_results/d076_heldout
    python3 -m evaluation.d076_eval --cached --cache-dir data/llm_cache/d076
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from allocation.allocate import allocate
from evaluation.annotations import _expand as _expand_graph_spec
from interaction.audit import IncidentObservationAudit
from interaction.audit_io import session_audit_payload
from interaction.ground import GroundingOutcome
from interaction.mission_ir import (
    ConditionalPolicy,
    IncidentSelector,
    ReconClause,
    ResponseClause,
    SemanticMissionIR,
    ZoneSelector,
)
from interaction.orchestrator import TurnOutcome, handle_turn
from interaction.resolve import ResolvedMissionIR, resolve_mission_ir
from interaction.schemas import wire_intent
from interaction.session import MissionSession, fresh_session_state
from llm.backend import DEFAULT_MODEL, MockBackend
from scenarios.compiler import task_id_for
from scenarios.scene import Scene, load_scene
from validator.candidate import CandidateEdge, CandidateTask, MissionCandidate
from validator.hashing import graph_hash
from validator.patch import AddEdge, AddTask, graph_edge_keys, graph_hash_nodes
from validator.validate import validate_candidate

_ROOT = Path(__file__).resolve().parents[1]
_DIR = _ROOT / "data" / "d076_eval"
LEVELS = ("explicit", "compositional", "contextual")

_UP_TO = {"inspection": "GROUND_INSPECTION", "suppression": "GROUND_SUPPRESSION"}
_RECENCY = {
    "recent": "MOST_RECENT_DETECTED",
    "previous": "PREVIOUS_DETECTED",
    "all": "ALL_KNOWN",
}
_SOURCE = {"sensor": "SENSOR", "operator": "OPERATOR", "any": "ANY"}
_PICK = {p.lower(): p for p in ("EASTMOST", "WESTMOST", "NORTHMOST", "SOUTHMOST")}
_REGION = {r.lower(): r for r in ("NORTH", "SOUTH", "EAST", "WEST")}


# -- compact IR DSL -> SemanticMissionIR --------------------------------


def _zone_selector(spec: dict) -> ZoneSelector:
    allowed = {"explicit", "range", "region", "exclude", "unvisited_only"}
    extra = set(spec) - allowed
    if extra:
        raise ValueError(f"zone selector has unexpected keys {sorted(extra)}")
    rng = spec.get("range")
    if rng is not None and len(rng) != 2:
        raise ValueError("range must be [from, to]")
    return ZoneSelector(
        explicit=list(spec.get("explicit", [])),
        range_from=rng[0] if rng else None,
        range_to=rng[1] if rng else None,
        region=_REGION[spec["region"].lower()] if "region" in spec else None,
        exclude=list(spec.get("exclude", [])),
        unvisited_only=bool(spec.get("unvisited_only", False)),
    )


def _incident_selector(spec: dict) -> IncidentSelector:
    allowed = {"explicit", "deixis", "recency", "count", "source", "spatial_pick", "up_to"}
    extra = set(spec) - allowed
    if extra:
        raise ValueError(f"incident selector has unexpected keys {sorted(extra)}")
    return IncidentSelector(
        explicit=list(spec.get("explicit", [])),
        deixis=spec.get("deixis"),
        recency=_RECENCY[spec["recency"]] if "recency" in spec else None,
        recent_count=spec.get("count"),
        recent_source=_SOURCE[spec["source"]] if "source" in spec else None,
        spatial_pick=_PICK[spec["spatial_pick"].lower()] if "spatial_pick" in spec else None,
    )


def expand_ir(spec: dict) -> SemanticMissionIR:
    extra = set(spec) - {"recon", "responses", "incident_policy"}
    if extra:
        raise ValueError(f"semantic_ir has unexpected keys {sorted(extra)}")
    recon = [ReconClause(zones=_zone_selector(c)) for c in spec.get("recon", [])]
    responses = [
        ResponseClause(
            incidents=_incident_selector(c), response_up_to=_UP_TO[c["up_to"]]
        )
        for c in spec.get("responses", [])
    ]
    policy = spec.get("incident_policy")
    return SemanticMissionIR(
        recon=recon,
        responses=responses,
        incident_policy=(
            None
            if policy is None
            else ConditionalPolicy(
                trigger="FIRE_DETECTED", response_up_to=_UP_TO[policy["up_to"]]
            )
        ),
    )


# -- resolved compact form --------------------------------------------


def _resolved_dict(resolved: ResolvedMissionIR) -> dict:
    return {
        "recon": [sorted(c.zone_ids) for c in resolved.recon],
        "responses": [
            [sorted(c.incident_ids), c.response_up_to] for c in resolved.responses
        ],
    }


def _expected_resolved_dict(spec: dict | None) -> dict | None:
    if spec is None:
        return None
    return {
        "recon": [sorted(zids) for zids in spec.get("recon", [])],
        "responses": [
            [sorted(ids), _UP_TO.get(up, up)] for ids, up in spec.get("responses", [])
        ],
    }


# -- annotation record ------------------------------------------------


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    level: str
    world: str
    utterance: str
    kind: str
    expected_ir: SemanticMissionIR
    expected_outcome: str
    expected_reason: str | None
    expected_resolved: dict | None
    counterfactual_of: str | None
    # derived at load, self-checked against the Validator
    expected_graph_hash: str | None
    expected_added_tasks: tuple[str, ...]
    expected_added_edges: tuple[tuple[str, str], ...]
    _initial_graph_spec: dict | None
    _event_history: tuple[dict, ...]
    _referents: tuple[str, ...]
    _completed_recon: tuple[str, ...]


_TOP_KEYS = {
    "id", "level", "world", "utterance", "expected",
    "initial_graph", "event_history", "counterfactual_of",
    "referents", "completed_recon",
}
_OUTCOMES = {"COMMITTED", "NO_CHANGE", "CLARIFICATION", "REJECTED"}
_EXPECTED_KEYS = {
    "kind", "semantic_ir", "outcome", "clarification_reason", "resolved",
}


def _build_session(
    scene: Scene,
    sid: str,
    *,
    initial_graph_spec: dict | None = None,
    event_history: tuple[dict, ...] = (),
    referents: tuple[str, ...] = (),
    completed_recon: tuple[str, ...] = (),
) -> MissionSession:
    from core.enums import TaskStatus, TaskType

    state = None
    plan = None
    if initial_graph_spec:
        _, candidate = _expand_graph_spec(initial_graph_spec, scene)
        graph = _compile_candidate(candidate, scene)
        for task in graph.tasks:
            if task.task_type is TaskType.AREA_RECON and task.target in completed_recon:
                task.status = TaskStatus.COMPLETED
        state = fresh_session_state(graph, scene)
        plan = allocate(state, scene)
    elif completed_recon:
        raise ValueError("completed_recon needs an initial_graph")
    session = MissionSession(sid, scene, state=state, plan=plan)
    _seed_events(session, event_history)
    for incident_id in referents:
        session.note_referent("incident", incident_id)
    return session


def _compile_candidate(candidate: MissionCandidate, scene: Scene):
    from scenarios.compiler import compile_reference_graph

    tasks = [(t.task_type, t.target) for t in candidate.tasks]
    edges = [(e.predecessor, e.successor) for e in candidate.edges]
    return compile_reference_graph(scene, tasks, edges)


def _seed_events(session: MissionSession, history: tuple[dict, ...]) -> None:
    for i, ev in enumerate(history):
        extra = set(ev) - {"incident", "source", "t", "zone"}
        if extra:
            raise ValueError(f"event_history entry has unexpected keys {sorted(extra)}")
        incident_id = ev["incident"]
        zone = ev.get("zone") or session.scene.incidents[incident_id].zone
        source = "SENSOR_SIMULATED" if ev.get("source", "sensor") == "sensor" else "OPERATOR"
        session.append_event(
            IncidentObservationAudit(
                session_id=session.session_id,
                fixture_id="d076-eval",
                zone_id=zone,
                trigger_task_id=f"AREA_RECON__{zone}",
                detecting_agent_id="U1",
                simulation_time=float(ev.get("t", 10.0 + i)),
                mode="mock",
                outcome="ADAPTED",
                incident_id=incident_id,
                source=source,
            )
        )


@dataclass(frozen=True, slots=True)
class _WorldCtx:
    scene: Scene
    world: str
    initial_graph_spec: dict | None
    event_history: tuple[dict, ...]
    referents: tuple[str, ...]
    completed_recon: tuple[str, ...]

    def build(self, sid: str) -> MissionSession:
        return _build_session(
            self.scene,
            sid,
            initial_graph_spec=self.initial_graph_spec,
            event_history=self.event_history,
            referents=self.referents,
            completed_recon=self.completed_recon,
        )


def _compile_and_validate(kind: str, resolved, ctx: _WorldCtx):
    from interaction.compile_clauses import compile_new_graph, compile_patch
    from validator.patch_apply import apply_patch

    if kind == "NEW_MISSION":
        graph = compile_new_graph(resolved, ctx.scene)
        candidate = MissionCandidate(
            tasks=[CandidateTask(tt, tg) for tt, tg in sorted(_task_keys(graph))],
            edges=[CandidateEdge(p, s) for p, s in sorted(graph_edge_keys(graph))],
        )
        return graph, validate_candidate(candidate, ctx.scene)
    state = ctx.build("d076-cmp").state
    patch = compile_patch(resolved, state.graph)
    _, result = apply_patch(state, patch, ctx.scene)
    return patch, result


def _task_keys(graph):
    return {(t.task_type, t.target) for t in graph.tasks}


def _derive_expected(path: Path, kind: str, resolved, ctx: _WorldCtx):
    obj, verdict = _compile_and_validate(kind, resolved, ctx)
    if not verdict.accepted:
        raise ValueError(
            f"{path}: the compiled expected graph fails the Validator: "
            f"{[str(e) for e in verdict.errors]}"
        )
    if kind == "NEW_MISSION":
        return graph_hash(graph_hash_nodes(obj), sorted(graph_edge_keys(obj))), (), ()
    tasks = tuple(
        task_id_for(op.task_type, op.target)
        for op in obj.operations
        if isinstance(op, AddTask)
    )
    edges = tuple(
        (task_id_for(*op.predecessor), task_id_for(*op.successor))
        for op in obj.operations
        if isinstance(op, AddEdge)
    )
    return None, tasks, edges


def load_case(path: Path) -> Case:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) - _TOP_KEYS:
        raise ValueError(f"{path}: keys {sorted(raw)} not within {sorted(_TOP_KEYS)}")
    for key in ("id", "level", "world", "utterance", "expected"):
        if key not in raw:
            raise ValueError(f"{path}: missing {key!r}")
    case_id = raw["id"]
    if path.stem != case_id:
        raise ValueError(f"{path}: id {case_id!r} != filename")
    if raw["level"] not in LEVELS or path.parent.name != raw["level"]:
        raise ValueError(f"{path}: level {raw['level']!r} mismatch")

    exp = raw["expected"]
    if set(exp) - _EXPECTED_KEYS:
        raise ValueError(f"{path}: expected keys {sorted(exp)}")
    kind = exp["kind"]
    if kind not in {"NEW_MISSION", "UPDATE_MISSION"}:
        raise ValueError(f"{path}: D-076 eval covers NEW/UPDATE_MISSION only, got {kind!r}")
    outcome = exp["outcome"]
    if outcome not in _OUTCOMES:
        raise ValueError(f"{path}: outcome {outcome!r}")
    reason = exp.get("clarification_reason")
    if (outcome == "CLARIFICATION") != (reason is not None):
        raise ValueError(f"{path}: clarification_reason iff outcome == CLARIFICATION")

    expected_ir = expand_ir(exp["semantic_ir"])
    initial_graph_spec = raw.get("initial_graph")
    if kind == "UPDATE_MISSION" and initial_graph_spec is None:
        raise ValueError(f"{path}: UPDATE_MISSION needs an initial_graph")
    if kind == "NEW_MISSION" and initial_graph_spec is not None:
        raise ValueError(f"{path}: NEW_MISSION must not carry an initial_graph")

    ctx = _WorldCtx(
        scene=load_scene(_ROOT / raw["world"]),
        world=raw["world"],
        initial_graph_spec=initial_graph_spec,
        event_history=tuple(raw.get("event_history") or ()),
        referents=tuple(raw.get("referents") or ()),
        completed_recon=tuple(raw.get("completed_recon") or ()),
    )

    # -- self-check: expected IR must resolve + compile exactly as annotated ---
    resolved = resolve_mission_ir(expected_ir, ctx.build("d076-load"))
    expected_resolved = _expected_resolved_dict(exp.get("resolved"))
    graph_hash_value: str | None = None
    added_tasks: tuple[str, ...] = ()
    added_edges: tuple[tuple[str, str], ...] = ()

    if outcome in {"COMMITTED", "NO_CHANGE"}:
        if isinstance(resolved, GroundingOutcome):
            raise ValueError(
                f"{path}: expected {outcome} but the resolver clarified ({resolved.reason})"
            )
        if _resolved_dict(resolved) != expected_resolved:
            raise ValueError(
                f"{path}: expected.resolved {expected_resolved} != resolver output "
                f"{_resolved_dict(resolved)}"
            )
        graph_hash_value, added_tasks, added_edges = _derive_expected(path, kind, resolved, ctx)
        if outcome == "NO_CHANGE" and (added_tasks or added_edges or graph_hash_value):
            # NO_CHANGE only makes sense for an UPDATE whose additive patch is empty
            if kind == "NEW_MISSION" or added_tasks or added_edges:
                raise ValueError(f"{path}: NO_CHANGE case must compile to an empty patch")
    elif outcome == "CLARIFICATION":
        if not isinstance(resolved, GroundingOutcome):
            raise ValueError(f"{path}: expected CLARIFICATION but the resolver succeeded")
        got = resolved.reason.value if resolved.reason else None
        if got != reason:
            raise ValueError(f"{path}: clarification_reason {reason!r} != resolver {got!r}")
        if exp.get("resolved") is not None:
            raise ValueError(f"{path}: a CLARIFICATION case must not carry resolved")
    else:  # REJECTED
        if isinstance(resolved, GroundingOutcome):
            raise ValueError(f"{path}: REJECTED case: the resolver clarified, use CLARIFICATION")
        _, verdict = _compile_and_validate(kind, resolved, ctx)
        if verdict.accepted:
            raise ValueError(f"{path}: expected REJECTED but the compiled graph is Validator-clean")

    return Case(
        id=case_id,
        level=raw["level"],
        world=raw["world"],
        utterance=" ".join(raw["utterance"].split()),
        kind=kind,
        expected_ir=expected_ir,
        expected_outcome=outcome,
        expected_reason=reason,
        expected_resolved=expected_resolved,
        counterfactual_of=raw.get("counterfactual_of"),
        expected_graph_hash=graph_hash_value,
        expected_added_tasks=added_tasks,
        expected_added_edges=added_edges,
        _initial_graph_spec=initial_graph_spec,
        _event_history=ctx.event_history,
        _referents=ctx.referents,
        _completed_recon=ctx.completed_recon,
    )


def load_all() -> list[Case]:
    cases: list[Case] = []
    for level in LEVELS:
        for path in sorted((_DIR / level).glob("*.yaml")):
            cases.append(load_case(path))
    return cases


# -- backends --------------------------------------------------------


def gold_backend(case: Case) -> MockBackend:
    return MockBackend([wire_intent(case.kind, mission=case.expected_ir)])


# -- scoring --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CaseScore:
    id: str
    level: str
    counterfactual_of: str | None
    ir_valid: bool                      # wire schema parsed (possibly after repair)
    ir_repair: bool
    ir_exact: bool
    resolved_exact: bool
    graph_exact: bool
    outcome_correct: bool
    unsafe_commit: bool
    actual_outcome: str
    actual_resolved: dict | None
    llm_latency_s: float
    turn_latency_s: float
    error: str | None = None


def _actual_resolved(semantic_ir) -> dict | None:
    if semantic_ir is None or semantic_ir.clarification_reason is not None:
        return None
    ir_responses = semantic_ir.ir.get("responses", [])
    return {
        "recon": [sorted(c.targets) for c in semantic_ir.recon],
        "responses": [
            [sorted(c.targets), ir_responses[i]["response_up_to"]]
            for i, c in enumerate(semantic_ir.responses)
        ],
    }


def score_case(case: Case, backend) -> tuple[CaseScore, MissionSession]:
    scene = load_scene(_ROOT / case.world)
    session = _build_session(
        scene,
        f"d076-{case.id}",
        initial_graph_spec=case._initial_graph_spec,
        event_history=case._event_history,
        referents=case._referents,
        completed_recon=case._completed_recon,
    )

    result = handle_turn(session, case.utterance, backend)
    audit = result.audit
    sir = audit.semantic_ir
    actual_outcome = result.outcome.value

    ir_valid = audit.intent_kind == case.kind and sir is not None
    ir_exact = ir_valid and sir.ir == case.expected_ir.model_dump()

    actual_resolved = _actual_resolved(sir)
    if case.expected_outcome in {"COMMITTED", "NO_CHANGE"}:
        resolved_exact = actual_resolved == case.expected_resolved
    else:
        got_reason = sir.clarification_reason if sir else None
        resolved_exact = got_reason == case.expected_reason

    graph_exact = _graph_matches(case, result, session)
    outcome_correct = actual_outcome == case.expected_outcome and (
        case.expected_outcome != "CLARIFICATION"
        or (sir is not None and sir.clarification_reason == case.expected_reason)
    )
    unsafe_commit = (
        case.expected_outcome in {"CLARIFICATION", "REJECTED"}
        and actual_outcome == "COMMITTED"
    )

    timing = audit.timing
    return (
        CaseScore(
            id=case.id,
            level=case.level,
            counterfactual_of=case.counterfactual_of,
            ir_valid=ir_valid,
            ir_repair=audit.intent_repair_attempted,
            ir_exact=ir_exact,
            resolved_exact=resolved_exact,
            graph_exact=graph_exact,
            outcome_correct=outcome_correct,
            unsafe_commit=unsafe_commit,
            actual_outcome=actual_outcome,
            actual_resolved=actual_resolved,
            llm_latency_s=timing.llm_total_s if timing else 0.0,
            turn_latency_s=timing.total_s if timing else 0.0,
            error=result.error,
        ),
        session,
    )


def _graph_matches(case: Case, result, session: MissionSession) -> bool:
    if case.expected_outcome in {"CLARIFICATION", "REJECTED", "NO_CHANGE"}:
        # nothing may have been committed
        return not result.audit.state_changed and not result.audit.scene_changed
    if result.outcome is not TurnOutcome.COMMITTED:
        return False
    if case.kind == "NEW_MISSION":
        return result.audit.post_graph_hash == case.expected_graph_hash
    patch = result.audit.patch
    if patch is None:
        return False
    return (
        tuple(patch.added_tasks) == case.expected_added_tasks
        and tuple(tuple(e) for e in patch.added_edges) == case.expected_added_edges
    )


# -- aggregate ------------------------------------------------------


@dataclass
class EvalRun:
    scores: list[CaseScore]
    mode: str
    resolved_models: list[str] = field(default_factory=list)
    audits: dict[str, dict] = field(default_factory=dict)
    generated_at: str = ""


def _rate(values: list[bool]) -> dict:
    n, d = sum(values), len(values)
    return {"n": n, "d": d, "pct": round(100 * _safe_div(n, d), 1)}


def _safe_div(a: int, b: int) -> float:
    return a / b if b else 0.0


def summarise(run: EvalRun) -> dict:
    by_level: dict[str, list[CaseScore]] = {level: [] for level in LEVELS}
    for score in run.scores:
        by_level[score.level].append(score)

    def block(scores: list[CaseScore]) -> dict:
        return {
            "cases": len(scores),
            "ir_exact": _rate([s.ir_exact for s in scores]),
            "resolved_exact": _rate([s.resolved_exact for s in scores]),
            "graph_exact": _rate([s.graph_exact for s in scores]),
            "outcome_correct": _rate([s.outcome_correct for s in scores]),
            "unsafe_commits": sum(s.unsafe_commit for s in scores),
            "structured_output_valid": _rate([s.ir_valid for s in scores]),
            "intent_repair": sum(s.ir_repair for s in scores),
            "llm_latency_s": _latency([s.llm_latency_s for s in scores]),
            "turn_latency_s": _latency([s.turn_latency_s for s in scores]),
            "attribution": _attribution(scores),
        }

    return {
        "overall": block(run.scores),
        "by_level": {level: block(by_level[level]) for level in LEVELS},
        "counterfactual_pairs": _counterfactual_report(run.scores),
    }


def _latency(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0}
    ordered = sorted(values)
    return {
        "mean": round(statistics.fmean(values), 3),
        "median": round(statistics.median(values), 3),
        "p95": round(ordered[max(0, round(0.95 * (len(ordered) - 1)))], 3),
    }


def _attribution(scores: list[CaseScore]) -> dict:
    buckets = {"all_correct": 0, "ir_wrong": 0, "resolver_wrong": 0, "compiler_wrong": 0}
    for s in scores:
        if s.ir_exact and s.resolved_exact and s.graph_exact:
            buckets["all_correct"] += 1
        elif not s.ir_exact:
            buckets["ir_wrong"] += 1
        elif not s.resolved_exact:
            buckets["resolver_wrong"] += 1
        else:
            buckets["compiler_wrong"] += 1
    return buckets


def _counterfactual_report(scores: list[CaseScore]) -> dict:
    by_id = {s.id: s for s in scores}
    pairs = []
    diverged = 0
    for s in scores:
        if not s.counterfactual_of or s.counterfactual_of not in by_id:
            continue
        other = by_id[s.counterfactual_of]
        same_targets = s.actual_resolved == other.actual_resolved
        pairs.append(
            {"a": other.id, "b": s.id, "diverged": not same_targets}
        )
        if not same_targets:
            diverged += 1
    return {"pairs": pairs, "diverged": diverged, "total": len(pairs)}


def run_eval(cases: list[Case], backend_for, mode: str) -> EvalRun:
    scores: list[CaseScore] = []
    audits: dict[str, dict] = {}
    models: list[str] = []
    for case in cases:
        backend = backend_for(case)
        score, session = score_case(case, backend)
        scores.append(score)
        audits[case.id] = session_audit_payload(session)
        models += list(getattr(backend, "resolved_models", ()))
    return EvalRun(
        scores=scores,
        mode=mode,
        resolved_models=sorted(set(models)),
        audits=audits,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# -- report ---------------------------------------------------------


def text_report(run: EvalRun) -> str:
    s = summarise(run)
    lines = [
        f"D-076 held-out evaluation  ({run.mode})",
        f"  cases: {len(run.scores)}   models: {', '.join(run.resolved_models) or '-'}",
        "",
    ]
    for name, block in [("OVERALL", s["overall"]), *s["by_level"].items()]:
        lines.append(f"[{name}]  ({block['cases']} cases)")
        for metric in (
            "ir_exact", "resolved_exact", "graph_exact",
            "outcome_correct", "structured_output_valid",
        ):
            r = block[metric]
            lines.append(f"  {metric:24s} {r['n']:2d}/{r['d']:<2d}  ({r['pct']}%)")
        lines.append(f"  {'unsafe_commits':24s} {block['unsafe_commits']}")
        lines.append(f"  {'intent_repair':24s} {block['intent_repair']}")
        a = block["attribution"]
        lines.append(
            f"  attribution              all={a['all_correct']} ir={a['ir_wrong']} "
            f"resolver={a['resolver_wrong']} compiler={a['compiler_wrong']}"
        )
        lat = block["turn_latency_s"]
        lines.append(
            f"  turn latency s           mean={lat['mean']} median={lat['median']} p95={lat['p95']}"
        )
        lines.append("")
    cf = s["counterfactual_pairs"]
    lines.append(f"counterfactual pairs: {cf['diverged']}/{cf['total']} diverged as designed")
    for pair in cf["pairs"]:
        flag = "ok" if pair["diverged"] else "SAME-TARGETS"
        lines.append(f"  {pair['a']} <> {pair['b']}: {flag}")
    return "\n".join(lines)


def to_json(run: EvalRun) -> str:
    payload = {
        "mode": run.mode,
        "generated_at": run.generated_at,
        "resolved_models": run.resolved_models,
        "summary": summarise(run),
        "cases": [
            {
                "id": s.id,
                "level": s.level,
                "counterfactual_of": s.counterfactual_of,
                "ir_valid": s.ir_valid,
                "ir_repair": s.ir_repair,
                "ir_exact": s.ir_exact,
                "resolved_exact": s.resolved_exact,
                "graph_exact": s.graph_exact,
                "outcome_correct": s.outcome_correct,
                "unsafe_commit": s.unsafe_commit,
                "actual_outcome": s.actual_outcome,
                "actual_resolved": s.actual_resolved,
                "llm_latency_s": round(s.llm_latency_s, 3),
                "turn_latency_s": round(s.turn_latency_s, 3),
                "error": s.error,
            }
            for s in run.scores
        ],
        "session_audits": run.audits,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


# -- CLI ----------------------------------------------------------


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--mock", action="store_true", help="gold-backend self-test")
    grp.add_argument("--live", action="store_true", help="OpenAI backend (records the cache)")
    grp.add_argument("--cached", action="store_true", help="replay a recorded cache")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--cache-dir", default="data/llm_cache/d076")
    p.add_argument("--out", default=None, help="write <out>.txt and <out>.json")
    return p


def _backend_factory(args):
    if args.live:
        from llm.backend import OpenAIBackend
        from llm.cache import RecordingBackend

        return lambda _case: RecordingBackend(OpenAIBackend(args.model), args.cache_dir)
    if args.cached:
        from llm.cache import CachedBackend

        return lambda _case: CachedBackend(args.model, args.cache_dir)
    return gold_backend


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    mode = "live" if args.live else "cached" if args.cached else "mock"
    cases = load_all()
    run = run_eval(cases, _backend_factory(args), mode)
    report = text_report(run)
    print(report)
    if args.out:
        prefix = Path(args.out)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        prefix.with_suffix(".txt").write_text(report + "\n", encoding="utf-8")
        prefix.with_suffix(".json").write_text(to_json(run) + "\n", encoding="utf-8")
    return 0 if run.scores and all(not s.unsafe_commit for s in run.scores) else 1


if __name__ == "__main__":
    sys.exit(main())
