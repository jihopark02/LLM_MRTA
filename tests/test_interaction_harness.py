from pathlib import Path

import pytest

from evaluation.interaction_annotations import load_all_dialogues
from evaluation.interaction_harness import gold_backend, run_interaction_eval
from evaluation.interaction_report import text_report, to_dict, to_json
from scenarios.scene import load_scene

pytestmark = pytest.mark.skip(
    reason="D-076 S11: the P8.4 grounder-only replay drives the pre-D-076 flat-slot "
    "orchestrator (resumable-ambiguous UPDATE_MISSION, removed by S8). The 12 gold "
    "dialogues and their results stay frozen as a historical artifact; D-076's own "
    "evaluation is a separate Explicit/Compositional/Contextual set."
)

ROOT = Path(__file__).parents[1]
SCENE = ROOT / "scenarios" / "industrial_park.yaml"


def test_grounder_only_runs_all_fixed_dialogues_exactly():
    scene = load_scene(SCENE)
    dialogues = load_all_dialogues(scene)

    run = run_interaction_eval(scene, dialogues, track="grounder-only")
    payload = to_dict(run)
    counts = payload["counts"]

    assert counts["dialogues"] == counts["dialogue_exact"] == 12
    assert counts["operator_turns"] == counts["turn_exact"] == 36
    assert counts["natural_language_turns"] == counts["intent_exact"] == 33
    assert counts["natural_language_turns"] == counts["slots_exact"] == 33
    assert counts["candidate_selection_turns"] == 3
    assert counts["candidate_selection_exact"] == 3
    assert counts["clarification_expected"] == 3
    assert counts["clarification_predicted"] == 3
    assert counts["clarification_tp"] == 3
    assert counts["wrong_guesses"] == 0
    assert counts["clarification_without_mutation"] == 3
    assert counts["patch_turns"] == counts["patch_exact"] == 5
    assert counts["harness_errors"] == 0
    assert all(dialogue.final_graph_exact for dialogue in run.dialogues)


def test_each_dialogue_gets_a_fresh_gold_backend():
    scene = load_scene(SCENE)
    dialogues = load_all_dialogues(scene)
    first = gold_backend(dialogues[0])
    second = gold_backend(dialogues[0])

    assert first is not second
    assert first.calls == []
    assert second.calls == []


def test_report_keeps_raw_denominators_and_complete_audit_json():
    scene = load_scene(SCENE)
    run = run_interaction_eval(
        scene,
        load_all_dialogues(scene),
        track="grounder-only",
    )

    report = text_report(run)
    payload = to_dict(run)
    encoded = to_json(run)

    assert "operator/audit turns         36" in report
    assert "natural-language turns       33" in report
    assert payload["metrics"]["clarification_recall"] == {"n": 3, "d": 3}
    assert len(payload["dialogues"]) == 12
    assert all(case["session_audit"]["events"] for case in payload["dialogues"])
    assert "네 구역" in encoded
