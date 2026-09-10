"""One-shot authoring helper for the D-076 held-out evaluation set (S12).

Each case's `utterance`, `expected.kind`, `expected.semantic_ir` (compact DSL)
and `expected.outcome` are human-authored intent. `expected.resolved` is
DERIVED here by running the real resolver against the case's world/state/event
snapshot, then written into the YAML so it is self-documenting and a resolver
regression fails the loader loudly (RESEARCH_CONTRACT §18.15).

Run once, review the YAMLs, commit. Not part of the test path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.d076_eval import (  # noqa: E402
    _ROOT,
    LEVELS,
    _resolved_dict,
    _WorldCtx,
    expand_ir,
)
from interaction.ground import GroundingOutcome  # noqa: E402
from interaction.resolve import resolve_mission_ir  # noqa: E402
from scenarios.scene import load_scene  # noqa: E402

OUT = _ROOT / "data" / "d076_eval"

IP = "scenarios/industrial_park.yaml"
SG = "scenarios/stress_grid.yaml"
TIE = "data/d076_eval/worlds/tie_park.yaml"

# recon chain helpers for initial_graph specs
RECON = lambda *z: {"recon_zones": list(z)}  # noqa: E731
def CHAIN(**kw):
    return {"incident_chains": kw}


def _merge(*specs):
    out = {}
    for s in specs:
        for k, v in s.items():
            if isinstance(v, dict):
                out.setdefault(k, {}).update(v)
            else:
                out.setdefault(k, []).extend(v)
    return out


CASES: list[dict] = []


def case(cid, level, world, utterance, ir, outcome, *, initial_graph=None,
         event_history=None, referents=None, completed_recon=None,
         clarification_reason=None, counterfactual_of=None):
    rec = {
        "id": cid,
        "level": level,
        "world": world,
        "utterance": utterance,
        "expected": {"kind": "UPDATE_MISSION" if initial_graph else "NEW_MISSION",
                     "semantic_ir": ir, "outcome": outcome},
    }
    if initial_graph is not None:
        rec["initial_graph"] = initial_graph
    if event_history:
        rec["event_history"] = event_history
    if referents:
        rec["referents"] = referents
    if completed_recon:
        rec["completed_recon"] = completed_recon
    if clarification_reason:
        rec["expected"]["clarification_reason"] = clarification_reason
    if counterfactual_of:
        rec["counterfactual_of"] = counterfactual_of
    CASES.append(rec)


# ============================ EXPLICIT (15) ============================

case("E01", "explicit", IP, "Warehouse 구역을 정찰해줘",
     {"recon": [{"explicit": ["Warehouse"]}]}, "COMMITTED")
case("E02", "explicit", IP, "Warehouse랑 Tank Farm 두 곳을 항공 정찰해줘",
     {"recon": [{"explicit": ["Warehouse", "Tank Farm"]}]}, "COMMITTED")
case("E03", "explicit", IP, "FIRE_SITE_1은 지상 점검까지만 대응해줘",
     {"responses": [{"explicit": ["FIRE_SITE_1"], "up_to": "inspection"}]}, "COMMITTED")
case("E04", "explicit", IP, "FIRE_SITE_1을 지상 진압까지 대응해줘",
     {"responses": [{"explicit": ["FIRE_SITE_1"], "up_to": "suppression"}]}, "COMMITTED")
case("E05", "explicit", IP, "네 구역 A B C D 전부 정찰해줘",
     {"recon": [{"explicit": ["A", "B", "C", "D"]}]}, "COMMITTED")
case("E06", "explicit", IP, "FIRE_SITE_1과 FIRE_SITE_2 둘 다 지상 진압까지 대응해줘",
     {"responses": [{"explicit": ["FIRE_SITE_1", "FIRE_SITE_2"], "up_to": "suppression"}]},
     "COMMITTED")
case("E07", "explicit", IP, "FIRE_SITE_1도 지상 진압까지 처리해줘",
     {"responses": [{"explicit": ["FIRE_SITE_1"], "up_to": "suppression"}]}, "COMMITTED",
     initial_graph=RECON("ZONE_A"))
case("E08", "explicit", IP, "FIRE_SITE_1을 지상 진압 단계까지 이어서 대응해줘",
     {"responses": [{"explicit": ["FIRE_SITE_1"], "up_to": "suppression"}]}, "COMMITTED",
     initial_graph=CHAIN(FIRE_SITE_1=["GROUND_INSPECTION"]))
case("E09", "explicit", IP, "Utility Yard도 정찰 목록에 추가해줘",
     {"recon": [{"explicit": ["Utility Yard"]}]}, "COMMITTED",
     initial_graph=RECON("ZONE_A", "ZONE_B"))
case("E10", "explicit", IP, "Warehouse를 정찰하고, 화재가 발견되면 지상 진압까지 대응해줘",
     {"recon": [{"explicit": ["Warehouse"]}], "incident_policy": {"up_to": "suppression"}},
     "COMMITTED")
case("E11", "explicit", IP, "FIRE_SITE_1을 다시 지상 진압까지 처리해줘",
     {"responses": [{"explicit": ["FIRE_SITE_1"], "up_to": "suppression"}]}, "NO_CHANGE",
     initial_graph=CHAIN(FIRE_SITE_1=["GROUND_INSPECTION", "GROUND_SUPPRESSION"]))
case("E12", "explicit", IP, "Tank Farm 구역만 정찰해줘",
     {"recon": [{"explicit": ["Tank Farm"]}]}, "COMMITTED")
case("E13", "explicit", IP, "North Gate 구역을 정찰해줘",
     {"recon": [{"explicit": ["North Gate"]}]}, "CLARIFICATION",
     clarification_reason="UNKNOWN_ENTITY")
case("E14", "explicit", IP, "FIRE_SITE_9를 지상 진압까지 대응해줘",
     {"responses": [{"explicit": ["FIRE_SITE_9"], "up_to": "suppression"}]}, "CLARIFICATION",
     clarification_reason="UNKNOWN_ENTITY")
case("E15", "explicit", IP, "Processing Area를 정찰하되 Processing Area는 빼줘",
     {"recon": [{"explicit": ["Processing Area"], "exclude": ["Processing Area"]}]},
     "CLARIFICATION", clarification_reason="NO_ENTITIES")


# ========================= COMPOSITIONAL (15) =========================

case("C01", "compositional", SG, "A부터 H까지 정찰하되 C와 F는 빼줘",
     {"recon": [{"range": ["A", "H"], "exclude": ["C", "F"]}]}, "COMMITTED")
case("C02", "compositional", SG, "북쪽 절반 구역을 전부 항공 정찰해줘",
     {"recon": [{"region": "north"}]}, "COMMITTED")
case("C03", "compositional", SG, "서쪽 구역을 정찰하되 A와 B는 빼줘",
     {"recon": [{"region": "west", "exclude": ["A", "B"]}]}, "COMMITTED")
case("C04", "compositional", SG, "A부터 O까지 전 구역을 정찰해줘",
     {"recon": [{"range": ["A", "O"]}]}, "COMMITTED")
case("C05", "compositional", SG, "A부터 D까지, 그리고 M부터 O까지 정찰해줘",
     {"recon": [{"range": ["A", "D"]}, {"range": ["M", "O"]}]}, "COMMITTED")
case("C06", "compositional", SG, "A부터 F까지 정찰하고 FIRE_SITE_1은 지상 진압까지 대응해줘",
     {"recon": [{"range": ["A", "F"]}],
      "responses": [{"explicit": ["FIRE_SITE_1"], "up_to": "suppression"}]}, "COMMITTED")
case("C07", "compositional", SG,
     "FIRE_SITE_1은 점검까지만, FIRE_SITE_2는 진압까지 대응해줘",
     {"responses": [{"explicit": ["FIRE_SITE_1"], "up_to": "inspection"},
                    {"explicit": ["FIRE_SITE_2"], "up_to": "suppression"}]}, "COMMITTED")
case("C08", "compositional", SG, "D부터 G까지 구역도 정찰 목록에 추가해줘",
     {"recon": [{"range": ["D", "G"]}]}, "COMMITTED",
     initial_graph=RECON("ZONE_A", "ZONE_B", "ZONE_C"))
case("C09", "compositional", SG, "A부터 H까지 정찰하되 양 끝 A와 H는 빼줘",
     {"recon": [{"range": ["A", "H"], "exclude": ["A", "H"]}]}, "COMMITTED")
case("C10", "compositional", SG, "남쪽 구역을 정찰하고 알려진 모든 화재는 점검까지만 대응해줘",
     {"recon": [{"region": "south"}],
      "responses": [{"recency": "all", "up_to": "inspection"}]}, "COMMITTED")
case("C11", "compositional", SG,
     "FIRE_SITE_1, FIRE_SITE_2, FIRE_SITE_3, FIRE_SITE_4를 전부 지상 진압까지 대응해줘",
     {"responses": [{"explicit": ["FIRE_SITE_1", "FIRE_SITE_2", "FIRE_SITE_3", "FIRE_SITE_4"],
                     "up_to": "suppression"}]}, "COMMITTED",
     initial_graph=_merge(RECON(*[f"ZONE_{c}" for c in "ABCDEFGHIJKLMNO"])))
case("C12", "compositional", SG,
     "A부터 D까지 정찰하고, FIRE_SITE_1은 점검까지만, FIRE_SITE_2는 진압까지 대응해줘",
     {"recon": [{"range": ["A", "D"]}],
      "responses": [{"explicit": ["FIRE_SITE_1"], "up_to": "inspection"},
                    {"explicit": ["FIRE_SITE_2"], "up_to": "suppression"}]}, "COMMITTED")
case("C13", "compositional", SG,
     "A부터 F까지 정찰하고 FIRE_SITE_1은 점검까지만 하되 진압까지도 해줘",
     {"recon": [{"range": ["A", "F"]}],
      "responses": [{"explicit": ["FIRE_SITE_1"], "up_to": "inspection"},
                    {"explicit": ["FIRE_SITE_1"], "up_to": "suppression"}]}, "CLARIFICATION",
     clarification_reason="SEMANTIC_CONFLICT")
case("C14", "compositional", SG, "A부터 H까지 정찰하되 ZONE_Z는 빼줘",
     {"recon": [{"range": ["A", "H"], "exclude": ["ZONE_Z"]}]}, "CLARIFICATION",
     clarification_reason="UNKNOWN_ENTITY")
case("C15", "compositional", SG, "H부터 A까지 순서대로 정찰해줘",
     {"recon": [{"range": ["H", "A"]}]}, "CLARIFICATION",
     clarification_reason="UNKNOWN_ENTITY")


# =========================== CONTEXTUAL (15) ==========================

_S_F1F3 = [{"incident": "FIRE_SITE_1", "source": "sensor", "t": 10.0},
           {"incident": "FIRE_SITE_3", "source": "sensor", "t": 20.0}]
_S_F2F4 = [{"incident": "FIRE_SITE_2", "source": "sensor", "t": 10.0},
           {"incident": "FIRE_SITE_4", "source": "sensor", "t": 20.0}]
_EAST_RECENT = {"responses": [{"recency": "recent", "count": 2, "source": "sensor",
                               "spatial_pick": "eastmost", "up_to": "inspection"}]}
case("X01a", "contextual", SG, "방금 센서가 발견한 두 화재 중 동쪽 것은 점검까지만 대응해줘",
     _EAST_RECENT, "COMMITTED", event_history=_S_F1F3)
case("X01b", "contextual", SG, "방금 센서가 발견한 두 화재 중 동쪽 것은 점검까지만 대응해줘",
     _EAST_RECENT, "COMMITTED", event_history=_S_F2F4, counterfactual_of="X01a")

_OP_F3 = [{"incident": "FIRE_SITE_1", "source": "operator", "t": 10.0},
          {"incident": "FIRE_SITE_3", "source": "operator", "t": 20.0}]
_OP_F1 = [{"incident": "FIRE_SITE_2", "source": "operator", "t": 10.0},
          {"incident": "FIRE_SITE_1", "source": "operator", "t": 20.0}]
_LAST_OP = {"responses": [{"recency": "recent", "count": 1, "source": "operator",
                           "up_to": "suppression"}]}
case("X02a", "contextual", SG, "가장 최근에 보고된 화재를 지상 진압까지 대응해줘",
     _LAST_OP, "COMMITTED", event_history=_OP_F3)
case("X02b", "contextual", SG, "가장 최근에 보고된 화재를 지상 진압까지 대응해줘",
     _LAST_OP, "COMMITTED", event_history=_OP_F1, counterfactual_of="X02a")

_DEIXIS = {"responses": [{"deixis": "거기", "up_to": "suppression"}]}
case("X03a", "contextual", SG, "거기 지상 진압까지 대응해줘",
     _DEIXIS, "COMMITTED", referents=["FIRE_SITE_2"])
case("X03b", "contextual", SG, "거기 지상 진압까지 대응해줘",
     _DEIXIS, "COMMITTED", referents=["FIRE_SITE_3"], counterfactual_of="X03a")

case("X04", "contextual", SG, "알려진 모든 화재를 지상 점검까지만 대응해줘",
     {"responses": [{"recency": "all", "up_to": "inspection"}]}, "COMMITTED")
case("X05", "contextual", SG, "아직 정찰하지 않은 구역만 다시 항공 정찰해줘",
     {"recon": [{"range": ["A", "J"], "unvisited_only": True}]}, "COMMITTED",
     initial_graph=RECON("ZONE_A", "ZONE_B", "ZONE_C", "ZONE_D", "ZONE_E"),
     completed_recon=["ZONE_A", "ZONE_B"])
case("X06", "contextual", SG, "알려진 화재 중 가장 북쪽 것만 점검까지 대응해줘",
     {"responses": [{"recency": "all", "spatial_pick": "northmost", "up_to": "inspection"}]},
     "COMMITTED")
case("X07", "contextual", TIE, "두 화재 중 동쪽에 있는 것을 지상 진압까지 대응해줘",
     {"responses": [{"recency": "all", "spatial_pick": "eastmost", "up_to": "suppression"}]},
     "CLARIFICATION", clarification_reason="AMBIGUOUS_ENTITY")
case("X08", "contextual", SG, "방금 센서가 감지한 화재를 지상 진압까지 대응해줘",
     {"responses": [{"recency": "recent", "source": "sensor", "up_to": "suppression"}]},
     "CLARIFICATION", clarification_reason="NO_ENTITIES",
     event_history=[{"incident": "FIRE_SITE_1", "source": "operator", "t": 10.0}])
case("X09", "contextual", SG, "방금 발견한 세 화재를 지상 진압까지 대응해줘",
     {"responses": [{"recency": "recent", "count": 3, "source": "sensor",
                     "up_to": "suppression"}]}, "CLARIFICATION",
     clarification_reason="NO_ENTITIES", event_history=_S_F1F3)
case("X10", "contextual", SG, "그 화재를 지상 진압까지 대응해줘",
     {"responses": [{"deixis": "그 화재", "up_to": "suppression"}]}, "CLARIFICATION",
     clarification_reason="AMBIGUOUS_ENTITY")
case("X11", "contextual", SG, "직전에 발견한 화재를 지상 진압까지 대응해줘",
     {"responses": [{"recency": "previous", "up_to": "suppression"}]}, "COMMITTED",
     event_history=[{"incident": "FIRE_SITE_1", "source": "sensor", "t": 10.0},
                    {"incident": "FIRE_SITE_2", "source": "sensor", "t": 20.0},
                    {"incident": "FIRE_SITE_3", "source": "sensor", "t": 30.0}])
case("X12", "contextual", SG, "최근에 파악된 화재 두 곳을 지상 점검까지만 대응해줘",
     {"responses": [{"recency": "recent", "count": 2, "up_to": "inspection"}]}, "COMMITTED",
     event_history=[{"incident": "FIRE_SITE_1", "source": "sensor", "t": 10.0},
                    {"incident": "FIRE_SITE_2", "source": "operator", "t": 20.0}])


# ------------------------------ emit ------------------------------

def _resolved_for(rec) -> dict | None:
    scene = load_scene(_ROOT / rec["world"])
    ctx = _WorldCtx(
        scene=scene,
        world=rec["world"],
        initial_graph_spec=rec.get("initial_graph"),
        event_history=tuple(rec.get("event_history") or ()),
        referents=tuple(rec.get("referents") or ()),
        completed_recon=tuple(rec.get("completed_recon") or ()),
    )
    ir = expand_ir(rec["expected"]["semantic_ir"])
    out = resolve_mission_ir(ir, ctx.build("gen"))
    if isinstance(out, GroundingOutcome):
        return None
    d = _resolved_dict(out)
    lower = {"GROUND_INSPECTION": "inspection", "GROUND_SUPPRESSION": "suppression"}
    return {
        "recon": [list(z) for z in d["recon"]],
        "responses": [[list(ids), lower[up]] for ids, up in d["responses"]],
    }


def main() -> None:
    seen: set[str] = set()
    for rec in CASES:
        assert rec["id"] not in seen, rec["id"]
        seen.add(rec["id"])
        resolved = _resolved_for(rec)
        if resolved is not None and rec["expected"]["outcome"] in {"COMMITTED", "NO_CHANGE"}:
            rec["expected"]["resolved"] = resolved
        path = OUT / rec["level"] / f"{rec['id']}.yaml"
        path.write_text(
            yaml.safe_dump(rec, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )
    counts = {lvl: sum(c["level"] == lvl for c in CASES) for lvl in LEVELS}
    print("wrote", len(CASES), "cases", counts)


if __name__ == "__main__":
    main()
