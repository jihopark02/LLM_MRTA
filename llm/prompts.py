"""Prompt builders for the LLM pipeline (RESEARCH_CONTRACT.md §12).

The scene vocabulary (zones, incidents, task types, workflow rule) is injected so
the model works from the same ground truth the deterministic Validator uses. The
model emits only task_type / target / priority and edges — never coordinates,
capabilities, durations, or task_ids (§7).
"""

from core.enums import TaskType
from scenarios.compiler import TASK_TABLE
from scenarios.scene import Scene

_TASK_TYPES = ", ".join(t.value for t in TaskType)
_WORKFLOW = "THERMAL_RECON -> SUPPRESSANT_DROP -> GROUND_INSPECTION -> GROUND_SUPPRESSION"


def _scene_facts(scene: Scene) -> str:
    zones = ", ".join(sorted(scene.zones))
    incidents = ", ".join(
        f"{iid} (zone {inc.zone}, priority {inc.priority})"
        for iid, inc in sorted(scene.incidents.items())
    )
    kinds = "; ".join(
        f"{tt.value}: target is a {TASK_TABLE[tt].target_kind}" for tt in TaskType
    )
    return (
        f"Zones: {zones}\n"
        f"Incidents (already RESPONSE_REQUIRED): {incidents}\n"
        f"Task types: {_TASK_TYPES}\n"
        f"Target kind per task type: {kinds}\n"
        f"Incident workflow (conditional — a downstream task requires exactly its "
        f"predecessor for the SAME incident): {_WORKFLOW}\n"
        f"AREA_RECON targets a zone and is independent of the incident workflow."
    )


_STEP1_SYSTEM = """You decompose a disaster-response command into a task list.
Output ONLY a JSON object {"tasks": [{"task_type", "target", "priority"}, ...]}.
- task_type is one of the listed types.
- target is a zone id (for AREA_RECON) or an incident id (for the others).
- priority is an integer 1..10; use the incident's priority for incident tasks.
Do not invent coordinates, capabilities, durations, or ids. Do not add edges here.
{facts}"""

_STEP2_SYSTEM = """You add dependency edges to an existing task list.
Output ONLY {"edges": [{"predecessor": "TYPE:target", "successor": "TYPE:target"}, ...]}.
Endpoints must be tasks that appear in the given list. Only add an edge when the
successor genuinely depends on the predecessor completing. Follow the incident
workflow chain; never connect tasks of different incidents.
{facts}"""

_REPAIR_SYSTEM = """A previous task graph failed deterministic validation.
Given the command, the graph, and the structured error codes, output a corrected
FULL graph: {"tasks": [...], "edges": [...]} in the same shapes as before.
Fix only what the errors point to; keep everything else. Do not invent coordinates,
capabilities, durations, or ids.
{facts}"""


def step1_system(scene: Scene) -> str:
    return _STEP1_SYSTEM.replace("{facts}", _scene_facts(scene))


def step1_user(command: str) -> str:
    return f"Command: {command}"


def step2_system(scene: Scene) -> str:
    return _STEP2_SYSTEM.replace("{facts}", _scene_facts(scene))


def step2_user(command: str, tasks_json: str) -> str:
    return f"Command: {command}\nTask list:\n{tasks_json}"


def repair_system(scene: Scene) -> str:
    return _REPAIR_SYSTEM.replace("{facts}", _scene_facts(scene))


def repair_user(command: str, graph_json: str, error_lines: list[str]) -> str:
    errors = "\n".join(f"- {line}" for line in error_lines)
    return f"Command: {command}\nGraph:\n{graph_json}\nValidation errors:\n{errors}"
