"""Deterministic P9 policy comparison at a frozen execution checkpoint (§19.5).

Run from the repository root:

    python3 -m evaluation.online_reallocation \
        --out data/eval_results/p9_online_reallocation
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from allocation.online import (
    ONLINE_POLICY_VERSION,
    OnlinePatchApplication,
    ReleasePolicy,
    apply_online_patch,
)
from core.enums import TaskStatus, TaskType
from core.mission_state import MissionState
from execution.executor import ExecutionResult, SimExecutor, Termination
from interaction.ground import build_chain_patch
from interaction.scene_mut import register_incident
from interaction.workflow import WORKFLOW_CHAIN
from scenarios.compiler import compile_reference_graph
from scenarios.scene import Scene, load_scene
from validator.hashing import VALIDATOR_VERSION, graph_hash, pre_state_hash, scene_hash
from validator.patch import graph_edge_keys, graph_hash_nodes

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_FIXTURE = _ROOT / "data" / "online_reallocation_fixture.yaml"


@dataclass(frozen=True, slots=True)
class OnlineFixture:
    fixture_id: str
    base_scene: str
    initial_report_zones: tuple[str, ...]
    checkpoint_event: int
    expected_time: float
    expected_completed_now: tuple[str, ...]
    online_report_zone: str
    online_update_up_to: str
    expected_new_incident_id: str
    expected_release: dict[ReleasePolicy, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class PolicyRun:
    policy: str
    completed_prefix: tuple[str, ...]
    running_commitments: dict[str, str]
    directly_affected_tasks: tuple[str, ...]
    released_tasks: tuple[str, ...]
    #: §19.5/D-041. released − directly_affected: how many tasks the §19.3
    #: bundle-suffix step released *beyond* the directly affected ones. Defined
    #: only for `selective`; the same subtraction under full-reset just counts
    #: what full-reset drops anyway, so calling that a suffix effect would be
    #: misleading. 0 means the suffix did not fire — reported, never hidden.
    suffix_extra_release_count: int | None
    preserved_assigned_tasks: tuple[str, ...]
    existing_owner_changes: dict[str, tuple[str, str]]
    new_task_assignments: dict[str, str]
    additional_consensus_rounds: tuple[int, ...]
    termination: str
    makespan: float
    uav_flight_distance: float
    ugv_route_distance: float
    capability_violations: tuple[str, ...]
    precedence_violations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OnlineComparison:
    fixture_id: str
    fixture_sha256: str
    scene_hash: str
    graph_hash: str
    checkpoint_state_hash: str
    validator_version: str
    policy_version: str
    checkpoint_event: int
    simulation_time: float
    completed_now: tuple[str, ...]
    completed_prefix: tuple[str, ...]
    running_commitments: dict[str, str]
    assigned_before: dict[str, str]
    new_incident_id: str
    policies: tuple[PolicyRun, ...]


def _strict_keys(raw: dict, expected: set[str], label: str) -> None:
    if set(raw) != expected:
        raise ValueError(
            f"{label} keys must be {sorted(expected)}, got {sorted(raw)}"
        )


# An evaluation fixture is an input to a published result, so it is read with
# the same strictness D-023 imposed on the scene loader: a wrong type is
# refused at load, never laundered through str()/float() into a plausible
# value that only fails a drift guard several steps later (§19.5, D-041).
def _text(raw: dict, key: str, label: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}.{key} must be a non-empty str, got {value!r}")
    return value


def _text_list(raw: dict, key: str, label: str) -> tuple[str, ...]:
    value = raw[key]
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{label}.{key} must be a list of non-empty str, got {value!r}")
    return tuple(value)


def _finite_number(raw: dict, key: str, label: str) -> float:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}.{key} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{label}.{key} must be finite, got {value!r}")
    return float(value)


def load_online_fixture(path: str | Path = _DEFAULT_FIXTURE) -> OnlineFixture:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("online fixture root must be a mapping")
    _strict_keys(
        raw,
        {
            "fixture_id",
            "base_scene",
            "initial_report_zones",
            "initial_graph",
            "checkpoint_event",
            "expected_checkpoint",
            "online_report_zone",
            "online_update_up_to",
            "expected_new_incident_id",
            "expected_release",
        },
        "online fixture",
    )
    if raw["initial_graph"] != {
        "area_recon_all_zones": True,
        "incident_workflow_up_to": "GROUND_SUPPRESSION",
    }:
        raise ValueError("P9 fixture initial_graph must be the frozen full workflow")
    checkpoint = raw["expected_checkpoint"]
    _strict_keys(checkpoint, {"simulation_time", "completed_now"}, "expected_checkpoint")
    expected_release = raw["expected_release"]
    if not isinstance(expected_release, dict):
        raise ValueError("expected_release must be a mapping")
    if set(expected_release) != {policy.value for policy in ReleasePolicy}:
        raise ValueError("expected_release must cover all release policies")
    event = raw["checkpoint_event"]
    if not isinstance(event, int) or isinstance(event, bool) or event <= 0:
        raise ValueError("checkpoint_event must be a positive int")
    up_to = _text(raw, "online_update_up_to", "online fixture")
    if up_to not in {step.value for step in WORKFLOW_CHAIN}:
        raise ValueError(
            f"online_update_up_to must be one of "
            f"{sorted(step.value for step in WORKFLOW_CHAIN)}, got {up_to!r}"
        )
    return OnlineFixture(
        fixture_id=_text(raw, "fixture_id", "online fixture"),
        base_scene=_text(raw, "base_scene", "online fixture"),
        initial_report_zones=_text_list(raw, "initial_report_zones", "online fixture"),
        checkpoint_event=event,
        expected_time=_finite_number(checkpoint, "simulation_time", "expected_checkpoint"),
        expected_completed_now=_text_list(
            checkpoint, "completed_now", "expected_checkpoint"
        ),
        online_report_zone=_text(raw, "online_report_zone", "online fixture"),
        online_update_up_to=up_to,
        expected_new_incident_id=_text(raw, "expected_new_incident_id", "online fixture"),
        expected_release={
            ReleasePolicy(name): _text_list(expected_release, name, "expected_release")
            for name in expected_release
        },
    )


def _build_initial(fixture: OnlineFixture) -> tuple[Scene, SimExecutor]:
    scene_path = _ROOT / fixture.base_scene
    scene = load_scene(scene_path)
    for zone_id in fixture.initial_report_zones:
        scene, _ = register_incident(scene, zone_id)

    specs = [(TaskType.AREA_RECON, zone_id) for zone_id in sorted(scene.zones)]
    edges = []
    for incident_id in sorted(scene.incidents):
        specs.extend((step, incident_id) for step in WORKFLOW_CHAIN)
        edges.extend(
            ((before, incident_id), (after, incident_id))
            for before, after in zip(WORKFLOW_CHAIN, WORKFLOW_CHAIN[1:], strict=False)
        )
    graph = compile_reference_graph(scene, specs, edges)
    state = MissionState(graph, {agent.agent_id: agent for agent in scene.fleet})
    return scene, SimExecutor(state, scene)


def _commitments(executor: SimExecutor, status: TaskStatus) -> dict[str, str]:
    return {
        task.task_id: task.assigned_agent
        for task in sorted(executor.graph.tasks, key=lambda item: item.task_id)
        if task.status is status and task.assigned_agent is not None
    }


def _run_policy(
    application: OnlinePatchApplication,
    *,
    completed_prefix: tuple[str, ...],
    running: dict[str, str],
    assigned_before: dict[str, str],
    new_incident_id: str,
) -> PolicyRun:
    executor = application.executor
    if executor is None:
        raise RuntimeError(f"{application.policy.value}: online patch was rejected")
    if tuple(sorted(executor.graph.ids_with_status(TaskStatus.COMPLETED))) != completed_prefix:
        raise RuntimeError(f"{application.policy.value}: COMPLETED prefix changed")
    if _commitments(executor, TaskStatus.RUNNING) != running:
        raise RuntimeError(f"{application.policy.value}: RUNNING commitments changed")

    released = set(application.released_tasks)
    suffix_extra = (
        len(released - set(application.directly_affected_tasks))
        if application.policy is ReleasePolicy.SELECTIVE
        else None
    )
    preserved_assigned = tuple(sorted(set(assigned_before) - released))
    existing_changes = {
        task_id: (assigned_before[task_id], application.after_assignments[task_id])
        for task_id in sorted(assigned_before.keys() & application.after_assignments.keys())
        if assigned_before[task_id] != application.after_assignments[task_id]
    }
    result: ExecutionResult = executor.run()
    new_assignments = {
        task_id: agent_id
        for task_id, agent_id in sorted(result.assignments.items())
        if executor.graph[task_id].target == new_incident_id
    }
    return PolicyRun(
        policy=application.policy.value,
        completed_prefix=completed_prefix,
        running_commitments=dict(running),
        directly_affected_tasks=application.directly_affected_tasks,
        released_tasks=application.released_tasks,
        suffix_extra_release_count=suffix_extra,
        preserved_assigned_tasks=preserved_assigned,
        existing_owner_changes=existing_changes,
        new_task_assignments=new_assignments,
        additional_consensus_rounds=application.consensus_rounds,
        termination=result.termination.value,
        makespan=result.makespan,
        uav_flight_distance=result.uav_flight_distance,
        ugv_route_distance=result.ugv_route_distance,
        capability_violations=tuple(result.capability_violations),
        precedence_violations=tuple(result.precedence_violations),
    )


def run_comparison(
    fixture_path: str | Path = _DEFAULT_FIXTURE,
) -> OnlineComparison:
    fixture_path = Path(fixture_path)
    fixture = load_online_fixture(fixture_path)
    scene, executor = _build_initial(fixture)
    completed_now: tuple[str, ...] = ()
    for _ in range(fixture.checkpoint_event):
        advance = executor.advance_to_next_completion()
        if advance.execution is not None:
            raise RuntimeError("mission terminated before the frozen checkpoint")
        completed_now = advance.completed_now

    if abs(executor.now - fixture.expected_time) > 1e-9:
        raise RuntimeError(
            f"checkpoint time drift: expected {fixture.expected_time}, got {executor.now}"
        )
    if completed_now != fixture.expected_completed_now:
        raise RuntimeError(
            f"checkpoint completion drift: expected {fixture.expected_completed_now}, "
            f"got {completed_now}"
        )

    completed_prefix = tuple(sorted(executor.graph.ids_with_status(TaskStatus.COMPLETED)))
    running = _commitments(executor, TaskStatus.RUNNING)
    assigned_before = _commitments(executor, TaskStatus.ASSIGNED)
    updated_scene, new_incident_id = register_incident(scene, fixture.online_report_zone)
    if new_incident_id != fixture.expected_new_incident_id:
        raise RuntimeError(
            f"incident id drift: expected {fixture.expected_new_incident_id}, got {new_incident_id}"
        )
    patch_plan = build_chain_patch(
        executor.graph, new_incident_id, fixture.online_update_up_to
    )
    if patch_plan.patch is None:
        raise RuntimeError("frozen online update unexpectedly produced NO_CHANGE")

    runs: list[PolicyRun] = []
    for policy in ReleasePolicy:
        application = apply_online_patch(
            executor,
            patch_plan.patch,
            updated_scene,
            policy=policy,
        )
        expected = fixture.expected_release[policy]
        if application.released_tasks != expected:
            raise RuntimeError(
                f"{policy.value} release drift: expected {expected}, "
                f"got {application.released_tasks}"
            )
        runs.append(
            _run_policy(
                application,
                completed_prefix=completed_prefix,
                running=running,
                assigned_before=assigned_before,
                new_incident_id=new_incident_id,
            )
        )

    if any(
        run.termination != Termination.COMPLETED.value
        or run.capability_violations
        or run.precedence_violations
        for run in runs
    ):
        raise RuntimeError("a policy failed the §19.5 safety gate")
    by_policy = {run.policy: run for run in runs}
    selective = by_policy[ReleasePolicy.SELECTIVE.value]
    full = by_policy[ReleasePolicy.FULL_RESET.value]
    no_reset = by_policy[ReleasePolicy.NO_RESET.value]
    if len(selective.preserved_assigned_tasks) <= len(full.preserved_assigned_tasks):
        raise RuntimeError("fixture no longer distinguishes selective from full reset")
    if not selective.released_tasks or no_reset.released_tasks:
        raise RuntimeError("fixture no longer distinguishes selective from no reset")

    graph = executor.graph
    fixture_sha = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    return OnlineComparison(
        fixture_id=fixture.fixture_id,
        fixture_sha256=fixture_sha,
        scene_hash=scene_hash(scene),
        graph_hash=graph_hash(graph_hash_nodes(graph), sorted(graph_edge_keys(graph))),
        checkpoint_state_hash=pre_state_hash(executor.work),
        validator_version=VALIDATOR_VERSION,
        policy_version=ONLINE_POLICY_VERSION,
        checkpoint_event=fixture.checkpoint_event,
        simulation_time=executor.now,
        completed_now=completed_now,
        completed_prefix=completed_prefix,
        running_commitments=running,
        assigned_before=assigned_before,
        new_incident_id=new_incident_id,
        policies=tuple(runs),
    )


def to_dict(run: OnlineComparison) -> dict:
    return asdict(run)


def to_json(run: OnlineComparison) -> str:
    return json.dumps(to_dict(run), indent=2, sort_keys=True)


def text_report(run: OnlineComparison) -> str:
    lines = [
        "P9 online selective reallocation comparison",
        "=" * 50,
        f"fixture: {run.fixture_id}",
        f"checkpoint: event {run.checkpoint_event}, t={run.simulation_time:.3f}s",
        f"completed prefix: {len(run.completed_prefix)}, running: {len(run.running_commitments)}",
        f"assigned before: {', '.join(run.assigned_before) or 'none'}",
        "",
    ]
    for policy in run.policies:
        lines.append(
            f"{policy.policy:<10} release={len(policy.released_tasks)} "
            f"preserved_assigned={len(policy.preserved_assigned_tasks)} "
            f"rounds={list(policy.additional_consensus_rounds)} "
            f"makespan={policy.makespan:.3f} termination={policy.termination}"
        )
        lines.append(f"  released: {', '.join(policy.released_tasks) or 'none'}")
        extra = policy.suffix_extra_release_count
        lines.append(
            f"  directly affected: "
            f"{', '.join(policy.directly_affected_tasks) or 'none'}"
            f" | suffix_extra_release_count={'n/a' if extra is None else extra}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluation.online_reallocation")
    parser.add_argument("--fixture", default=str(_DEFAULT_FIXTURE))
    parser.add_argument("--out", help="path prefix for .json and .txt")
    args = parser.parse_args(argv)
    run = run_comparison(args.fixture)
    report = text_report(run)
    print(report)
    if args.out:
        prefix = Path(args.out)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        prefix.with_suffix(".json").write_text(to_json(run) + "\n", encoding="utf-8")
        prefix.with_suffix(".txt").write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

