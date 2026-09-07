"""P8.3 Streamlit smoke test; skipped when the optional demo extra is absent."""

import json
from pathlib import Path

import pytest

from demo.mock_script import MOCK_COMMANDS

streamlit = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).parents[1] / "demo" / "app.py"


def _submit(at: AppTest, command: str) -> AppTest:
    return at.chat_input[0].set_value(command).run()


def test_streamlit_mock_path_renders_planning_clarification_and_execution(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LLM_MRTA_RUNTIME_ROOT", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=20).run()

    assert not at.exception
    assert at.title[0].value == "LLM-MRTA Operator Console"
    assert at.selectbox[0].value == "live"
    assert {item.value for item in at.subheader} == {
        "운용자–LLM 대화",
        "Semantic scene",
        "최근 자연어 처리 결과",
        "TaskGraph",
        "Plan-time CBBA",
        "2D 임무 지도",
        "2D 실행 결과",
    }
    assert next(button for button in at.button if button.label == "임무 실행").disabled

    at = at.selectbox[0].select("mock").run()
    at = _submit(at, MOCK_COMMANDS[0])
    assert not at.exception
    assert ("Estimated makespan", "359.8 s") in [
        (metric.label, metric.value) for metric in at.metric
    ]
    assert not next(button for button in at.button if button.label == "임무 실행").disabled

    at = _submit(at, MOCK_COMMANDS[1])
    assert at.chat_input[0].disabled
    assert next(button for button in at.button if button.label == "임무 실행").disabled
    assert {button.label for button in at.button} >= {
        "FIRE_SITE_1",
        "FIRE_SITE_2",
        "취소",
    }

    at = next(button for button in at.button if button.label == "FIRE_SITE_1").click().run()
    assert not at.chat_input[0].disabled
    run = next(button for button in at.button if button.label == "임무 실행")
    at = run.click().run()

    assert not at.exception
    assert ("Phase", "EXECUTED") in [(metric.label, metric.value) for metric in at.metric]
    assert next(button for button in at.button if button.label == "임무 실행").disabled
    audit_files = list((tmp_path / "interaction_runs").glob("*.json"))
    assert len(audit_files) == 1


def test_streamlit_mock_path_accepts_an_update_while_execution_is_paused(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LLM_MRTA_RUNTIME_ROOT", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=20).run()
    at = at.selectbox[0].select("mock").run()
    at = _submit(at, MOCK_COMMANDS[0])

    start = next(button for button in at.button if button.label == "온라인 실행 시작")
    at = start.click().run()
    assert not at.exception
    assert ("Phase", "EXECUTION_PAUSED") in [
        (metric.label, metric.value) for metric in at.metric
    ]
    assert not at.chat_input[0].disabled
    assert any(metric.label == "Current simulation time" for metric in at.metric)

    # Consume the scripted ambiguous query, select its structured candidate,
    # then report and extend a genuinely new incident while still paused.
    at = _submit(at, MOCK_COMMANDS[1])
    at = next(button for button in at.button if button.label == "FIRE_SITE_1").click().run()
    at = _submit(at, MOCK_COMMANDS[2])
    at = _submit(at, MOCK_COMMANDS[3])
    assert not at.exception
    assert ("Phase", "EXECUTION_PAUSED") in [
        (metric.label, metric.value) for metric in at.metric
    ]
    assert any("selective release / rebid" in item.value for item in at.markdown)

    for _ in range(30):
        phase = next(metric.value for metric in at.metric if metric.label == "Phase")
        if phase == "EXECUTED":
            break
        button = next(
            button for button in at.button if button.label == "다음 task 완료까지 계속"
        )
        at = button.click().run()
        assert not at.exception
    assert next(metric.value for metric in at.metric if metric.label == "Phase") == "EXECUTED"

    audit_file = next((tmp_path / "interaction_runs").glob("*.json"))
    payload = json.loads(audit_file.read_text(encoding="utf-8"))
    event_types = [event["event_type"] for event in payload["events"]]
    assert "EXECUTION_CHECKPOINT" in event_types
    assert event_types[-1] == "EXECUTION"
    online_turns = [
        event
        for event in payload["events"]
        if event["event_type"] == "TURN" and event["online_reallocation"] is not None
    ]
    assert len(online_turns) == 1
    assert online_turns[0]["online_reallocation"]["policy"] == "selective"


# -- online retry button states (§19.1 table, D-042) ----------------------


def _paused_app(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MRTA_RUNTIME_ROOT", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=20).run()
    at = at.selectbox[0].select("mock").run()
    at = _submit(at, MOCK_COMMANDS[0])
    start = next(button for button in at.button if button.label == "온라인 실행 시작")
    return start.click().run()


def _online_button(at):
    labels = {
        "온라인 실행 시작",
        "다음 task 완료까지 계속",
        "마지막 checkpoint에서 온라인 실행 재시도",
    }
    return next(button for button in at.button if button.label in labels)


def test_an_exception_failure_offers_the_checkpoint_retry_button(tmp_path, monkeypatch):
    from execution.executor import SimExecutor

    at = _paused_app(tmp_path, monkeypatch)

    def boom(self, *args, **kwargs):
        raise RuntimeError("sim exploded")

    # Scoped, not undo(): undo() would also revert _paused_app's
    # LLM_MRTA_RUNTIME_ROOT, and the next rerun would write its audit JSON into
    # the real repository instead of tmp_path.
    with monkeypatch.context() as failure_patch:
        failure_patch.setattr(SimExecutor, "advance_to_next_completion", boom)
        at = _online_button(at).click().run()
        assert not at.exception
        assert ("Phase", "EXECUTION_FAILED") in [
            (metric.label, metric.value) for metric in at.metric
        ]

    at = at.run()
    retry = _online_button(at)
    assert retry.label == "마지막 checkpoint에서 온라인 실행 재시도"
    assert not retry.disabled
    # one-shot must not adopt the online runtime
    assert next(b for b in at.button if b.label.startswith(("임무 실행", "동일 graph"))).disabled

    at = retry.click().run()
    assert not at.exception
    assert ("Phase", "EXECUTION_PAUSED") in [
        (metric.label, metric.value) for metric in at.metric
    ]


def test_a_terminal_deadlock_does_not_offer_a_retry(tmp_path, monkeypatch):
    from execution.executor import CompletionAdvance, SimExecutor, Termination

    at = _paused_app(tmp_path, monkeypatch)

    def deadlocked(self, *args, **kwargs):
        return CompletionAdvance(
            self.checkpoint(), (), self._result(Termination.DEADLOCK)
        )

    with monkeypatch.context() as failure_patch:
        failure_patch.setattr(SimExecutor, "advance_to_next_completion", deadlocked)
        at = _online_button(at).click().run()
        assert not at.exception
        assert ("Phase", "EXECUTION_FAILED") in [
            (metric.label, metric.value) for metric in at.metric
        ]

    at = at.run()
    # DEADLOCK is a result, not a crash: the run is over, so no resume is offered.
    assert _online_button(at).disabled


# -- DAG panel and viz degrade (§18.14, D-044) ----------------------------


class _BlockMatplotlib:
    """Import hook that makes matplotlib look uninstalled."""

    def find_spec(self, name, path=None, target=None):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ImportError(f"No module named {name!r}")
        return None


@pytest.fixture
def without_matplotlib():
    import sys

    saved = {
        name: module
        for name, module in sys.modules.items()
        if name == "matplotlib" or name.startswith("matplotlib.")
    }
    for name in saved:
        del sys.modules[name]
    hook = _BlockMatplotlib()
    sys.meta_path.insert(0, hook)
    try:
        yield
    finally:
        sys.meta_path.remove(hook)
        sys.modules.update(saved)


def _planned_app(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MRTA_RUNTIME_ROOT", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=20).run()
    at = at.selectbox[0].select("mock").run()
    return _submit(at, MOCK_COMMANDS[0])


def test_the_graph_panel_draws_the_dag_and_keeps_the_table(tmp_path, monkeypatch):
    at = _planned_app(tmp_path, monkeypatch)
    assert not at.exception
    # st.pyplot surfaces as an Image: the DAG plus the Plan-time map
    assert len(at.image) == 2
    assert any("TaskGraph 표" in item.label for item in at.expander)
    # the auditable table is still reachable underneath the figure
    assert any(
        "task_id" in str(frame.value) for frame in at.dataframe
    ), "the TaskGraph table must survive alongside the figure"


def test_the_console_still_runs_without_matplotlib(
    tmp_path, monkeypatch, without_matplotlib
):
    from demo.app import VIZ_MISSING_NOTE

    at = _planned_app(tmp_path, monkeypatch)

    # Not "the call failed and was caught" — matplotlib genuinely cannot be
    # imported here, and the console still starts and answers a turn (D-044).
    assert not at.exception
    assert list(at.image) == []
    assert any(VIZ_MISSING_NOTE in item.value for item in at.caption)
    assert any("task_id" in str(frame.value) for frame in at.dataframe)
    assert ("Estimated makespan", "359.8 s") in [
        (metric.label, metric.value) for metric in at.metric
    ]


def test_an_update_made_while_paused_reaches_the_dag_and_both_maps(
    tmp_path, monkeypatch
):
    at = _planned_app(tmp_path, monkeypatch)
    at = next(b for b in at.button if b.label == "온라인 실행 시작").click().run()

    at = _submit(at, MOCK_COMMANDS[1])
    at = next(b for b in at.button if b.label == "FIRE_SITE_1").click().run()
    at = _submit(at, MOCK_COMMANDS[2])          # report a new incident
    at = _submit(at, MOCK_COMMANDS[3])          # extend it — new tasks appear
    assert not at.exception
    # DAG + both map tabs (Streamlit renders every tab's body each run)
    assert len(at.image) == 3

    # the new incident's chain is in the graph the panel just drew
    session = at.session_state["mission_session"]
    from demo.app import _mission_map_specs
    from demo.visualization import dag_render_spec

    spec = dag_render_spec(session.state.graph)
    assert "FIRE_SITE_3" in spec.row_labels
    assert spec.task_ids == {task.task_id for task in session.state.graph.tasks}

    # ...and in both 2D maps, not just the DAG (§15 P8.5: an online update must
    # show up on the next render).
    added = {
        task.task_id
        for task in session.state.graph.tasks
        if task.target == "FIRE_SITE_3"
    }
    assert added, "the scripted update must have added the new incident's chain"

    maps = dict((label, spec) for label, spec in _mission_map_specs(session))
    assert set(maps) == {"Plan-time", "Runtime"}
    for label, map_spec in maps.items():
        drawn = {point.entity_id for point in map_spec.task_points}
        assert added <= drawn, f"{label} map is missing the new tasks"
    assert "FIRE_SITE_3" in {
        point.entity_id for point in maps["Runtime"].incidents
    }
    assert "FIRE_SITE_3" in {
        point.entity_id for point in maps["Plan-time"].incidents
    }

    # The plan predates the online update and is not recomputed by a paused
    # UPDATE, so the new tasks appear as markers with no planned route. Say so,
    # or they read as planned work nobody was assigned.
    assert not [leg for leg in maps["Plan-time"].legs if leg.task_id in added]
    assert [leg for leg in maps["Runtime"].legs if leg.task_id in added]
    assert any("Runtime 탭을 확인하세요" in item.value for item in at.caption)


# -- 2D map tabs (§18.14, P8.5g) -----------------------------------------


def _map_tab_labels(at):
    return [
        tab.label
        for tab in at.get("tab")
        if tab.label in {"Plan-time", "Runtime", "Execution"}
    ]


def test_planning_shows_only_the_plan_time_map(tmp_path, monkeypatch):
    at = _planned_app(tmp_path, monkeypatch)
    assert not at.exception
    assert _map_tab_labels(at) == ["Plan-time"]


def test_a_paused_run_adds_a_runtime_map(tmp_path, monkeypatch):
    at = _planned_app(tmp_path, monkeypatch)
    at = next(b for b in at.button if b.label == "온라인 실행 시작").click().run()

    assert not at.exception
    assert ("Phase", "EXECUTION_PAUSED") in [
        (metric.label, metric.value) for metric in at.metric
    ]
    assert _map_tab_labels(at) == ["Plan-time", "Runtime"]
    assert "Execution" not in _map_tab_labels(at)


def test_a_completed_run_adds_an_execution_map(tmp_path, monkeypatch):
    at = _planned_app(tmp_path, monkeypatch)
    at = next(b for b in at.button if b.label == "임무 실행").click().run()

    assert not at.exception
    assert ("Phase", "EXECUTED") in [
        (metric.label, metric.value) for metric in at.metric
    ]
    assert _map_tab_labels(at) == ["Plan-time", "Execution"]


def test_a_failed_run_shows_the_plan_only_and_names_the_cause(tmp_path, monkeypatch):
    from execution.executor import SimExecutor

    at = _planned_app(tmp_path, monkeypatch)
    with monkeypatch.context() as failure_patch:
        failure_patch.setattr(
            SimExecutor, "run", lambda self, *a, **k: (_ for _ in ()).throw(
                RuntimeError("sim exploded")
            )
        )
        at = next(b for b in at.button if b.label == "임무 실행").click().run()

    assert not at.exception
    assert ("Phase", "EXECUTION_FAILED") in [
        (metric.label, metric.value) for metric in at.metric
    ]
    # No completed-execution map for a run that did not complete (§18.14).
    assert _map_tab_labels(at) == ["Plan-time"]
    assert any("RuntimeError" in item.value for item in at.warning)


def test_a_rerun_redraws_without_recomputing_the_plan_or_the_run(
    tmp_path, monkeypatch
):
    """Rendering must read what is stored, never recompute it."""
    import allocation.allocate as allocate_module
    from execution.executor import SimExecutor

    at = _planned_app(tmp_path, monkeypatch)
    at = next(b for b in at.button if b.label == "임무 실행").click().run()
    assert _map_tab_labels(at) == ["Plan-time", "Execution"]

    def forbidden(*args, **kwargs):
        raise AssertionError("the map panel must not recompute")

    with monkeypatch.context() as no_recompute:
        no_recompute.setattr(allocate_module, "allocate", forbidden)
        no_recompute.setattr(SimExecutor, "run", forbidden)
        no_recompute.setattr(SimExecutor, "advance_to_next_completion", forbidden)
        at = at.run()

    assert not at.exception
    assert _map_tab_labels(at) == ["Plan-time", "Execution"]
    assert len(at.image) == 3


def test_repeated_reruns_do_not_accumulate_figures(tmp_path, monkeypatch):
    at = _planned_app(tmp_path, monkeypatch)
    for _ in range(3):
        at = at.run()
        assert not at.exception

    # Figures are created without pyplot, so none is registered globally and
    # nothing piles up across reruns.
    import matplotlib.pyplot as plt

    assert plt.get_fignums() == []
    assert len(at.image) == 2


def test_without_matplotlib_the_map_panel_falls_back_but_controls_remain(
    tmp_path, monkeypatch, without_matplotlib
):
    from demo.app import VIZ_MISSING_NOTE

    at = _planned_app(tmp_path, monkeypatch)

    assert not at.exception
    assert list(at.image) == []
    assert _map_tab_labels(at) == []
    # the fallback note appears for both the DAG and the map panel
    assert sum(VIZ_MISSING_NOTE in item.value for item in at.caption) == 2
    # and the console is still operable
    assert not next(b for b in at.button if b.label == "임무 실행").disabled
    assert not next(b for b in at.button if b.label == "온라인 실행 시작").disabled


# -- the Plan-time map must describe the state it is actually in ----------


def _stale_captions(at):
    return [c.value for c in at.caption if "계획 경로가 없습니다" in c.value]


def test_pausing_without_an_update_shows_no_stale_plan_note(tmp_path, monkeypatch):
    at = _planned_app(tmp_path, monkeypatch)
    at = next(b for b in at.button if b.label == "온라인 실행 시작").click().run()

    assert not at.exception
    # Starting an online run is not an update: the plan still covers every task,
    # so claiming tasks were added would be false.
    assert _map_tab_labels(at) == ["Plan-time", "Runtime"]
    assert _stale_captions(at) == []


def test_a_completed_run_after_an_update_points_at_the_execution_tab(
    tmp_path, monkeypatch
):
    at = _planned_app(tmp_path, monkeypatch)
    at = next(b for b in at.button if b.label == "온라인 실행 시작").click().run()
    at = _submit(at, MOCK_COMMANDS[1])
    at = next(b for b in at.button if b.label == "FIRE_SITE_1").click().run()
    at = _submit(at, MOCK_COMMANDS[2])
    at = _submit(at, MOCK_COMMANDS[3])
    assert _stale_captions(at), "the paused state must already be explained"

    for _ in range(40):
        phase = next(m.value for m in at.metric if m.label == "Phase")
        if phase != "EXECUTION_PAUSED":
            break
        at = next(
            b for b in at.button if b.label == "다음 task 완료까지 계속"
        ).click().run()

    assert next(m.value for m in at.metric if m.label == "Phase") == "EXECUTED"
    assert _map_tab_labels(at) == ["Plan-time", "Execution"]
    # session.runtime outlives the paused phase, so the note must follow the
    # phase rather than the runtime's mere existence.
    note = _stale_captions(at)
    assert note and "Execution 탭을 확인하세요" in note[0]
    assert "Runtime 탭" not in note[0]


def test_a_failed_run_never_points_at_a_tab_that_is_not_shown(tmp_path, monkeypatch):
    from execution.executor import SimExecutor

    at = _planned_app(tmp_path, monkeypatch)
    at = next(b for b in at.button if b.label == "온라인 실행 시작").click().run()
    at = _submit(at, MOCK_COMMANDS[1])
    at = next(b for b in at.button if b.label == "FIRE_SITE_1").click().run()
    at = _submit(at, MOCK_COMMANDS[2])
    at = _submit(at, MOCK_COMMANDS[3])

    with monkeypatch.context() as failure_patch:
        failure_patch.setattr(
            SimExecutor,
            "advance_to_next_completion",
            lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("sim exploded")),
        )
        at = next(
            b for b in at.button if b.label == "다음 task 완료까지 계속"
        ).click().run()

    assert next(m.value for m in at.metric if m.label == "Phase") == "EXECUTION_FAILED"
    assert _map_tab_labels(at) == ["Plan-time"]
    note = _stale_captions(at)
    assert note
    assert "Runtime 탭" not in note[0] and "Execution 탭" not in note[0]


@pytest.mark.parametrize("phase_action", ["pause", "run"])
def test_the_plan_title_never_claims_nothing_has_run(tmp_path, monkeypatch, phase_action):
    from demo.app import _mission_map_specs
    from demo.visualization import MAP_MODE_TITLES, render_mission_map

    at = _planned_app(tmp_path, monkeypatch)
    label = "온라인 실행 시작" if phase_action == "pause" else "임무 실행"
    at = next(b for b in at.button if b.label == label).click().run()

    session = at.session_state["mission_session"]
    plan_spec = dict(_mission_map_specs(session))["Plan-time"]
    figure = render_mission_map(plan_spec)
    try:
        # A slide exported on its own must not carry a claim that is false for
        # the state it was taken from.
        title = figure.axes[0].get_title(loc="left")
        assert "nothing has run" not in title
        assert MAP_MODE_TITLES["plan"] in title
    finally:
        figure.clear()
