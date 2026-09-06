# P8.4 Operator–LLM interaction 평가 결과

측정일: 2026-09-06  
계약: `RESEARCH_CONTRACT.md` v1.35 / D-035~D-037  
Validator: 1.4  
scene hash: `3141d8d32e04c12fbb6e9927f80440491ff5ace62a6e7264788f4e5d326566bb`

## 평가 순서와 재현 기준

12개 gold dialogue(`A1..C4`)는 live 호출 전에 커밋했다. 최초 gold commit은 `8f11f22`,
initial/final graph 분리와 patch 결과 명문화는 각각 `b72b7c7`, `bfa587b`다. 하네스 구현
commit은 `eadad48`이며, 그 다음에 최초 live 평가를 한 번 수행했다. 따라서 아래 정답은 live
결과를 본 뒤 바꾼 것이 아니다.

- 12 dialogues / 36 operator·audit turns
- 자연어 intent·slot 평가 33 turns
- 구조화된 후보 선택 3 turns(LLM 호출 0, intent·slot 분모에서 제외)
- resolved referent 평가 16 turns
- expected patch 평가 5 turns
- clarification positive/negative 3/33 turns

원자료:

- `data/eval_results/p8_4_grounder_only.{json,txt}`
- `data/eval_results/p8_4_gpt-5-mini.{json,txt}`

JSON은 각 turn의 gold·actual, session event audit, raw numerator/denominator를 포함한다. 집계는
JSON의 turn 원자료에서 독립 재계산해 저장된 `counts`와 일치함을 확인했다.

## 결과

| 지표 | grounder-only | end-to-end live |
|---|---:|---:|
| dialogue exact | 12/12 | 6/12 |
| turn exact | 36/36 | 21/36 |
| final graph exact | 12/12 | 7/12 |
| intent accuracy | 주입 경계 33/33 | 30/33 |
| slot accuracy | 주입 경계 33/33 | 26/33 |
| referent resolution | 16/16 | 6/16 |
| canonical patch exact | 5/5 | 0/5 |
| clarification precision | 3/3 | 3/11 |
| clarification recall | 3/3 | 3/3 |
| wrong guess | 0/3 | 0/3 |
| clarification no-mutation | 3/3 | 11/11 |
| candidate-selection exact | 3/3 | 1/3 |

grounder-only의 intent·slot 33/33은 모델 성능이 아니다. 사람이 고정한 intent·slot을
`MockBackend`로 주입하는 배선 검사다. 이 track이 보여주는 것은 같은 입력을 받은 결정론적
grounder·canonical patch builder·Validator·CBBA 경로가 gold와 12/12 일치한다는 점이다.

end-to-end는 `gpt-5-mini`를 요청했고 실제 snapshot은
`gpt-5-mini-2025-08-07`이었다. 발표에서 사용해야 할 모델 포함 헤드라인은 이 live 결과다.

## 실패 분석

실패는 크게 두 경계에 집중됐다.

1. 모델이 한국어 조사를 slot에 포함했다. 예: `Warehouse 구역에`, `Utility Yard에서`,
   `거기는`, `FIRE_SITE_2에`. 현재 결정론적 matcher는 이 문자열을 알려진 id/alias와 같다고
   추정하지 않고 fail-closed clarification을 냈다. 잘못된 incident를 고른 사례는 0/3이지만,
   불필요한 clarification이 늘어 precision이 3/11로 낮아졌다.
2. B4·C4의 `NEW_MISSION`에서 모델이 사용하면 안 되는 `note` slot을 채웠다. strict wire
   schema가 이를 받아들이지 않아 `TURN_ERROR`가 됐다. 이어지는 후보 선택은 pending
   clarification이 없으므로 두 turn 모두 평가상 실패로 남겼다. 앞선 실패 때문에 후속 turn을
   제거하거나 분모에서 숨기지 않았다.

`C2`의 마지막 QUERY는 grounding 자체는 맞았지만 `about=mission` gold에 대해
`about=incidents`를 출력해 slot exact에서 실패했다.

## 해석과 주장 경계

- 결정론적 계층은 고정 gold에서 기대대로 동작했다.
- 실제 LLM을 포함한 상호작용 전체가 안정적이라고 주장할 수 없다. 현재 병목은 task graph
  Validator가 아니라 intent wire slot과 deterministic text grounding 사이의 경계다.
- clarification recall 3/3, wrong guess 0/3, no-mutation 11/11은 fail-closed 안전 동작을
  뒷받침한다. 다만 낮은 precision은 운용 효율 한계다.
- 이 12개를 보고 prompt/normalizer를 고친 뒤 같은 셋의 상승값을 새 headline으로 쓰지 않는다.
  그런 수정은 engineering 개선으로 별도 기록하고, 성능 주장은 새 held-out dialogue에서만
  검증한다.

## 재실행

```bash
# 결정론적 compiler/grounder 회귀
python3 -m evaluation.interaction_eval --grounder-only \
  --out data/eval_results/p8_4_grounder_only

# live + 성공 응답 exact cache 기록
python3 -m evaluation.interaction_eval \
  --out data/eval_results/p8_4_gpt-5-mini

# 네트워크 없는 성공 응답 재생(실패 응답은 cache하지 않음)
python3 -m evaluation.interaction_eval --cached
```
