"""LLM task-graph generation pipeline (RESEARCH_CONTRACT.md §12).

  command -> Step 1 (task list) -> schema validation
          -> Step 2 (edges) -> whole-graph Validator
          -> structured-error repair (at most once) -> re-validate
          -> APPROVED or explicit REJECTED (never a silent fallback to reference)

Step 2 is never called until Step 1's own output has passed schema validation
(contract order). A ``pydantic.ValidationError`` raised by a backend call — the
model returned an extra field or a wrong-typed value the schema forbids — is
itself a schema failure, not an exception that aborts the run. The raw
(pre-repair) candidate and its validation result are always preserved
alongside the final one, so raw output and validated/repaired output can be
compared (§16).
"""

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

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
from validator.errors import ErrorCode
from validator.errors import ValidationError as SchemaError
from validator.result import ValidationResult
from validator.validate import validate_candidate


@dataclass
class GenerationResult:
    command: str
    approved: bool
    attempts: int                            # LLM generation attempts (1, or 2 with repair)
    repaired: bool
    raw_schema_valid: bool                   # Step 1+2 output parsed into a clean candidate
    raw_whole_graph_valid: bool              # raw candidate passed whole-graph validation
    repaired_schema_valid: bool | None = None       # None if repair was never attempted
    repaired_whole_graph_valid: bool | None = None  # None if repair was never attempted
    failure_category: str | None = None      # None if approved
    errors: tuple[SchemaError, ...] = ()
    raw_candidate: MissionCandidate | None = None
    raw_validation: ValidationResult | None = None
    candidate: MissionCandidate | None = None       # final: repaired if repaired else raw
    validation: ValidationResult | None = None      # final
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
    task_specs = [(t.task_type, t.target) for t in candidate.tasks]
    edges = [(e.predecessor, e.successor) for e in candidate.edges]
    return compile_reference_graph(scene, task_specs, edges)


def _call(backend: LLMBackend, system: str, user: str, schema: type[BaseModel]):
    """Run one backend call. A pydantic ValidationError (the model's structured
    output itself violates the schema — extra field, wrong type) is a schema
    failure, not an exception that should abort the pipeline; anything else
    (network, auth, a backend running out of mock script) propagates."""
    try:
        return backend.complete(system, user, schema), None
    except ValidationError as e:
        return None, str(e)


def _schema_error(detail: str) -> SchemaError:
    return SchemaError(ErrorCode.E_SCHEMA, "backend", detail)


def generate_mission(
    command: str, scene: Scene, backend: LLMBackend
) -> GenerationResult:
    # -- Step 1 --------------------------------------------------------
    step1, err = _call(backend, step1_system(scene), step1_user(command), Step1Output)
    if err is not None:
        return GenerationResult(
            command, approved=False, attempts=1, repaired=False,
            raw_schema_valid=False, raw_whole_graph_valid=False,
            failure_category="SCHEMA", errors=(_schema_error(err),),
        )

    # Contract order: schema-validate Step 1's own output BEFORE calling Step 2.
    tasks_only, step1_errors = MissionCandidate.from_raw(to_candidate_dict(step1.tasks, []))
    if tasks_only is not None:
        step1_errors = step1_errors + tasks_only.consistency_errors()
    if tasks_only is None or step1_errors:
        return GenerationResult(
            command, approved=False, attempts=1, repaired=False,
            raw_schema_valid=False, raw_whole_graph_valid=False,
            failure_category="SCHEMA", errors=tuple(step1_errors),
        )

    # -- Step 2 (only reached once Step 1 is schema-clean) --------------
    step2, err = _call(
        backend, step2_system(scene), step2_user(command, step1.model_dump_json()), Step2Output
    )
    if err is not None:
        return GenerationResult(
            command, approved=False, attempts=1, repaired=False,
            raw_schema_valid=False, raw_whole_graph_valid=False,
            failure_category="SCHEMA", errors=(_schema_error(err),),
        )

    raw = to_candidate_dict(step1.tasks, step2.edges)
    candidate, schema_errors = MissionCandidate.from_raw(raw)
    if candidate is None or schema_errors:
        return GenerationResult(
            command, approved=False, attempts=1, repaired=False,
            raw_schema_valid=False, raw_whole_graph_valid=False,
            failure_category="SCHEMA", errors=tuple(schema_errors),
        )

    result = validate_candidate(candidate, scene)
    if result.accepted:
        return GenerationResult(
            command, approved=True, attempts=1, repaired=False,
            raw_schema_valid=True, raw_whole_graph_valid=True, failure_category=None,
            raw_candidate=candidate, raw_validation=result,
            candidate=candidate, validation=result, graph=_compile(candidate, scene),
        )

    # -- one repair pass, driven by the structured errors --------------
    repair, err = _call(
        backend,
        repair_system(scene),
        repair_user(command, json.dumps(raw), [str(e) for e in result.errors]),
        RepairOutput,
    )
    if err is not None:
        return GenerationResult(
            command, approved=False, attempts=2, repaired=True,
            raw_schema_valid=True, raw_whole_graph_valid=False,
            repaired_schema_valid=False, repaired_whole_graph_valid=False,
            failure_category="SCHEMA", errors=(_schema_error(err),),
            raw_candidate=candidate, raw_validation=result,
        )

    raw2 = to_candidate_dict(repair.tasks, repair.edges)
    candidate2, schema_errors2 = MissionCandidate.from_raw(raw2)
    if candidate2 is None or schema_errors2:
        return GenerationResult(
            command, approved=False, attempts=2, repaired=True,
            raw_schema_valid=True, raw_whole_graph_valid=False,
            repaired_schema_valid=False, repaired_whole_graph_valid=False,
            failure_category="SCHEMA", errors=tuple(schema_errors2),
            raw_candidate=candidate, raw_validation=result,
        )

    result2 = validate_candidate(candidate2, scene)
    if result2.accepted:
        return GenerationResult(
            command, approved=True, attempts=2, repaired=True,
            raw_schema_valid=True, raw_whole_graph_valid=False,
            repaired_schema_valid=True, repaired_whole_graph_valid=True,
            failure_category=None,
            raw_candidate=candidate, raw_validation=result,
            candidate=candidate2, validation=result2, graph=_compile(candidate2, scene),
        )

    return GenerationResult(
        command, approved=False, attempts=2, repaired=True,
        raw_schema_valid=True, raw_whole_graph_valid=False,
        repaired_schema_valid=True, repaired_whole_graph_valid=False,
        failure_category=_category(result2.errors), errors=result2.errors,
        raw_candidate=candidate, raw_validation=result,
        candidate=candidate2, validation=result2,
    )
