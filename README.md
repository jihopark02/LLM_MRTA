# LLM_MRTA

LLM-Based Disaster Mission Decomposition and CBBA Task Allocation for Heterogeneous
Unmanned Systems

학부 학술대회 발표용 독립 연구 프로젝트. `/home/jiho/LLM_CBBA`와 Git 이력·연구 계약을
공유하지 않는다.

- 연구 계약 (단일 진실 원천): [`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md)
- 설계 결정 이력: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- 이식 코드 등록부: [`docs/PROVENANCE.md`](docs/PROVENANCE.md)

## 현재 단계

**P1~P6 구현 완료** — `validator/`(P2) + `allocation/`(P3) + `execution/`(P4:
`SimExecutor`) + `llm/`(P5: Step1/Step2/repair 파이프라인 §12) + `evaluation/`(P6:
9개 입력 평가 하네스 + 지표 + 시각화). 테스트 214개 통과(`python3 -m pytest -q`).

P6 실측(gpt-5-mini, 2026-09-01): 9/9 approved, task·edge precision/recall 1.00/1.00,
exact graph match 9/9, repair 0회. 상세는 [`docs/P6_RESULTS.md`](docs/P6_RESULTS.md),
원자료 `data/eval_results/`. 재현: `python -m evaluation --out data/eval_results/p6 --plot`.

task 어휘: `GROUND_SUPPRESSION`(symbolic UGV 진압) workflow (D-016). 계약 버전 v1.20 /
최신 결정 D-021. 단계 게이트 정의는
[`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md) §15 참고.

새로운 LLM 모델이나 CBBA 알고리즘을 제안하는 연구가 아니다. 검증된 구성요소를 통합하고
재현 가능하게 시연·평가한다.
