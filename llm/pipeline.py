"""LLM task-graph generation pipeline (RESEARCH_CONTRACT.md §12).

  command -> Step 1 (task list) -> schema validation
          -> Step 2 (edges) -> whole-graph Validator
          -> structured-error repair (at most once) -> re-validate
          -> APPROVED or explicit REJECTED (never a silent fallback to reference)

An APPROVED result carries the compiled executable TaskGraph — the candidate has
passed the Validator, so the trusted compiler path is valid (D-003).
"""

import json
from dataclasses import dataclass, field

from core.task_graph import TaskGraph
from llm.backend import LLMBackend
from llm.prompts import (
    repair_system,
    repair_user,
    step1_system,
    step1_user,
    step2_system,
    step2_user,
)
from llm.schemas import RepairOutput, Step1Output, Step2Output, to_candidate_dict
from scenarios.compiler import compile_reference_graph
from scenarios.scene import Scene
from validator.candidate import MissionCandidate
from validator.errors import ErrorCode, ValidationError
from validator.result import ValidationResult
from validator.validate import validate_candidate


@dataclass
class GenerationResult:
    command: str
    approved: bool
    attempts: int                       # LLM generation attempts (1, or 2 with repair)
    repaired: bool
    schema_valid: bool                  # Step 1/2 parsed + MissionCandidate.from_raw clean
    raw_whole_graph_valid: bool         # first whole-graph validation passed
    repaired_whole_graph_valid: bool    # second validation passed (False if no repair ran)
    failure_category: str | None        # None if approved
    errors: tuple[ValidationError, ...] = ()
    candidate: MissionCandidate | None = None
    validation: ValidationResult | None = None
    graph: TaskGraph | None = field(default=None, repr=False)


def _category(errors) -> str:
    codes = {e.code for e in errors}
    if codes & {ErrorCode.E_SCHEMA, ErrorCode.E_TYPE_NOT_ALLOWED}:
        return "SCHEMA"
    if ErrorCode.E_WORKFLOW in codes or ErrorCode.E_CROSS_INCIDENT in codes:
        return "WORKFLOW"
    if codes & {ErrorCode.E_CYCLE, ErrorCode.E_DUPLICATE_EDGE, ErrorCode.E_SELF_LOOP}:
        return "STRUCTURE"
    if codes & {ErrorCode.E_UNKNOWN_REF, ErrorCode.E_DUPLICATE_ID}:
        return "REFERENCE"
    if codes & {ErrorCode.E_INFEASIBLE, ErrorCode.E_UNREACHABLE}:
        return "FEASIBILITY"
    return "OTHER"


def _compile(candidate: MissionCandidate, scene: Scene) -> TaskGraph:
    task_specs = [(t.task_type, t.target, t.priority) for t in candidate.tasks]
    edges = [(e.predecessor, e.successor) for e in candidate.edges]
    return compile_reference_graph(scene, task_specs, edges)


def generate_mission(
    command: str, scene: Scene, backend: LLMBackend
) -> GenerationResult:
    step1: Step1Output = backend.complete(step1_system(scene), step1_user(command), Step1Output)
    step2: Step2Output = backend.complete(
        step2_system(scene),
        step2_user(command, step1.model_dump_json()),
        Step2Output,
    )

    raw = to_candidate_dict(step1.tasks, step2.edges)
    candidate, schema_errors = MissionCandidate.from_raw(raw)
    if candidate is None or schema_errors:
        return GenerationResult(
            command, approved=False, attempts=1, repaired=False,
            schema_valid=False, raw_whole_graph_valid=False,
            repaired_whole_graph_valid=False, failure_category="SCHEMA",
            errors=tuple(schema_errors),
        )

    result = validate_candidate(candidate, scene)
    if result.accepted:
        return GenerationResult(
            command, approved=True, attempts=1, repaired=False,
            schema_valid=True, raw_whole_graph_valid=True,
            repaired_whole_graph_valid=False, failure_category=None,
            candidate=candidate, validation=result, graph=_compile(candidate, scene),
        )

    # -- one repair pass, driven by the structured errors --------------
    repair: RepairOutput = backend.complete(
        repair_system(scene),
        repair_user(command, json.dumps(raw), [str(e) for e in result.errors]),
        RepairOutput,
    )
    raw2 = to_candidate_dict(repair.tasks, repair.edges)
    candidate2, schema_errors2 = MissionCandidate.from_raw(raw2)
    if candidate2 is None or schema_errors2:
        return GenerationResult(
            command, approved=False, attempts=2, repaired=True,
            schema_valid=False, raw_whole_graph_valid=False,
            repaired_whole_graph_valid=False, failure_category="SCHEMA",
            errors=tuple(schema_errors2),
        )

    result2 = validate_candidate(candidate2, scene)
    if result2.accepted:
        return GenerationResult(
            command, approved=True, attempts=2, repaired=True,
            schema_valid=True, raw_whole_graph_valid=False,
            repaired_whole_graph_valid=True, failure_category=None,
            candidate=candidate2, validation=result2, graph=_compile(candidate2, scene),
        )

    return GenerationResult(
        command, approved=False, attempts=2, repaired=True,
        schema_valid=True, raw_whole_graph_valid=False,
        repaired_whole_graph_valid=False, failure_category=_category(result2.errors),
        errors=result2.errors, candidate=candidate2, validation=result2,
    )
