# P6 결과 — LLM 임무 분해 평가

RESEARCH_CONTRACT.md §12 / §15, D-021 · D-022 · D-023 · D-024. 소표본(9개) 평가이므로
백분율이 아니라 원시 개수로 보고한다. P6는 D-024 시점에 승인 완료.

## 실행 조건 (재현성, §14)

| 항목 | 값 |
|------|-----|
| backend | `OpenAIBackend` |
| 모델 (요청 alias) | `gpt-5-mini` |
| 모델 (실제 resolved, 전 호출) | `gpt-5-mini-2025-08-07` |
| scene_hash | `0e8f098cd95aba26f1384fc6ad5c89ad047ec84912cf595936a7b56d75672c6d` |
| validator_version | `1.3` (candidate 경로 invariant **#1~#12**) |
| 실행 시각 (UTC) | 2026-09-02 09:39:33 – 09:42:17 |
| 입력 | `data/reference_annotations/{A1..C3}.yaml` (LLM 호출 전 커밋: `c3ed0f3`) |
| 원자료 | `data/eval_results/p6_gpt-5-mini.{json,txt}`, 그림 `.png/.pdf` |

`p6_gpt-5-mini.json`은 case별로 raw·final 후보의 `tasks`(task_type/target/파생 priority)·
`edges`·`graph_hash`·`accepted`·`error_codes`, 그리고 schema/구조 실패 시 구조화된
`pipeline_errors`(code/subject/detail)를 담는다. 제3자는 `task_type`/`target`만으로
task·edge precision/recall·exact match를 독립 재계산할 수 있다.

재현: `pip install -e '.[llm,viz]'` 후
`python3 -m evaluation --model gpt-5-mini --out data/eval_results/p6_gpt-5-mini --plot`.

## 집계 (X/9)

| 지표 | 결과 |
|------|------|
| schema-valid | 9/9 |
| raw whole-graph-valid | 9/9 |
| approved | 9/9 |
| harness error | 0/9 |
| exact graph match (raw = final) | 9/9 |
| failure category | 없음 |

**repair**: attempted 0/9, first-pass approved 9/9. repair가 한 번도 트리거되지 않았으므로
이 실행은 repair의 실효성을 입증하지 않는다 — repair 경로는 mock·negative 테스트
(`tests/test_llm_pipeline.py`)로만 검증됐다.

## Graph 지표 (best-matching allowed reference 대조)

| 축 | task P/R (macro) | task micro tp/fp/fn | edge P/R (macro) | edge micro tp/fp/fn |
|----|------------------|---------------------|------------------|---------------------|
| raw | 1.00 / 1.00 | 77 / 0 / 0 | 1.00 / 1.00 | 27 / 0 / 0 |
| final | 1.00 / 1.00 | 77 / 0 / 0 | 1.00 / 1.00 | 27 / 0 / 0 |

edge macro는 채점 가능한 edge 집합이 있는 case(family A·C, 6개)의 평균이다.

family별 (final):

| family | approved | exact | task P/R | edge P/R |
|--------|----------|-------|----------|----------|
| A (FULL_RESPONSE) | 3/3 | 3/3 | 1.00 / 1.00 | 1.00 / 1.00 |
| B (AERIAL_ONLY) | 3/3 | 3/3 | 1.00 / 1.00 | **N/A** (정답 edge 0개) |
| C (SELECTIVE_RESPONSE) | 3/3 | 3/3 | 1.00 / 1.00 | 1.00 / 1.00 |

## Latency

명령당 벽시계(Step1+Step2, repair 없음): min 10.7s / mean 18.2s / max 22.7s.
가장 빠른 건 family B(6 task/0 edge).

## 해석

- **9/9 정확 일치.** gpt-5-mini는 이 시나리오의 임무 분해를 오류 없이 수행했다. Step1
  출력이 전부 schema를 통과했고(0 repair), whole-graph Validator도 전부 첫 시도에 승인.
- 이 결과는 과제가 **잘 제약돼 있기 때문**이기도 하다: task 어휘 5종이 고정돼 있고,
  prompt에 scene facts(zone·incident·priority)와 task glossary(의미+담당 platform, D-020)가
  주입되며, workflow chain 규칙이 명시된다. priority·좌표·capability는 LLM이 만들지 않고
  compiler가 파생하므로(D-022), 이 평가는 **LLM이 생성하는 것 = graph 구조(task_type·
  target·edge)**만 측정한다.
- **결정론적 Validator의 역할은 여전히 유효하다.** 이번 표본에서 LLM이 틀리지 않았다고
  해서 Validator가 불필요한 게 아니라, "승인된 candidate graph는 schema + whole-graph
  invariant **#1~#12**를 만족함"이라는 보증을 제공한다(§9). #13~#14는 MissionPatch 경로
  전용이며 이 평가에 적용되지 않는다. 실패가 나오면 구조화된 error code로 최대 1회 repair가
  돌고, 그래도 안 되면 명시적 REJECT(§12, D-019) — reference로의 silent fallback 없음.
- **한계**: n=9, 단일 scene, 단일 모델, 단일 실행. 통계적 일반화는 불가. 프롬프트가
  관대하다(glossary 포함). repair 경로는 라이브로 실증되지 않았다. 더 어려운 조건 —
  glossary 제거, 모호한 명령, 다중 scene, 반복 실행으로 분산 측정, 더 약한 모델 — 은
  후속(P8 또는 확장 평가)으로 남긴다.
- RQ1(LLM task graph **구조** 생성) 파이프라인은 이 표본에서 end-to-end로 동작함을 확인.
