# LLM_MRTA

LLM-Based Disaster Mission Decomposition and CBBA Task Allocation for Heterogeneous
Unmanned Systems

학부 학술대회 발표용 독립 연구 프로젝트. `/home/jiho/LLM_CBBA`와 Git 이력·연구 계약을
공유하지 않는다.

- 연구 계약 (단일 진실 원천): [`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md)
- 설계 결정 이력: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- 이식 코드 등록부: [`docs/PROVENANCE.md`](docs/PROVENANCE.md)

## 현재 단계

**P1·P2·P3 승인. P4 승인 완료** — `validator/`(P2: whole-graph Validator §9,
MissionPatch §10) + `allocation/`(P3: travel §8, CBBA §11, §13 지표) + `execution/`(P4:
`SimExecutor` 2D discrete-event executor, §14 deadlock 처리). 테스트 175개 통과
(`python3 -m pytest -q`). P4 게이트 통과 — reference mission 12/12 완주, capability/precedence
violation 0, deadlock 최소 재현 테스트. RQ1/RQ2 실행 파이프라인(P1~P4) 완성. 다음은
P5(LLM Step1/Step2/repair).

계약 버전 v1.13 / 최신 결정 D-014. 단계 게이트 정의는
[`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md) §15 참고.

새로운 LLM 모델이나 CBBA 알고리즘을 제안하는 연구가 아니다. 검증된 구성요소를 통합하고
재현 가능하게 시연·평가한다.
