"""P12 live/mock counterfactual evaluation for incident contingencies (§22.4).

Run from the repository root:

    python3 -m evaluation.incident_contingency --mock
    python3 -m evaluation.incident_contingency --out data/eval_results/p12_gpt-5-mini
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from core.enums import TaskType
from interaction.audit import IncidentObservationAudit
from interaction.audit_io import session_audit_payload
from interaction.ground import chain_prefix
from interaction.observe import apply_fire_observation
from interaction.online_execute import advance_online_session
from interaction.orchestrator import TurnOutcome, handle_turn
from interaction.schemas import UpToStep, wire_intent
from interaction.session import MissionSession, SessionPhase
from llm.backend import DEFAULT_MODEL, MockBackend
from llm.schemas import LLMTask, Step1Output, Step2Output
from scenarios.latent import SimulatedFireSource, load_latent_incident_fixture
from scenarios.scene import load_scene
from validator.hashing import VALIDATOR_VERSION, scene_hash

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANNOTATION = ROOT / "data" / "p12_counterfactual.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PolicyCase(_Strict):
    id: str
    command: str
    expected_policy: UpToStep | None
    expected_response_tasks: list[UpToStep]


class ReportCase(_Strict):
    id: str
    initial_command: str
    report_command: str
    expected_zone: str
    expected_response_up_to: UpToStep


class UnsupportedCase(_Strict):
    id: str
    command: str
    expected_outcome: Literal["UNSUPPORTED"]


class CounterfactualAnnotation(_Strict):
    annotation_version: Literal["p12-v1"]
    scene: str
    latent_fixture: str
    expected_initial_tasks: list[str]
    policy_cases: list[PolicyCase]
    report_cases: list[ReportCase]
    unsupported_cases: list[UnsupportedCase]


def load_annotation(path: str | Path = DEFAULT_ANNOTATION) -> CounterfactualAnnotation:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    annotation = CounterfactualAnnotation.model_validate(raw)
    ids = [
        case.id
        for cases in (
            annotation.policy_cases,
            annotation.report_cases,
            annotation.unsupported_cases,
        )
        for case in cases
    ]
    if len(ids) != len(set(ids)):
        raise ValueError("counterfactual case ids must be unique")
    expected_initial = {
        f"{TaskType.AREA_RECON.value}:{zone}" for zone in ("ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D")
    }
    if set(annotation.expected_initial_tasks) != expected_initial:
        raise ValueError("expected_initial_tasks must be the four patrol AREA_RECON tasks")
    return annotation


@dataclass(frozen=True, slots=True)
class CounterfactualCaseResult:
    id: str
    family: str
    commands: tuple[str, ...]
    expected: dict
    actual: dict
    exact: bool
    termination: str | None
    capability_violations: tuple[str, ...]
    precedence_violations: tuple[str, ...]
    released_tasks: tuple[str, ...]
    resolved_models: tuple[str, ...]
    session_audit: dict
    harness_error: str | None = None


@dataclass(frozen=True, slots=True)
class CounterfactualRun:
    annotation_version: str
    backend_mode: str
    requested_model: str | None
    scene_hash: str
    validator_version: str
    started_at: str
    finished_at: str
    cases: tuple[CounterfactualCaseResult, ...] = field(default_factory=tuple)

    @property
    def exact_count(self) -> int:
        return sum(case.exact for case in self.cases)


BackendFactory = Callable[[str, object], object]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _initial_tasks(annotation: CounterfactualAnnotation) -> list[LLMTask]:
    return [
        LLMTask(task_type=task.split(":", 1)[0], target=task.split(":", 1)[1])
        for task in annotation.expected_initial_tasks
    ]


def mock_backend_factory(annotation: CounterfactualAnnotation) -> BackendFactory:
    tasks = _initial_tasks(annotation)

    def factory(_case_id: str, case: object) -> MockBackend:
        if isinstance(case, PolicyCase):
            script = [
                wire_intent(
                    "NEW_MISSION",
                    incident_response_up_to=case.expected_policy,
                ),
                Step1Output(tasks=tasks),
                Step2Output(edges=[]),
            ]
        elif isinstance(case, ReportCase):
            script = [
                wire_intent("NEW_MISSION"),
                Step1Output(tasks=tasks),
                Step2Output(edges=[]),
                wire_intent(
                    "REPORT_INCIDENT",
                    zone_ref=case.expected_zone,
                    response_up_to=case.expected_response_up_to,
                ),
            ]
        else:
            script = [wire_intent("UNSUPPORTED", note="resource constraint")]
        return MockBackend(script)

    return factory


def _task_keys(session: MissionSession) -> list[str]:
    if session.state is None:
        return []
    return sorted(f"{task.task_type.value}:{task.target}" for task in session.state.graph.tasks)


def _response_steps(session: MissionSession, incident_id: str | None) -> list[str]:
    if session.state is None or incident_id is None:
        return []
    return sorted(
        task.task_type.value
        for task in session.state.graph.tasks
        if task.target == incident_id and task.task_type is not TaskType.AREA_RECON
    )


def _finish_execution(session: MissionSession, mode: str) -> None:
    while session.phase in {SessionPhase.PLANNING, SessionPhase.EXECUTION_PAUSED}:
        advance_online_session(session, mode=mode)


def _result_common(
    case_id: str,
    family: str,
    commands: tuple[str, ...],
    expected: dict,
    actual: dict,
    exact: bool,
    session: MissionSession,
    backend: object,
    released: tuple[str, ...] = (),
    error: str | None = None,
) -> CounterfactualCaseResult:
    execution = session.execution
    return CounterfactualCaseResult(
        id=case_id,
        family=family,
        commands=commands,
        expected=expected,
        actual=actual,
        exact=exact and error is None,
        termination=execution.termination.value if execution is not None else None,
        capability_violations=(
            tuple(execution.capability_violations) if execution is not None else ()
        ),
        precedence_violations=(
            tuple(execution.precedence_violations) if execution is not None else ()
        ),
        released_tasks=released,
        resolved_models=tuple(getattr(backend, "resolved_models", ())),
        session_audit=session_audit_payload(session),
        harness_error=error,
    )


def _run_policy_case(
    annotation: CounterfactualAnnotation,
    case: PolicyCase,
    backend: object,
) -> CounterfactualCaseResult:
    scene = load_scene(ROOT / annotation.scene)
    session = MissionSession(f"p12-{case.id.lower().replace('_', '-')}", scene)
    expected = {
        "initial_tasks": sorted(annotation.expected_initial_tasks),
        "policy": case.expected_policy,
        "response_tasks": sorted(case.expected_response_tasks),
        "observation_source": "SENSOR_SIMULATED",
    }
    error = None
    observation_audit: IncidentObservationAudit | None = None
    try:
        initial = handle_turn(session, case.command, backend)
        initial_keys = _task_keys(session)
        initial_exact = (
            initial.outcome is TurnOutcome.COMMITTED
            and initial_keys == expected["initial_tasks"]
            and len(session.state.graph.edges) == 0
        )
        source = SimulatedFireSource(
            load_latent_incident_fixture(ROOT / annotation.latent_fixture, scene)
        )
        while session.phase in {SessionPhase.PLANNING, SessionPhase.EXECUTION_PAUSED}:
            checkpoint = advance_online_session(session, mode=backend.mode)
            if checkpoint.event_type != "EXECUTION_CHECKPOINT":
                continue
            observation = source.inspect(checkpoint, session.runtime.assignments)
            if observation is not None:
                observation_audit = apply_fire_observation(
                    session, observation, mode=backend.mode
                )
        actual_policy = (
            session.directive.incident_response_up_to.value
            if session.directive.incident_response_up_to is not None
            else None
        )
        incident_id = observation_audit.incident_id if observation_audit else None
        actual = {
            "initial_tasks": initial_keys,
            "initial_edges": 0 if initial_exact else None,
            "policy": actual_policy,
            "response_tasks": _response_steps(session, incident_id),
            "observation_source": observation_audit.source if observation_audit else None,
            "incident_id": incident_id,
        }
        execution_clean = bool(
            session.execution
            and session.execution.termination.value == "COMPLETED"
            and not session.execution.capability_violations
            and not session.execution.precedence_violations
        )
        exact = (
            initial_exact
            and actual_policy == case.expected_policy
            and actual["response_tasks"] == expected["response_tasks"]
            and actual["observation_source"] == "SENSOR_SIMULATED"
            and observation_audit is not None
            and observation_audit.outcome == "COMMITTED"
            and execution_clean
        )
    except Exception as exc:  # noqa: BLE001 - retain every failed live case
        error = f"{type(exc).__name__}: {exc}"
        actual = {"policy": None, "response_tasks": []}
        exact = False
    released = (
        tuple(observation_audit.online_reallocation.selectively_released_tasks)
        if observation_audit and observation_audit.online_reallocation
        else ()
    )
    return _result_common(
        case.id,
        "policy",
        (case.command,),
        expected,
        actual,
        exact,
        session,
        backend,
        released,
        error,
    )


def _run_report_case(
    annotation: CounterfactualAnnotation,
    case: ReportCase,
    backend: object,
) -> CounterfactualCaseResult:
    scene = load_scene(ROOT / annotation.scene)
    session = MissionSession(f"p12-{case.id.lower().replace('_', '-')}", scene)
    expected_steps = [step.value for step in chain_prefix(case.expected_response_up_to)]
    expected = {
        "initial_tasks": sorted(annotation.expected_initial_tasks),
        "zone": case.expected_zone,
        "response_up_to": case.expected_response_up_to,
        "response_tasks": sorted(expected_steps),
        "source": "OPERATOR",
    }
    error = None
    report = None
    try:
        initial = handle_turn(session, case.initial_command, backend)
        initial_keys = _task_keys(session)
        initial_exact = (
            initial.outcome is TurnOutcome.COMMITTED
            and initial_keys == expected["initial_tasks"]
            and len(session.state.graph.edges) == 0
        )
        advance_online_session(session, mode=backend.mode)
        report = handle_turn(session, case.report_command, backend)
        action = report.audit.incident_action
        actual = {
            "initial_tasks": initial_keys,
            "zone": action.zone_id if action else None,
            "response_up_to": action.response_up_to if action else None,
            "response_tasks": _response_steps(
                session, action.incident_id if action else None
            ),
            "source": action.source if action else None,
            "incident_id": action.incident_id if action else None,
        }
        _finish_execution(session, backend.mode)
        execution_clean = bool(
            session.execution
            and session.execution.termination.value == "COMPLETED"
            and not session.execution.capability_violations
            and not session.execution.precedence_violations
        )
        exact = (
            initial_exact
            and report.outcome is TurnOutcome.COMMITTED
            and actual["zone"] == case.expected_zone
            and actual["response_up_to"] == case.expected_response_up_to
            and actual["response_tasks"] == expected["response_tasks"]
            and actual["source"] == "OPERATOR"
            and execution_clean
        )
    except Exception as exc:  # noqa: BLE001 - retain every failed live case
        error = f"{type(exc).__name__}: {exc}"
        actual = {"zone": None, "response_tasks": []}
        exact = False
    online = report.audit.online_reallocation if report is not None else None
    released = tuple(online.selectively_released_tasks) if online is not None else ()
    return _result_common(
        case.id,
        "operator-report",
        (case.initial_command, case.report_command),
        expected,
        actual,
        exact,
        session,
        backend,
        released,
        error,
    )


def _run_unsupported_case(
    annotation: CounterfactualAnnotation,
    case: UnsupportedCase,
    backend: object,
) -> CounterfactualCaseResult:
    scene = load_scene(ROOT / annotation.scene)
    session = MissionSession(f"p12-{case.id.lower().replace('_', '-')}", scene)
    result = handle_turn(session, case.command, backend)
    actual = {"outcome": result.outcome.value, "state_created": session.state is not None}
    expected = {"outcome": case.expected_outcome, "state_created": False}
    return _result_common(
        case.id,
        "unsupported",
        (case.command,),
        expected,
        actual,
        actual == expected,
        session,
        backend,
    )


def run_counterfactual(
    annotation: CounterfactualAnnotation,
    backend_factory: BackendFactory,
    *,
    requested_model: str | None,
) -> CounterfactualRun:
    started = _utc_now()
    results = []
    modes = set()
    for family, cases, runner in (
        ("policy", annotation.policy_cases, _run_policy_case),
        ("operator-report", annotation.report_cases, _run_report_case),
        ("unsupported", annotation.unsupported_cases, _run_unsupported_case),
    ):
        del family
        for case in cases:
            backend = backend_factory(case.id, case)
            modes.add(getattr(backend, "mode", "unknown"))
            results.append(runner(annotation, case, backend))
    if len(modes) != 1:
        raise ValueError(f"one run cannot mix backend modes: {sorted(modes)}")
    scene = load_scene(ROOT / annotation.scene)
    return CounterfactualRun(
        annotation_version=annotation.annotation_version,
        backend_mode=modes.pop(),
        requested_model=requested_model,
        scene_hash=scene_hash(scene),
        validator_version=VALIDATOR_VERSION,
        started_at=started,
        finished_at=_utc_now(),
        cases=tuple(results),
    )


def text_report(run: CounterfactualRun) -> str:
    lines = [
        "P12 incident contingency counterfactual",
        f"backend={run.backend_mode} model={run.requested_model or 'n/a'}",
        f"exact={run.exact_count}/{len(run.cases)}",
    ]
    for case in run.cases:
        lines.append(
            f"{case.id:24s} exact={str(case.exact):5s} "
            f"termination={case.termination or 'n/a':9s} "
            f"release={len(case.released_tasks)} error={case.harness_error or '-'}"
        )
    return "\n".join(lines)


def to_json(run: CounterfactualRun) -> str:
    return json.dumps(asdict(run), ensure_ascii=False, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluation.incident_contingency")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true")
    mode.add_argument("--cached", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cache-dir", default=str(ROOT / "data" / "llm_cache"))
    parser.add_argument("--annotation", default=str(DEFAULT_ANNOTATION))
    parser.add_argument("--out", help="path prefix for .json and .txt")
    args = parser.parse_args(argv)
    annotation = load_annotation(args.annotation)

    if args.mock:
        factory = mock_backend_factory(annotation)
        requested_model = None
    elif args.cached:
        from llm.cache import CachedBackend

        def factory(_id, _case):
            return CachedBackend(args.model, args.cache_dir)

        requested_model = args.model
    else:
        from llm.backend import OpenAIBackend
        from llm.cache import RecordingBackend

        def factory(_id, _case):
            return RecordingBackend(OpenAIBackend(args.model), args.cache_dir)

        requested_model = args.model

    run = run_counterfactual(annotation, factory, requested_model=requested_model)
    report = text_report(run)
    print(report)
    if args.out:
        prefix = Path(args.out)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        prefix.with_suffix(".json").write_text(to_json(run) + "\n", encoding="utf-8")
        prefix.with_suffix(".txt").write_text(report + "\n", encoding="utf-8")
        print(f"wrote {prefix.with_suffix('.json')}, {prefix.with_suffix('.txt')}")
    return 0 if run.exact_count == len(run.cases) else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "CounterfactualAnnotation",
    "CounterfactualCaseResult",
    "CounterfactualRun",
    "load_annotation",
    "mock_backend_factory",
    "run_counterfactual",
    "text_report",
    "to_json",
]
