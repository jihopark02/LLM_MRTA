"""Raw-count report and audit JSON for the P8.4 interaction evaluation."""

from __future__ import annotations

import json
from dataclasses import asdict

from evaluation.interaction_harness import InteractionRun, TurnScore


def _ratio(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "N/A (0)"
    return f"{numerator}/{denominator} ({numerator / denominator:.3f})"


def _counts(run: InteractionRun) -> dict[str, int]:
    turns = [turn for dialogue in run.dialogues for turn in dialogue.turns]
    natural = [turn for turn in turns if turn.input_kind == "NATURAL_LANGUAGE"]
    selections = [turn for turn in turns if turn.input_kind == "CANDIDATE_SELECTION"]
    referents = [turn for turn in turns if turn.referent_exact is not None]
    patches = [turn for turn in turns if turn.expected_patch is not None]
    expected_clarifications = [turn for turn in turns if turn.expected_outcome == "CLARIFICATION"]
    predicted_clarifications = [turn for turn in turns if turn.actual_outcome == "CLARIFICATION"]
    clarification_tp = sum(
        turn.expected_outcome == "CLARIFICATION"
        for turn in predicted_clarifications
    )
    wrong_guesses = sum(
        turn.expected_outcome == "CLARIFICATION"
        and turn.actual_grounding is not None
        and turn.actual_grounding.get("status") == "RESOLVED"
        for turn in turns
    )
    no_mutation = sum(turn.clarification_without_mutation is True for turn in turns)
    return {
        "dialogues": len(run.dialogues),
        "dialogue_exact": sum(dialogue.dialogue_exact for dialogue in run.dialogues),
        "final_graph_exact": sum(dialogue.final_graph_exact for dialogue in run.dialogues),
        "operator_turns": len(turns),
        "turn_exact": sum(turn.turn_exact for turn in turns),
        "natural_language_turns": len(natural),
        "intent_exact": sum(turn.intent_exact is True for turn in natural),
        "slots_exact": sum(turn.slots_exact is True for turn in natural),
        "candidate_selection_turns": len(selections),
        "candidate_selection_exact": sum(turn.turn_exact for turn in selections),
        "referent_turns": len(referents),
        "referent_exact": sum(turn.referent_exact is True for turn in referents),
        "patch_turns": len(patches),
        "patch_exact": sum(turn.patch_exact is True for turn in patches),
        "clarification_expected": len(expected_clarifications),
        "clarification_predicted": len(predicted_clarifications),
        "clarification_tp": clarification_tp,
        "wrong_guesses": wrong_guesses,
        "clarification_without_mutation": no_mutation,
        "harness_errors": sum(len(dialogue.harness_errors) for dialogue in run.dialogues),
    }


def _turn_dict(turn: TurnScore) -> dict:
    return asdict(turn)


def to_dict(run: InteractionRun) -> dict:
    counts = _counts(run)
    expected = counts["clarification_expected"]
    predicted = counts["clarification_predicted"]
    tp = counts["clarification_tp"]
    metrics = {
        "dialogue_exact": {"n": counts["dialogue_exact"], "d": counts["dialogues"]},
        "turn_exact": {"n": counts["turn_exact"], "d": counts["operator_turns"]},
        "intent_accuracy": {"n": counts["intent_exact"], "d": counts["natural_language_turns"]},
        "slot_accuracy": {"n": counts["slots_exact"], "d": counts["natural_language_turns"]},
        "referent_resolution_accuracy": {
            "n": counts["referent_exact"],
            "d": counts["referent_turns"],
        },
        "patch_exact": {"n": counts["patch_exact"], "d": counts["patch_turns"]},
        "clarification_precision": {"n": tp, "d": predicted},
        "clarification_recall": {"n": tp, "d": expected},
        "wrong_guess_rate": {"n": counts["wrong_guesses"], "d": expected},
        "clarification_without_mutation": {
            "n": counts["clarification_without_mutation"],
            "d": predicted,
        },
        "candidate_selection_exact": {
            "n": counts["candidate_selection_exact"],
            "d": counts["candidate_selection_turns"],
        },
        "final_graph_exact": {
            "n": counts["final_graph_exact"],
            "d": counts["dialogues"],
        },
    }
    return {
        "meta": {
            "track": run.track,
            "backend_kind": run.backend_kind,
            "model": run.model,
            "scene_hash": run.scene_hash,
            "validator_version": run.validator_version,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        },
        "counts": counts,
        "metrics": metrics,
        "dialogues": [
            {
                "id": dialogue.id,
                "family": dialogue.family,
                "profile": dialogue.profile,
                "shape": dialogue.shape,
                "final_graph_exact": dialogue.final_graph_exact,
                "dialogue_exact": dialogue.dialogue_exact,
                "resolved_models": list(dialogue.resolved_models),
                "harness_errors": list(dialogue.harness_errors),
                "turns": [_turn_dict(turn) for turn in dialogue.turns],
                "session_audit": dialogue.session_audit,
            }
            for dialogue in run.dialogues
        ],
    }


def to_json(run: InteractionRun, *, indent: int = 2) -> str:
    return json.dumps(to_dict(run), indent=indent, sort_keys=True, ensure_ascii=False)


def text_report(run: InteractionRun) -> str:
    c = _counts(run)
    lines = [
        "P8.4 operator-interaction evaluation (RESEARCH_CONTRACT.md §18.11)",
        "=" * 72,
        f"track          {run.track}",
        f"backend        {run.backend_kind}" + (f" ({run.model})" if run.model else ""),
        f"scene_hash     {run.scene_hash}",
        f"validator      {run.validator_version}",
        f"run            {run.started_at} .. {run.finished_at}",
        "",
        "sample denominators",
        f"  dialogues                    {c['dialogues']}",
        f"  operator/audit turns         {c['operator_turns']}",
        f"  natural-language turns       {c['natural_language_turns']}",
        f"  structured selections        {c['candidate_selection_turns']}",
        f"  resolved-referent turns      {c['referent_turns']}",
        f"  expected patch turns         {c['patch_turns']}",
        "  clarification +/-            "
        f"{c['clarification_expected']}/"
        f"{c['operator_turns'] - c['clarification_expected']}",
        "",
        "metrics (raw count and ratio)",
        f"  dialogue exact               {_ratio(c['dialogue_exact'], c['dialogues'])}",
        f"  turn exact                   {_ratio(c['turn_exact'], c['operator_turns'])}",
        f"  final graph exact            {_ratio(c['final_graph_exact'], c['dialogues'])}",
        f"  intent accuracy              {_ratio(c['intent_exact'], c['natural_language_turns'])}",
        f"  slot accuracy                {_ratio(c['slots_exact'], c['natural_language_turns'])}",
        f"  referent accuracy            {_ratio(c['referent_exact'], c['referent_turns'])}",
        f"  patch exact                  {_ratio(c['patch_exact'], c['patch_turns'])}",
        "  clarification precision      "
        f"{_ratio(c['clarification_tp'], c['clarification_predicted'])}",
        "  clarification recall         "
        f"{_ratio(c['clarification_tp'], c['clarification_expected'])}",
        f"  wrong guesses                {_ratio(c['wrong_guesses'], c['clarification_expected'])}",
        "  clarification no-mutation    "
        f"{_ratio(c['clarification_without_mutation'], c['clarification_predicted'])}",
        "  candidate selection exact    "
        f"{_ratio(c['candidate_selection_exact'], c['candidate_selection_turns'])}",
        f"  harness errors               {c['harness_errors']}",
        "",
        "per dialogue",
    ]
    for dialogue in run.dialogues:
        lines.append(
            f"  {dialogue.id} {dialogue.family}/{dialogue.shape:<19} "
            f"turn {sum(t.turn_exact for t in dialogue.turns)}/{len(dialogue.turns)}  "
            f"graph={dialogue.final_graph_exact}  exact={dialogue.dialogue_exact}"
        )
        for error in dialogue.harness_errors:
            lines.append(f"       HARNESS {error}")
    return "\n".join(lines)


__all__ = ["text_report", "to_dict", "to_json"]
