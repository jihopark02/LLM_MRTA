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
