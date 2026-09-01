# LLM_MRTA

LLM-Based Disaster Mission Decomposition and CBBA Task Allocation for Heterogeneous
Unmanned Systems

학부 학술대회 발표용 독립 연구 프로젝트. `/home/jiho/LLM_CBBA`와 Git 이력·연구 계약을
공유하지 않는다.

- 연구 계약 (단일 진실 원천): [`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md)
- 설계 결정 이력: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- 이식 코드 등록부: [`docs/PROVENANCE.md`](docs/PROVENANCE.md)

## 현재 단계

**P1·P2 승인. P3 구현 완료**(Codex 검토 대기) — `validator/`(P2: whole-graph Validator §9,
MissionPatch §10) + `allocation/`(P3: platform-aware travel §8, CBBA scoring/epoch §11,
rolling READY-frontier allocation + §13 지표). 테스트 155개 통과(`python3 -m pytest -q`).
P3 게이트 통과(reference fixture 12/12 할당, capability/precedence violation 0, UGV 이동거리
= route Dijkstra). 다음은 P4(2D executor, end-to-end).

계약 버전 v1.8 / 최신 결정 D-009. 단계 게이트 정의는
[`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md) §15 참고.

새로운 LLM 모델이나 CBBA 알고리즘을 제안하는 연구가 아니다. 검증된 구성요소를 통합하고
재현 가능하게 시연·평가한다.
