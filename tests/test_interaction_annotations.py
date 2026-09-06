from pathlib import Path

import pytest
import yaml

from evaluation.interaction_annotations import CASE_IDS, load_all_dialogues, load_dialogue
from scenarios.scene import load_scene

ROOT = Path(__file__).parents[1]
SCENE = ROOT / "scenarios" / "industrial_park.yaml"


@pytest.fixture
def scene():
    return load_scene(SCENE)


def test_all_twelve_gold_dialogues_are_strict_and_self_consistent(scene):
    dialogues = load_all_dialogues(scene)

    assert tuple(dialogue.id for dialogue in dialogues) == CASE_IDS
    assert len(dialogues) == 12
    assert {dialogue.family for dialogue in dialogues} == {"A", "B", "C"}
    assert all(2 <= len(dialogue.turns) <= 5 for dialogue in dialogues)
    assert sum(len(dialogue.turns) for dialogue in dialogues) == 36
    assert sum(
        turn.input_kind == "NATURAL_LANGUAGE"
        for dialogue in dialogues
        for turn in dialogue.turns
    ) == 33
    assert sum(
        turn.input_kind == "CANDIDATE_SELECTION"
        for dialogue in dialogues
        for turn in dialogue.turns
    ) == 3


def test_each_family_has_exactly_the_four_contract_shapes(scene):
    dialogues = load_all_dialogues(scene)
    expected = {"NEW_ONLY", "REPORT_UPDATE", "QUERY", "AMBIGUOUS_SELECTION"}
    for family in "ABC":
        assert {d.shape for d in dialogues if d.family == family} == expected


def test_loader_rejects_unknown_top_level_key(scene, tmp_path):
    raw = yaml.safe_load((ROOT / "data/interaction_dialogues/A1.yaml").read_text())
    raw["notes"] = "not allowed"
    path = tmp_path / "A1.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True))

    with pytest.raises(ValueError, match="keys"):
        load_dialogue(path, scene)


def test_loader_rejects_patch_gold_that_disagrees_with_graph_diff(scene, tmp_path):
    raw = yaml.safe_load((ROOT / "data/interaction_dialogues/B4.yaml").read_text())
    raw["turns"][-1]["patch"]["added_tasks"].pop()
    path = tmp_path / "B4.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))

    with pytest.raises(ValueError, match="patch task gold"):
        load_dialogue(path, scene)


def test_loader_rejects_candidate_selection_with_an_intent(scene, tmp_path):
    raw = yaml.safe_load((ROOT / "data/interaction_dialogues/C4.yaml").read_text())
    raw["turns"][-1]["intent"] = {"kind": "UPDATE_MISSION"}
    path = tmp_path / "C4.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))

    with pytest.raises(ValueError, match="invalid keys"):
        load_dialogue(path, scene)
