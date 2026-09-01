# P6 결과 — LLM 임무 분해 평가

RESEARCH_CONTRACT.md §12 / §15, D-021. 소표본(9개) 평가이므로 백분율이 아니라 원시
개수로 보고한다.

## 실행 조건 (재현성, §14)

| 항목 | 값 |
|------|-----|
| backend | `OpenAIBackend` |
| 모델 (요청 alias) | `gpt-5-mini` |
| 모델 (실제 resolved, 전 호출) | `gpt-5-mini-2025-08-07` |
| scene_hash | `0e8f098cd95aba26f1384fc6ad5c89ad047ec84912cf595936a7b56d75672c6d` |
| validator_version | `1.2` |
| 실행 시각 (UTC) | 2026-09-01 16:28:05 – 16:30:34 |
| 입력 | `data/reference_annotations/{A1..C3}.yaml` (LLM 호출 전 커밋: `c3ed0f3`) |
| 원자료 | `data/eval_results/p6_gpt-5-mini.{json,txt}`, 그림 `.png/.pdf` |

재현: `pip install -e '.[llm,viz]'` 후
`python -m evaluation --model gpt-5-mini --out data/eval_results/p6_gpt-5-mini --plot`.

## 집계 (X/9)

| 지표 | 결과 |
|------|------|
| schema-valid | 9/9 |
| raw whole-graph-valid | 9/9 |
| repair 후 whole-graph-valid | 0/9 (repair 불필요) |
| approved | 9/9 |
| exact graph match (raw = final) | 9/9 |
| failure category | 없음 |

## Graph 지표 (best-matching allowed reference 대조)

| 축 | task P/R (macro) | task micro tp/fp/fn | edge P/R (macro) | edge micro tp/fp/fn |
|----|------------------|---------------------|------------------|---------------------|
| raw | 1.00 / 1.00 | 77 / 0 / 0 | 1.00 / 1.00 | 27 / 0 / 0 |
| final | 1.00 / 1.00 | 77 / 0 / 0 | 1.00 / 1.00 | 27 / 0 / 0 |

family별 (final): A 3/3 approved·exact, B 3/3, C 3/3 — 전부 task·edge P/R = 1.00/1.00.

## Latency

명령당 벽시계(Step1+Step2, repair 없음): min 11.0s / mean 16.5s / max 28.5s.
A1(12 task/6 edge)이 28.5s로 최대, family B(6 task/0 edge)가 가장 빠름.

## 해석

- **9/9 정확 일치.** gpt-5-mini는 이 시나리오의 임무 분해를 오류 없이 수행했다. Step1
  출력이 전부 schema를 통과했고(0 repair), whole-graph Validator도 전부 첫 시도에 승인.
- 이 결과는 과제가 **잘 제약돼 있기 때문**이기도 하다: task 어휘 5종이 고정돼 있고,
  prompt에 scene facts(zone·incident·priority)와 task glossary(의미+담당 platform, D-020)가
  주입되며, workflow chain 규칙이 명시된다. 즉 "자유로운 계획"이 아니라 "정의된 어휘로의
  구조화된 분해"를 측정한 것이다.
- **결정론적 Validator의 역할은 여전히 유효하다.** 이번 표본에서 LLM이 틀리지 않았다고
  해서 Validator가 불필요한 게 아니라, "승인된 graph는 14개 invariant를 만족함"이라는
  보증을 무료로 제공한다(§9, MP4MR의 LLM Critic 대비 차별점). 실패가 나오면 구조화된
  error code로 최대 1회 repair가 돌고, 그래도 안 되면 명시적 REJECT(§12, D-019) —
  reference로의 silent fallback 없음.
- **한계**: n=9, 단일 scene, 단일 모델, 단일 실행. 통계적 일반화는 불가. 프롬프트가
  관대하다(glossary 포함). 더 어려운 조건 — glossary 제거, 모호한 명령, 다중 scene,
  반복 실행으로 분산 측정, 더 약한 모델 — 은 후속(P8 또는 확장 평가)으로 남긴다.
- RQ1(LLM 복합 task graph 생성) 파이프라인은 이 표본에서 end-to-end로 동작함을 확인.
