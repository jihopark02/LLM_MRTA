# LLM_MRTA

LLM-Based Disaster Mission Decomposition and CBBA Task Allocation for Heterogeneous
Unmanned Systems

학부 학술대회 발표용 독립 연구 프로젝트. `/home/jiho/LLM_CBBA`와 Git 이력·연구 계약을
공유하지 않는다.

- 연구 계약 (단일 진실 원천): [`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md)
- 설계 결정 이력: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- 이식 코드 등록부: [`docs/PROVENANCE.md`](docs/PROVENANCE.md)

## 현재 단계

**P1~P6.5 완료** — `validator/`(P2) + `allocation/`(P3) + `execution/`(P4:
`SimExecutor`) + `llm/`(P5: Step1/Step2/repair 파이프라인 §12) + `evaluation/`(P6:
9개 입력 평가 하네스 + 감사 JSON + 시각화; P6.5: 통합 runner). 테스트 232개 통과.

P6 실측(gpt-5-mini, 2026-09-02, validator 1.3): 9/9 approved, task precision/recall
1.00/1.00, edge P/R 1.00/1.00(family A·C), exact graph match 9/9, repair 0회. 상세는
[`docs/P6_RESULTS.md`](docs/P6_RESULTS.md), 원자료 `data/eval_results/`.
재현: `python3 -m evaluation --out data/eval_results/p6 --plot`.

P6.5 통합 runner(D-025, D-026): 대표 명령 A1/B1/C1. NL → `generate_mission`(RQ1) →
검증된 graph가 `allocate`(plan-time CBBA)와 `SimExecutor`(event-driven 실행)로 **각각**
들어간다(fork — allocate 결과는 executor에 전달 안 됨). 3/3 demo_pass(annotation
exact-match + 무위반 완주), A1(=P1 fixture graph)은 P3/P4 골든 makespan(359.8/257.9)과
graph_hash까지 일치. `python3 -m evaluation.integration [--mock]`.

priority·좌표·capability는 LLM이 만들지 않고 결정론적 compiler가 파생한다(D-022) —
LLM 출력은 graph 구조(task_type·target·edge)뿐이다. task 어휘: `GROUND_SUPPRESSION`
workflow (D-016). 계약 버전 v1.25 / 최신 결정 D-027 (P8 = 실행 전 다중 턴 자연어 계획
세션, §18 — Codex 검토 대기). 단계 게이트 정의는
[`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md) §15 참고.

새로운 LLM 모델이나 CBBA 알고리즘을 제안하는 연구가 아니다. 검증된 구성요소를 통합하고
재현 가능하게 시연·평가한다.
