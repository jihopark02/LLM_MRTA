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
import time
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
from execution.executor import SimExecutor, Termination
from interaction.audit import CheckpointAudit, ExecutionAudit
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
PLAYBACK_FRAMES = 18
PLAYBACK_WALL_SECONDS = 3.0


def _new_session() -> MissionSession:
    return MissionSession(f"ui-{uuid4().hex[:12]}", load_scene(SCENE_PATH))


def _initialise() -> None:
    if "mission_session" not in st.session_state:
        st.session_state.mission_session = _new_session()
        st.session_state.chat = []
        st.session_state.backends = {}


def _playback_figure(frame):
    """Draw one P10 frame, or ``None`` when optional viz is unavailable."""
    try:
        from demo.visualization import render_playback_frame

        return render_playback_frame(frame)
    except ImportError:
        return None


def _playback_panel(enabled: bool, speed: int) -> None:
    """Synchronously replay one committed segment, then expose the checkpoint.

    Streamlit does not process another widget event while this run is drawing
    frames.  Execution has already committed, so a draw/import failure only
    degrades the view and can never roll the simulator back (§20.4).
    """
    error = st.session_state.pop("pending_playback_error", None)
    if error is not None:
        st.warning(
            "실행은 checkpoint에 반영됐지만 애니메이션을 만들지 못했습니다: "
            f"{error}. 정적 Runtime 지도와 표를 사용하세요."
        )
    playback = st.session_state.pop("pending_playback", None)
    if playback is None:
        return
    st.session_state.last_playback = playback
    if not enabled:
        st.info(
            f"화면 재생을 건너뛰었습니다 (simulation t={playback.start_time:.1f}"
            f"→{playback.end_time:.1f}s). 실행 결과는 그대로 반영됐습니다."
        )
        return

    st.subheader("Checkpoint 구간 2D 애니메이션")
    st.caption(
        "기록된 discrete-event schedule의 보간입니다. 실제 robot telemetry나 물리 pose가 아닙니다."
    )
    holder = st.empty()
    progress = st.progress(0.0)
    wall_seconds = float(os.environ.get("LLM_MRTA_PLAYBACK_SECONDS", PLAYBACK_WALL_SECONDS))
    delay = max(0.0, wall_seconds) / speed / max(1, len(playback.frames) - 1)
    for index, frame in enumerate(playback.frames):
        figure = _playback_figure(frame)
        if figure is None:
            st.warning(
                "애니메이션 렌더러를 불러오지 못했습니다. 실행은 보존되며 정적 지도로 전환합니다."
            )
            progress.empty()
            return
        holder.pyplot(figure)
        figure.clear()
        progress.progress((index + 1) / len(playback.frames))
        if index + 1 < len(playback.frames) and delay:
            time.sleep(delay)
    progress.empty()
    st.success(
        f"구간 재생 완료: simulation t={playback.start_time:.1f}"
        f"→{playback.end_time:.1f}s. 지금 후속 명령을 입력할 수 있습니다."
    )


def _queue_playback(session: MissionSession, before) -> None:
    """Build a view from the committed runtime; never alter execution state."""
    if session.runtime is None:
        return
    after = session.runtime.checkpoint()
    if after.now <= before.now:
        return
    try:
        from demo.animation import build_playback_spec

        frame_count = int(os.environ.get("LLM_MRTA_PLAYBACK_FRAMES", PLAYBACK_FRAMES))
        st.session_state.pending_playback = build_playback_spec(
            session.scene, before, after, frame_count=frame_count
        )
    except Exception as exc:  # noqa: BLE001 - view failure must not undo execution
        st.session_state.pending_playback_error = f"{type(exc).__name__}: {exc}"


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


#: Shown instead of the DAG when the optional drawing stack is missing.
VIZ_MISSING_NOTE = (
    "그래프 그림은 `pip install -e '.[viz]'` 후에 표시됩니다. 아래 표는 그대로 사용할 수 있습니다."
)


def _dag_figure(graph):
    """The DAG figure, or ``None`` when the drawing stack is unavailable.

    Both the module import and the draw are guarded (§18.14, D-044).
    ``demo.visualization`` deliberately keeps matplotlib out of its import path
    today, but the console must survive either step failing — a missing ``viz``
    extra degrades to the tables below, it does not take the app down.
    """
    try:
        from demo.visualization import dag_render_spec, render_task_graph

        return render_task_graph(dag_render_spec(graph))
    except ImportError:
        return None


def _graph_panel(session: MissionSession) -> None:
    st.subheader("TaskGraph")
    if session.state is None:
        st.info("아직 생성된 임무가 없습니다.")
        return
    graph = session.state.graph

    figure = _dag_figure(graph)
    if figure is None:
        st.caption(VIZ_MISSING_NOTE)
    else:
        st.pyplot(figure)

    # The tables stay: they are the auditable form, and they must remain
    # reachable whether or not the figure rendered.
    with st.expander("TaskGraph 표", expanded=figure is None):
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
            [
                {"predecessor": pred, "successor": succ}
                for pred, succ in sorted(graph.edges)
            ],
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


def _show_figure(figure) -> None:
    """Render a figure and release it.

    Figures are built without pyplot, so none is registered globally; clearing
    after Streamlit has marshalled the element keeps repeated reruns from
    holding on to artists.
    """
    st.pyplot(figure)
    figure.clear()


def _map_figure(spec):
    """Draw one map, or ``None`` when the drawing stack is unavailable.

    The guard belongs here, not around spec building: specs are deliberately
    matplotlib-free (P8.5a/e), so guarding *those* imports proves nothing and
    lets the ImportError escape from the draw instead (D-044).
    """
    try:
        from demo.visualization import render_mission_map

        return render_mission_map(spec)
    except ImportError:
        return None


def _mission_map_specs(session: MissionSession):
    """``(tab label, spec)`` for the maps this phase may show.

    Plan-time is always available once a mission is planned. The second map
    depends on the phase and is never overlaid on the first: a paused run shows
    its runtime, a completed run shows what it drove, and a failed run shows
    neither — ``execution_map_spec`` refuses a non-COMPLETED result because its
    departed tasks never arrived.
    """
    try:
        from demo.visualization import (
            execution_map_spec,
            plan_map_spec,
            runtime_map_spec,
        )
    except ImportError:      # only if the spec module itself grows a hard dep
        return None

    specs = [
        ("Plan-time", plan_map_spec(session.scene, session.state.graph, session.plan))
    ]
    if session.phase is SessionPhase.EXECUTION_PAUSED and session.runtime is not None:
        specs.append(("Runtime", runtime_map_spec(session.scene, session.runtime)))
    elif (
        session.phase is SessionPhase.EXECUTED
        and session.execution is not None
        and session.execution.termination is Termination.COMPLETED
    ):
        specs.append(
            (
                "Execution",
                execution_map_spec(
                    session.scene, session.state.graph, session.execution
                ),
            )
        )
    return specs


def _post_plan_tasks(session: MissionSession) -> set[str]:
    """Tasks in the graph that the stored plan never saw.

    ``assignments | unassigned_tasks`` is the plan's full task set, so this is
    exactly what a later online UPDATE added — not merely "something was left
    unassigned at plan time".
    """
    planned = set(session.plan.assignments) | set(session.plan.unassigned_tasks)
    return {task.task_id for task in session.state.graph.tasks} - planned


def _plan_staleness_note(session: MissionSession) -> None:
    """Explain the Plan-time map only when it is actually out of date.

    A paused UPDATE deliberately does not recompute ``session.plan`` (§18.9
    keeps plan-time analysis and runtime assignment apart), while the task
    markers come from the current graph. When those disagree the added tasks
    look like planned work nobody was assigned, so say what happened — and
    point at a tab that exists in this phase, since ``session.runtime`` outlives
    the paused state.
    """
    if not _post_plan_tasks(session):
        return
    if session.phase is SessionPhase.EXECUTION_PAUSED:
        destination = "실제 온라인 배정은 Runtime 탭을 확인하세요."
    elif session.phase is SessionPhase.EXECUTED:
        destination = "실제 완료 경로는 Execution 탭을 확인하세요."
    else:
        destination = "실행 실패 상태와 감사 기록을 확인하세요."
    st.caption(
        "이 계획은 실행을 시작하기 전의 분석입니다. 이후 추가된 task는 지도에 표시되지만 "
        f"계획 경로가 없습니다 — {destination}"
    )


def _failure_note(session: MissionSession) -> str | None:
    if session.phase is not SessionPhase.EXECUTION_FAILED:
        return None
    if session.execution is not None:
        return (
            f"실행이 `{session.execution.termination.value}`로 끝났습니다. "
            "완료 실행 지도는 표시하지 않습니다 — 출발했지만 도착하지 않은 task가 있습니다."
        )
    audit = next(
        (e for e in reversed(session.event_log) if isinstance(e, ExecutionAudit)), None
    )
    detail = f"{audit.error_type}: {audit.error_detail}" if audit else "원인 미기록"
    return f"실행이 예외로 중단됐습니다 ({detail}). 완료 실행 지도는 표시하지 않습니다."


def _map_panel(session: MissionSession) -> None:
    st.subheader("2D 임무 지도")
    if session.state is None or session.plan is None:
        st.info("임무를 생성하면 지도가 표시됩니다.")
        return

    note = _failure_note(session)
    if note is not None:
        st.warning(note)

    specs = _mission_map_specs(session)
    if specs is None:
        st.caption(VIZ_MISSING_NOTE)
        return
    drawn = [(label, spec, _map_figure(spec)) for label, spec in specs]
    if any(figure is None for _, _, figure in drawn):
        # Release whatever did draw before bailing out, so a partial failure
        # leaves nothing behind.
        for _, _, figure in drawn:
            if figure is not None:
                figure.clear()
        st.caption(VIZ_MISSING_NOTE)
        return
    tabs = st.tabs([label for label, _, _ in drawn])
    for tab, (label, spec, figure) in zip(tabs, drawn, strict=True):
        with tab:
            _show_figure(figure)
            st.caption(f"{label} · agent {len(spec.agents)}기 · leg {len(spec.legs)}개")
            if label == "Plan-time":
                _plan_staleness_note(session)


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
    playback_enabled = st.sidebar.checkbox("checkpoint 구간 애니메이션", value=True)
    playback_speed = st.sidebar.selectbox(
        "애니메이션 배속 (표시 전용)", (1, 2, 5), index=1, format_func=lambda value: f"{value}x"
    )
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

    # A queued segment was already committed by the preceding button action.
    # Replay it before rendering any interactive controls for this run.
    _playback_panel(playback_enabled, playback_speed)

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
        before = (
            session.runtime.checkpoint()
            if session.runtime is not None
            else SimExecutor(session.state, session.scene).checkpoint()
        )
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
        _queue_playback(session, before)
        st.rerun()

    left, right = st.columns(2)
    with left:
        _scene_panel(session)
        _last_turn_panel(session)
    with right:
        _graph_panel(session)
        _plan_panel(session)
    _map_panel(session)
    _execution_panel(session)


if __name__ == "__main__":
    main()
