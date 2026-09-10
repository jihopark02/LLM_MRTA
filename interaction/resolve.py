"""Deterministic Clause Resolver — Semantic Mission IR → concrete target sets
(D-076, §18.3, DECISIONS S1–S7).

Every generic language operator the LLM emitted (`RANGE`, `REGION`, `EXCLUDE`,
`RECENT_INCIDENTS`, `SPATIAL_PICK`, `UNVISITED_ONLY`, `DEIXIS`, explicit
phrases) is interpreted here against the **current world**: the `Scene`, the
current `MissionState`, and the chronological `event_log`. Nothing in this
module branches on the raw utterance or maps a specific phrase / scenario to a
fixed graph — the same IR resolves differently as the world changes.

Fail-closed: an operator that resolves to nothing, an under-determined
singular pick, an unknown exclusion, or two response depths for one incident
all return a `GroundingOutcome(CLARIFICATION_REQUIRED)` rather than a guess.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.enums import TaskStatus, TaskType
from interaction.audit import IncidentActionAudit, IncidentObservationAudit, TurnAudit
from interaction.ground import (
    ClarificationReason,
    GroundingOutcome,
    GroundingStatus,
    resolve_incident,
    resolve_zone,
)
from interaction.mission_ir import (
    IncidentSelector,
    ReconClause,
    ResponseClause,
    SemanticMissionIR,
    ZoneSelector,
)
from interaction.session import MissionSession, ReferentKind
from scenarios.scene import Scene


@dataclass(frozen=True, slots=True)
class ResolvedReconClause:
    zone_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolvedResponseClause:
    incident_ids: tuple[str, ...]
    response_up_to: str            # "GROUND_INSPECTION" | "GROUND_SUPPRESSION"


@dataclass(frozen=True, slots=True)
class ResolvedMissionIR:
    recon: tuple[ResolvedReconClause, ...]
    responses: tuple[ResolvedResponseClause, ...]
    incident_policy: object | None = None      # carried through unchanged


ResolveResult = ResolvedMissionIR | GroundingOutcome


def _clarify(question: str, reason: ClarificationReason,
             candidates: tuple[str, ...] = (),
             entity_kind: ReferentKind | None = None) -> GroundingOutcome:
    return GroundingOutcome(
        GroundingStatus.CLARIFICATION_REQUIRED,
        entity_kind=entity_kind,
        clarification=question,
        candidates=candidates,
        reason=reason,
    )


# -- zones ------------------------------------------------------------


def _zone_phrase(scene: Scene, phrase: str) -> str | GroundingOutcome:
    out = resolve_zone(scene, phrase)
    return out.entity_id if out.resolved else out


def _region_zone_ids(scene: Scene, region: str) -> tuple[str, ...]:
    """Scene-bbox half-plane over every zone's recon_waypoint (S6)."""
    xs = [z.recon_waypoint[0] for z in scene.zones.values()]
    ys = [z.recon_waypoint[1] for z in scene.zones.values()]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    keep = {
        "WEST": lambda x, y: x < cx,
        "EAST": lambda x, y: x >= cx,
        "SOUTH": lambda x, y: y < cy,
        "NORTH": lambda x, y: y >= cy,
    }[region]
    return tuple(
        zid for zid, z in sorted(scene.zones.items())
        if keep(z.recon_waypoint[0], z.recon_waypoint[1])
    )


def _completed_recon_zones(session: MissionSession) -> set[str]:
    if session.state is None:
        return set()
    return {
        t.target for t in session.state.graph.tasks
        if t.task_type is TaskType.AREA_RECON and t.status is TaskStatus.COMPLETED
    }


def _resolve_zone_selector(sel: ZoneSelector, session: MissionSession):
    scene = session.scene
    ordered = sorted(scene.zones)

    if sel.explicit:
        base: list[str] = []
        for phrase in sel.explicit:
            got = _zone_phrase(scene, phrase)
            if isinstance(got, GroundingOutcome):
                return got
            base.append(got)
    elif sel.region is not None:
        base = list(_region_zone_ids(scene, sel.region))
    else:  # range
        lo = _zone_phrase(scene, sel.range_from)
        hi = _zone_phrase(scene, sel.range_to)
        for got in (lo, hi):
            if isinstance(got, GroundingOutcome):
                return got
        i, j = ordered.index(lo), ordered.index(hi)
        if i > j:
            return _clarify(
                f"'{sel.range_from}~{sel.range_to}' 범위가 순서에 맞지 않습니다.",
                ClarificationReason.UNKNOWN_ENTITY, tuple(ordered), ReferentKind.ZONE,
            )
        base = ordered[i : j + 1]

    excluded: set[str] = set()
    for phrase in sel.exclude:
        got = _zone_phrase(scene, phrase)
        if isinstance(got, GroundingOutcome):
            return _clarify(
                f"제외 대상 '{phrase}'을(를) 구역으로 해석할 수 없습니다.",
                ClarificationReason.UNKNOWN_ENTITY, tuple(ordered), ReferentKind.ZONE,
            )
        excluded.add(got)

    result = [z for z in base if z not in excluded]
    if sel.unvisited_only:
        done = _completed_recon_zones(session)
        result = [z for z in result if z not in done]

    if not result:
        return _clarify(
            "선택한 조건에 해당하는 구역이 없습니다.",
            ClarificationReason.NO_ENTITIES, tuple(ordered), ReferentKind.ZONE,
        )
    # dedup, keep scene order
    seen: set[str] = set()
    return tuple(z for z in result if not (z in seen or seen.add(z)))


# -- incidents ------------------------------------------------------


def _registration_events(session: MissionSession):
    """(incident_id, source) newest-first for every incident that entered the
    system, source in {OPERATOR, SENSOR} (S2)."""
    out: list[tuple[str, str]] = []
    for event in reversed(session.event_log):
        act: IncidentActionAudit | None = None
        if isinstance(event, TurnAudit):
            act = event.incident_action
        elif isinstance(event, IncidentObservationAudit) and event.incident_id:
            src = "SENSOR" if event.source == "SENSOR_SIMULATED" else "OPERATOR"
            out.append((event.incident_id, src))
            continue
        if act is not None and act.incident_id:
            src = "OPERATOR" if act.source == "OPERATOR" else "SENSOR"
            out.append((act.incident_id, src))
    return out


def _recent_incident_ids(sel: IncidentSelector, session: MissionSession) -> list[str]:
    if sel.recency == "ALL_KNOWN":
        return list(session.known_incident_ids)

    want = sel.recent_source or "ANY"
    seen: set[str] = set()
    ordered: list[str] = []
    for iid, src in _registration_events(session):
        if want != "ANY" and src != want:
            continue
        if iid not in seen and iid in session.scene.incidents:
            seen.add(iid)
            ordered.append(iid)

    if sel.recency == "PREVIOUS_DETECTED":
        return ordered[1:2] if len(ordered) > 1 else []
    count = sel.recent_count or 1
    return ordered[:count]


def _resolve_incident_selector(sel: IncidentSelector, session: MissionSession):
    scene = session.scene
    known = tuple(session.known_incident_ids)

    if sel.explicit:
        ids: list[str] = []
        for phrase in sel.explicit:
            out = resolve_incident(session, phrase)
            if not out.resolved:
                return out
            ids.append(out.entity_id)
    elif sel.deixis is not None:
        out = resolve_incident(session, sel.deixis)
        if not out.resolved:
            return out
        ids = [out.entity_id]
    else:  # recency
        ids = _recent_incident_ids(sel, session)
        need = sel.recent_count or (1 if sel.recency != "ALL_KNOWN" else 0)
        if not ids or (sel.recent_count is not None and len(ids) < need):
            return _clarify(
                f"해당하는 화재가 충분하지 않습니다 (요청 {need}, 확인 {len(ids)}).",
                ClarificationReason.NO_ENTITIES, known, ReferentKind.INCIDENT,
            )

    if sel.spatial_pick is not None:
        ids = _spatial_pick(scene, ids, sel.spatial_pick)
        if isinstance(ids, GroundingOutcome):
            return ids

    seen: set[str] = set()
    return tuple(i for i in ids if not (i in seen or seen.add(i)))


def _spatial_pick(scene: Scene, ids: list[str], pick: str):
    if not ids:
        return []
    axis, want_max = {
        "EASTMOST": (0, True), "WESTMOST": (0, False),
        "NORTHMOST": (1, True), "SOUTHMOST": (1, False),
    }[pick]
    keyed = [(scene.incidents[i].position[axis], i) for i in ids]
    extreme = (max if want_max else min)(v for v, _ in keyed)
    winners = sorted(i for v, i in keyed if v == extreme)
    if len(winners) != 1:
        return _clarify(
            f"'{pick}'에 해당하는 화재가 둘 이상입니다. 어느 쪽입니까?",
            ClarificationReason.AMBIGUOUS_ENTITY, tuple(winners), ReferentKind.INCIDENT,
        )
    return winners


# -- top level -----------------------------------------------------


def resolve_mission_ir(ir: SemanticMissionIR, session: MissionSession) -> ResolveResult:
    recon: list[ResolvedReconClause] = []
    for clause in ir.recon:
        assert isinstance(clause, ReconClause)
        got = _resolve_zone_selector(clause.zones, session)
        if isinstance(got, GroundingOutcome):
            return got
        recon.append(ResolvedReconClause(got))

    responses: list[ResolvedResponseClause] = []
    for clause in ir.responses:
        assert isinstance(clause, ResponseClause)
        got = _resolve_incident_selector(clause.incidents, session)
        if isinstance(got, GroundingOutcome):
            return got
        responses.append(ResolvedResponseClause(got, clause.response_up_to))

    # S4: one incident may not carry two response depths across clauses.
    depths: dict[str, set[str]] = {}
    for r in responses:
        for iid in r.incident_ids:
            depths.setdefault(iid, set()).add(r.response_up_to)
    conflicted = sorted(i for i, d in depths.items() if len(d) > 1)
    if conflicted:
        return _clarify(
            f"{', '.join(conflicted)}에 대한 대응 단계 지시가 상충합니다. 어느 단계로 할까요?",
            ClarificationReason.SEMANTIC_CONFLICT, tuple(conflicted), ReferentKind.INCIDENT,
        )

    return ResolvedMissionIR(tuple(recon), tuple(responses), ir.incident_policy)


__all__ = [
    "ResolvedReconClause",
    "ResolvedResponseClause",
    "ResolvedMissionIR",
    "ResolveResult",
    "resolve_mission_ir",
]
