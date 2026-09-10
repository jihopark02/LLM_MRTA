# D-076 held-out evaluation set (RESEARCH_CONTRACT §18.15, DECISIONS S12)

45 cases — `explicit/` (15), `compositional/` (15), `contextual/` (15).

Each YAML fixes, **before any live run**:

- `world` — a fixed scene fixture (reproducibility snapshot, not a runtime
  scenario branch).
- `initial_graph` / `event_history` / `referents` / `completed_recon` — the
  world state the utterance is interpreted against.
- `utterance` — the free-form operator command.
- `expected.kind` / `expected.semantic_ir` (compact DSL) / `expected.outcome`
  — the human-authored intent.
- `expected.resolved` — **derived** by running the real resolver at authoring
  time; the loader re-derives and rejects the file if it disagrees. `final
  graph / patch` is likewise derived + Validator-self-checked at load, never
  hand-authored.

Each level contains fail-closed cases (expected `CLARIFICATION`); `contextual/`
contains three world-counterfactual pairs (`X01a/b`, `X02a/b`, `X03a/b`) —
same utterance, different world → different resolved targets.

`worlds/tie_park.yaml` is an eval-only fixture: two fires at equal x, so a
spatial pick is a genuine tie.

**Freeze rule.** The commit that adds this directory and `evaluation/d076_eval.py`
is the freeze point. After the live run, the annotations and the intent prompt
are **not** edited to chase a number — a revision means a new decision (D-077+)
and a new evaluation version.

Run: `python3 -m evaluation.d076_eval --mock` (gold-backend self-test) /
`--live` / `--cached`. Regenerate the derived fields (never the intent):
`python3 scripts/gen_d076_eval.py`.
