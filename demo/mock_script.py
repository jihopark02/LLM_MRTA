"""A labelled, finite fallback script for the Streamlit UI.

This is not a substitute model and is never used for research measurements.
It only lets a presenter exercise the already-tested interaction path without
network access. The UI exposes the exact supported utterance order.
"""

from interaction.schemas import IntentEnvelope
from llm.backend import MockBackend
from llm.schemas import LLMEdge, LLMTask, Step1Output, Step2Output
from scenarios.fixture import load_reference_fixture

MOCK_COMMANDS = (
    "전체 구역을 항공 정찰하고 알려진 두 화재를 지상 진압까지 대응해줘",
    "그 화재의 상태를 알려줘",
    "A 구역에 새 화재가 발생했어",
    "거기 지상 진압까지 계획에 추가해줘",
    "거기 대응 상태를 알려줘",
    "FIRE_SITE_3의 우선순위를 올려줘",
)


def _intent(kind: str, **slots) -> IntentEnvelope:
    return IntentEnvelope.model_validate({"intent": {"kind": kind, **slots}})


def make_mock_backend() -> MockBackend:
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
    return MockBackend(
        [
            _intent("NEW_MISSION"),
            Step1Output(tasks=tasks),
            Step2Output(edges=edges),
            _intent("QUERY_STATUS", about="mission", target_phrase="그 화재"),
            _intent("REPORT_INCIDENT", zone_ref="A 구역"),
            _intent(
                "UPDATE_MISSION",
                target_phrase="거기",
                up_to_step="GROUND_SUPPRESSION",
            ),
            _intent("QUERY_STATUS", about="mission", target_phrase="거기"),
            _intent("UNSUPPORTED", note="priority change is outside the contract"),
        ]
    )


__all__ = ["MOCK_COMMANDS", "make_mock_backend"]
