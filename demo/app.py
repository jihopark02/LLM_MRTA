"""Streamlit operator console for the P8 planning session.

Run from the repository root:

    streamlit run demo/app.py

The page is a pure view/controller: all mission decisions go through
``interaction.orchestrator`` and ``interaction.execute``.
"""

# ruff: noqa: E402 -- Streamlit needs the repository-root bootstrap below.

from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import streamlit as st

# Streamlit executes this file with ``demo/`` as the import root.  Add the
# repository root before importing project packages so the documented
# ``streamlit run demo/app.py`` command works without an editable install.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo.mock_script import MOCK_COMMANDS, make_mock_backend
from interaction.audit import CheckpointAudit
from interaction.audit_io import write_session_audit
from interaction.execute import execute_session
from interaction.online_execute import advance_online_session
from interaction.orchestrator import (
    cancel_clarification,
    handle_turn,
    select_clarification_candidate,
)
from interaction.session import MissionSession, SessionPhase
from llm.backend import DEFAULT_MODEL, OpenAIBackend
from llm.cache import CachedBackend, RecordingBackend
from scenarios.scene import load_scene

SCENE_PATH = ROOT / "scenarios" / "industrial_park.yaml"
RUNTIME_ROOT = Path(os.environ.get("LLM_MRTA_RUNTIME_ROOT", ROOT / "data"))
AUDIT_PATH = RUNTIME_ROOT / "interaction_runs"
CACHE_PATH = RUNTIME_ROOT / "llm_cache"


def _new_session() -> MissionSession:
    return MissionSession(f"ui-{uuid4().hex[:12]}", load_scene(SCENE_PATH))


def _initialise() -> None:
    if "mission_session" not in st.session_state:
        st.session_state.mission_session = _new_session()
        st.session_state.chat = []
        st.session_state.backends = {}


def _backend(mode: str):
    backends = st.session_state.backends
    if mode not in backends:
        if mode == "live":
            backends[mode] = RecordingBackend(OpenAIBackend(DEFAULT_MODEL), CACHE_PATH)
        elif mode == "cached":
            backends[mode] = CachedBackend(DEFAULT_MODEL, CACHE_PATH)
        else:
            backends[mode] = make_mock_backend()
    return backends[mode]


def _record(operator: str, assistant: str) -> None:
    st.session_state.chat.extend(
        [
            {"role": "user", "content": operator},
            {"role": "assistant", "content": assistant},
        ]
    )


def _persist(session: MissionSession) -> None:
    write_session_audit(session, AUDIT_PATH)


def _scene_panel(session: MissionSession) -> None:
    st.subheader("Semantic scene")
    st.write("Zones")
    st.dataframe(
        [
            {
                "zone_id": zone_id,
                "name": zone.name,
                "response_access_node": zone.reported_incident_access_node,
            }
            for zone_id, zone in sorted(session.scene.zones.items())
        ],
        width="stretch",
        hide_index=True,
    )
    st.write("Known incidents")
    st.dataframe(
        [
            {
                "incident_id": incident_id,
                "zone": incident.zone,
                "status": incident.status.value,
                "priority": incident.priority,
            }
            for incident_id, incident in sorted(session.scene.incidents.items())
        ],
        width="stretch",
        hide_index=True,
    )


def _graph_panel(session: MissionSession) -> None:
    st.subheader("TaskGraph")
    if session.state is None:
        st.info("아직 생성된 임무가 없습니다.")
        return
    graph = session.state.graph
    st.dataframe(
        [
            {
                "task_id": task.task_id,
                "task_type": task.task_type.value,
                "target": task.target,
                "status": task.status.value,
            }
            for task in sorted(graph.tasks, key=lambda item: item.task_id)
        ],
        width="stretch",
        hide_index=True,
    )
    st.write("Dependencies")
    st.dataframe(
        [{"predecessor": pred, "successor": succ} for pred, succ in sorted(graph.edges)],
        width="stretch",
        hide_index=True,
    )


def _last_turn_panel(session: MissionSession) -> None:
    st.subheader("최근 자연어 처리 결과")
    if not session.turn_log:
        st.info("아직 처리한 발화가 없습니다.")
        return
    turn = session.turn_log[-1]
    left, right = st.columns(2)
    left.write("Intent / slots")
    left.json({"intent_kind": turn.intent_kind, "slots": turn.extracted_slots})
    right.write("Grounding")
    right.json(asdict(turn.grounding) if turn.grounding else {"status": "N/A"})

    st.write("MissionPatch diff / NO_CHANGE")
    if turn.outcome == "NO_CHANGE":
        st.info("NO_CHANGE — 현재 계획이 이미 요청 단계를 포함합니다.")
    elif turn.patch:
        st.json(
            {
                "added_tasks": turn.patch.added_tasks,
                "added_edges": turn.patch.added_edges,
                "directly_released_tasks": turn.patch.directly_released_tasks,
                "status_changes": turn.patch.status_changes,
            }
        )
    else:
        st.caption("이 턴에는 MissionPatch가 없습니다.")

    st.write("Validator")
    if turn.patch:
        st.json({"accepted": turn.patch.accepted, "error_codes": turn.patch.error_codes})
    elif turn.generation:
        st.json(
            {
                "accepted": turn.generation.approved,
                "error_codes": turn.generation.error_codes,
            }
        )
    else:
        st.caption("검증 대상 graph/patch가 없는 턴입니다.")

    if turn.online_reallocation is not None:
        online = turn.online_reallocation
        st.write("실행 중 selective release / rebid")
        st.json(
            {
                "policy": f"{online.policy} v{online.policy_version}",
                "simulation_time": online.simulation_time,
                "directly_affected_tasks": online.directly_affected_tasks,
                "released_tasks": online.selectively_released_tasks,
                "preserved_active_assignments": online.preserved_active_assignments,
                "assignment_changes": asdict(online.assignment_changes),
                "consensus_rounds": online.consensus_rounds,
            }
        )


def _plan_panel(session: MissionSession) -> None:
    st.subheader("Plan-time CBBA")
    if session.plan is None:
        st.info("할당 결과가 없습니다.")
    else:
        st.metric("Estimated makespan", f"{session.plan.estimated_makespan:.1f} s")
        st.dataframe(
            [
                {"task_id": task_id, "agent_id": agent_id}
                for task_id, agent_id in sorted(session.plan.assignments.items())
            ],
            width="stretch",
            hide_index=True,
        )

    st.write("이전 계획 대비 assignment 변화 (재할당 아님)")
    turn = session.turn_log[-1] if session.turn_log else None
    changes = turn.plan_assignment_changes if turn else None
    st.json(asdict(changes) if changes else {"added": {}, "removed": {}, "changed": {}})


def _execution_panel(session: MissionSession) -> None:
    st.subheader("2D 실행 결과")
    if session.phase is SessionPhase.EXECUTION_PAUSED and session.runtime is not None:
        runtime = session.runtime
        checkpoint = next(
            (
                event
                for event in reversed(session.event_log)
                if isinstance(event, CheckpointAudit)
            ),
            None,
        )
        st.info(
            "온라인 실행이 task 완료 경계에서 일시정지됐습니다. "
            "지금 후속 명령을 입력하거나 다음 완료까지 계속할 수 있습니다."
        )
        st.metric("Current simulation time", f"{runtime.now:.1f} s")
        if checkpoint is not None:
            st.write("이번 checkpoint에서 완료")
            st.write(", ".join(checkpoint.completed_now) or "없음")
            st.write("RUNNING")
            st.dataframe(
                [
                    {
                        "task_id": task_id,
                        "agent_id": value["agent_id"],
                        "finish_time": value["finish_time"],
                    }
                    for task_id, value in sorted(checkpoint.running.items())
                ],
                width="stretch",
                hide_index=True,
            )
            st.write("READY")
            st.write(", ".join(checkpoint.ready_tasks) or "없음")
        st.write("현재 active assignment")
        st.dataframe(
            [
                {"task_id": task_id, "agent_id": agent_id}
                for task_id, agent_id in sorted(runtime.assignments.items())
                if runtime.graph[task_id].status.value in {"ASSIGNED", "RUNNING"}
            ],
            width="stretch",
            hide_index=True,
        )
        return
    if session.execution is None:
        if session.phase is SessionPhase.EXECUTION_FAILED:
            st.error("최근 실행이 예외로 종료됐습니다. 감사 로그에서 원인을 확인하세요.")
        else:
            st.info("아직 실행하지 않았습니다.")
        return
    result = session.execution
    st.json(
        {
            "termination": result.termination.value,
            "makespan": result.makespan,
            "capability_violation_count": len(result.capability_violations),
            "precedence_violation_count": len(result.precedence_violations),
            "unfinished_tasks": result.unfinished_tasks,
        }
    )
    st.dataframe(
        [
            {"task_id": task_id, "agent_id": agent_id}
            for task_id, agent_id in sorted(result.assignments.items())
        ],
        width="stretch",
        hide_index=True,
    )


def _pending_controls(session: MissionSession, mode: str) -> None:
    pending = session.pending_clarification
    if pending is None:
        return
    last = session.turn_log[-1]
    question = last.grounding.clarification if last.grounding else "후보를 선택해 주세요."
    st.warning(question)
    columns = st.columns(len(pending.candidates) + 1)
    for column, candidate in zip(columns, pending.candidates, strict=False):
        if column.button(candidate, key=f"candidate-{pending.source_turn_id}-{candidate}"):
            result = select_clarification_candidate(session, candidate, mode=mode)
            _record(f"후보 선택: {candidate}", result.message)
            _persist(session)
            st.rerun()
    if columns[-1].button("취소", key=f"cancel-{pending.source_turn_id}"):
        result = cancel_clarification(session, mode=mode)
        _record("후보 선택 취소", result.message)
        _persist(session)
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="LLM-MRTA Operator Console", layout="wide")
    _initialise()
    session: MissionSession = st.session_state.mission_session

    st.title("LLM-MRTA Operator Console")
    mode = st.sidebar.selectbox("실행 모드", ("live", "cached", "mock"), index=0)
    st.sidebar.info(f"현재 응답 출처: {mode.upper()}")
    if mode == "live":
        st.sidebar.caption("실제 OpenAI API를 호출하며 성공 응답을 로컬 캐시에 기록합니다.")
    elif mode == "cached":
        st.sidebar.caption("정확히 같은 모델·문맥·발화의 저장 응답만 재생합니다.")
    else:
        st.sidebar.warning("MOCK: 연구 결과가 아닌 고정 발표 스크립트입니다.")
        with st.sidebar.expander("mock 명령 순서"):
            for number, command in enumerate(MOCK_COMMANDS, 1):
                st.write(f"{number}. {command}")
                if number == 2:
                    st.caption("↳ 표시되는 후보 중 FIRE_SITE_1을 선택")

    if st.sidebar.button("새 세션"):
        st.session_state.clear()
        st.rerun()

    st.sidebar.write(f"Session: `{session.session_id}`")
    st.sidebar.metric("Phase", session.phase.value)
    st.sidebar.write(f"Audit events: {len(session.event_log)}")

    st.subheader("운용자–LLM 대화")
    for message in st.session_state.chat:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    _pending_controls(session, mode)
    pending = session.pending_clarification is not None
    utterance = st.chat_input(
        "임무를 입력하거나 상태를 질문하세요",
        disabled=pending,
    )
    if utterance:
        result = handle_turn(session, utterance, _backend(mode))
        _record(utterance, result.message)
        _persist(session)
        st.rerun()

    one_shot_disabled = (
        session.state is None
        or session.plan is None
        or pending
        or session.runtime is not None
        or session.phase not in {SessionPhase.PLANNING, SessionPhase.EXECUTION_FAILED}
    )
    run_label = (
        "동일 graph 재시도"
        if session.phase is SessionPhase.EXECUTION_FAILED
        else "임무 실행"
    )
    # §19.1/D-041: an advance that died from an exception keeps its runtime, so
    # that state offers a retry rather than a dead end. Without the runtime it
    # was a one-shot failure and belongs to the one-shot button. With an
    # ExecutionResult it ended on DEADLOCK/STEP_LIMIT and is terminal (D-042).
    online_retryable = (
        session.phase is SessionPhase.EXECUTION_FAILED
        and session.runtime is not None
        and session.execution is None
    )
    online_resumable = (
        session.phase is SessionPhase.EXECUTION_PAUSED or online_retryable
    )
    online_disabled = (
        session.state is None
        or session.plan is None
        or pending
        or not (session.phase is SessionPhase.PLANNING or online_resumable)
    )
    online_label = (
        "마지막 checkpoint에서 온라인 실행 재시도"
        if online_retryable
        else "다음 task 완료까지 계속"
        if session.phase is SessionPhase.EXECUTION_PAUSED
        else "온라인 실행 시작"
    )
    one_shot_col, online_col = st.columns(2)
    if one_shot_col.button(run_label, type="primary", disabled=one_shot_disabled):
        audit = execute_session(session, mode=mode)
        text = f"실행 종료: {audit.execution_termination}, makespan {audit.makespan:.1f}s"
        if audit.error_type:
            text += f" ({audit.error_type}: {audit.error_detail})"
        _record("[한 번에 끝까지 실행]", text)
        _persist(session)
        st.rerun()
    if online_col.button(online_label, disabled=online_disabled):
        audit = advance_online_session(session, mode=mode)
        if isinstance(audit, CheckpointAudit):
            completed = ", ".join(audit.completed_now) or "없음"
            text = f"t={audit.simulation_time:.1f}s에서 일시정지 (완료: {completed})"
        else:
            text = f"실행 종료: {audit.execution_termination}, makespan {audit.makespan:.1f}s"
            if audit.error_type:
                text += f" ({audit.error_type}: {audit.error_detail})"
        _record("[온라인 실행: 다음 완료 이벤트]", text)
        _persist(session)
        st.rerun()

    left, right = st.columns(2)
    with left:
        _scene_panel(session)
        _last_turn_panel(session)
    with right:
        _graph_panel(session)
        _plan_panel(session)
    _execution_panel(session)


if __name__ == "__main__":
    main()
