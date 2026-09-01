"""Whole-graph validation entry point for the LLM pipeline (RESEARCH_CONTRACT.md §9, §12).

``validate_candidate`` runs the raw-list checks (validator/candidate.py) and the
whole-graph invariants (validator/whole_graph.py) on a MissionCandidate and
returns a ValidationResult with the §14 reproducibility fields.

The MissionPatch path (validator/patch.py) reuses ``validate_structure`` on the
post-patch graph; it does not go through this function.
"""

from scenarios.scene import Scene
from validator.candidate import MissionCandidate
from validator.hashing import graph_hash, scene_hash
from validator.result import ValidationResult
from validator.whole_graph import validate_structure


def validate_candidate(candidate: MissionCandidate, scene: Scene) -> ValidationResult:
    nodes = [t.key for t in candidate.tasks]
    edges = [(e.predecessor, e.successor) for e in candidate.edges]

    errors = list(candidate.consistency_errors())
    errors += validate_structure(nodes, edges, scene)

    hash_nodes = list(
        dict.fromkeys((t.task_type, t.target, t.priority) for t in candidate.tasks)
    )
    return ValidationResult(
        accepted=not errors,
        errors=tuple(errors),
        graph_hash=graph_hash(hash_nodes, edges),
        scene_hash=scene_hash(scene),
    )
