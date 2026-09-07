"""Exact, labelled fallback scripts for UI wiring checks (§22.4).

Mock mode is not a substitute LLM. Each response is bound to one published
utterance and schema call; arbitrary text is rejected *before* the cursor is
advanced. Live counterfactual behaviour is measured through OpenAIBackend (or
an exact cache of those calls), never inferred from this script.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from core.enums import TaskType
from interaction.schemas import IntentWireEnvelope, wire_intent
from llm.schemas import LLMEdge, LLMTask, Step1Output, Step2Output
from scenarios.fixture import load_reference_fixture

REFERENCE_SCRIPT = "reference"
SENSOR_SCRIPT = "sensor-detection"
OPERATOR_SCRIPT = "operator-report"

MOCK_COMMANDS = (
    "전체 구역을 항공 정찰하고 알려진 두 화재를 지상 진압까지 대응해줘",
    "그 화재의 상태를 알려줘",
    "A 구역에 새 화재가 발생했어",
    "거기 지상 진압까지 계획에 추가해줘",
    "거기 대응 상태를 알려줘",
    "FIRE_SITE_3의 우선순위를 올려줘",
)

SENSOR_MOCK_COMMANDS = (
    "전체 구역을 순찰하고 화재를 발견하면 지상 진압까지 대응해줘",
    "그 화재의 상태를 알려줘",
)

OPERATOR_MOCK_COMMANDS = (
    "전체 구역을 순찰해줘",
    "Warehouse에서 불이 났어. 지상 진압까지 대응해줘",
    "그 화재의 상태를 알려줘",
)


class UnsupportedMockCommand(ValueError):
    """The current script does not own the submitted utterance."""


@dataclass(frozen=True, slots=True)
class _ScriptItem:
    command: str
    schema_name: str
    response: BaseModel | dict


class ExactScriptBackend:
    mode = "mock"

    def __init__(self, items: list[_ScriptItem]) -> None:
        self._items = tuple(items)
        self._cursor = 0
        self.calls: list[tuple[str, str, str]] = []
        self.rejected_calls: list[tuple[str, str]] = []

    @property
    def remaining(self) -> int:
        return len(self._items) - self._cursor

    @staticmethod
    def _command(schema_name: str, user: str) -> str | None:
        prefix = "Operator: " if schema_name == "IntentWireEnvelope" else "Command: "
        first_line = user.splitlines()[0] if user else ""
        return first_line.removeprefix(prefix) if first_line.startswith(prefix) else None

    def complete(self, system: str, user: str, schema):
        if self._cursor >= len(self._items):
            self.rejected_calls.append((user, schema.__name__))
            raise UnsupportedMockCommand("MOCK script has no remaining published command")
        expected = self._items[self._cursor]
        command = self._command(schema.__name__, user)
        if schema.__name__ != expected.schema_name or command != expected.command:
            self.rejected_calls.append((user, schema.__name__))
            raise UnsupportedMockCommand(
                "MOCK은 제시된 명령만 재생합니다. "
                f"다음 명령: {expected.command!r}; 자유 입력은 LIVE를 사용하세요."
            )
        self._cursor += 1
        self.calls.append((system, user, schema.__name__))
        item = expected.response
        return item if isinstance(item, schema) else schema.model_validate(item)


def _intent(kind: str, **slots) -> IntentWireEnvelope:
    return wire_intent(kind, **slots)


def _mission_items(
    command: str,
    intent: IntentWireEnvelope,
    tasks: list[LLMTask],
    edges: list[LLMEdge],
) -> list[_ScriptItem]:
    return [
        _ScriptItem(command, "IntentWireEnvelope", intent),
        _ScriptItem(command, "Step1Output", Step1Output(tasks=tasks)),
        _ScriptItem(command, "Step2Output", Step2Output(edges=edges)),
    ]


def _reference_items() -> list[_ScriptItem]:
    fixture = load_reference_fixture()
    graph = fixture.graph
    tasks = [
        LLMTask(task_type=task.task_type.value, target=task.target)
        for task in graph.tasks
    ]
    edges = [
        LLMEdge(
            predecessor=f"{graph[pred].task_type.value}:{graph[pred].target}",
            successor=f"{graph[succ].task_type.value}:{graph[succ].target}",
        )
        for pred, succ in sorted(graph.edges)
    ]
    first, query, report, update, status, unsupported = MOCK_COMMANDS
    return [
        *_mission_items(first, _intent("NEW_MISSION"), tasks, edges),
        _ScriptItem(
            query,
            "IntentWireEnvelope",
            _intent("QUERY_STATUS", about="mission", target_phrase="그 화재"),
        ),
        _ScriptItem(
            report,
            "IntentWireEnvelope",
            _intent("REPORT_INCIDENT", zone_ref="A 구역"),
        ),
        _ScriptItem(
            update,
            "IntentWireEnvelope",
            _intent(
                "UPDATE_MISSION",
                target_phrase="거기",
                up_to_step="GROUND_SUPPRESSION",
            ),
        ),
        _ScriptItem(
            status,
            "IntentWireEnvelope",
            _intent("QUERY_STATUS", about="mission", target_phrase="거기"),
        ),
        _ScriptItem(
            unsupported,
            "IntentWireEnvelope",
            _intent("UNSUPPORTED", note="priority change is outside the contract"),
        ),
    ]


def _patrol_tasks() -> list[LLMTask]:
    return [
        LLMTask(task_type=TaskType.AREA_RECON.value, target=f"ZONE_{suffix}")
        for suffix in "ABCD"
    ]


def _sensor_items() -> list[_ScriptItem]:
    initial, query = SENSOR_MOCK_COMMANDS
    return [
        *_mission_items(
            initial,
            _intent(
                "NEW_MISSION",
                incident_response_up_to="GROUND_SUPPRESSION",
            ),
            _patrol_tasks(),
            [],
        ),
        _ScriptItem(
            query,
            "IntentWireEnvelope",
            _intent("QUERY_STATUS", about="mission", target_phrase="그 화재"),
        ),
    ]


def _operator_items() -> list[_ScriptItem]:
    initial, report, query = OPERATOR_MOCK_COMMANDS
    return [
        *_mission_items(initial, _intent("NEW_MISSION"), _patrol_tasks(), []),
        _ScriptItem(
            report,
            "IntentWireEnvelope",
            _intent(
                "REPORT_INCIDENT",
                zone_ref="Warehouse",
                response_up_to="GROUND_SUPPRESSION",
            ),
        ),
        _ScriptItem(
            query,
            "IntentWireEnvelope",
            _intent("QUERY_STATUS", about="mission", target_phrase="그 화재"),
        ),
    ]


def make_mock_backend(script_id: str = REFERENCE_SCRIPT) -> ExactScriptBackend:
    factories = {
        REFERENCE_SCRIPT: _reference_items,
        SENSOR_SCRIPT: _sensor_items,
        OPERATOR_SCRIPT: _operator_items,
    }
    try:
        items = factories[script_id]()
    except KeyError as exc:
        raise ValueError(f"unknown mock script: {script_id!r}") from exc
    return ExactScriptBackend(items)


def commands_for_script(script_id: str) -> tuple[str, ...]:
    try:
        return {
            REFERENCE_SCRIPT: MOCK_COMMANDS,
            SENSOR_SCRIPT: SENSOR_MOCK_COMMANDS,
            OPERATOR_SCRIPT: OPERATOR_MOCK_COMMANDS,
        }[script_id]
    except KeyError as exc:
        raise ValueError(f"unknown mock script: {script_id!r}") from exc


__all__ = [
    "ExactScriptBackend",
    "MOCK_COMMANDS",
    "OPERATOR_MOCK_COMMANDS",
    "OPERATOR_SCRIPT",
    "REFERENCE_SCRIPT",
    "SENSOR_MOCK_COMMANDS",
    "SENSOR_SCRIPT",
    "UnsupportedMockCommand",
    "commands_for_script",
    "make_mock_backend",
]
