"""Prompt content (RESEARCH_CONTRACT.md §12, Codex P5 recommendation).

Without a meaning + platform glossary, P6 would measure the model's ability to
guess English task names rather than its ability to decompose a mission — so
every task type's glossary line must actually be present in what gets sent.
"""

from pathlib import Path

from core.enums import TaskType
from llm.prompts import repair_system, step1_system, step1_user, step2_system
from scenarios.scene import load_scene

SCENE = Path(__file__).parents[1] / "scenarios" / "industrial_park.yaml"


def test_every_task_type_glossary_entry_is_in_the_prompts():
    scene = load_scene(SCENE)
    for builder in (step1_system, step2_system, repair_system):
        prompt = builder(scene)
        for tt in TaskType:
            assert tt.value in prompt, f"{tt.value} missing from {builder.__name__}"

    # the two easily-confused ground steps must be distinguishable, not just present
    s1 = step1_system(scene)
    assert "inspect ground conditions" in s1
    assert "suppression" in s1.split("GROUND_SUPPRESSION:")[1].split("\n")[0].lower()


def test_step1_user_carries_the_command_verbatim():
    assert "Evacuate ZONE_A now" in step1_user("Evacuate ZONE_A now")
