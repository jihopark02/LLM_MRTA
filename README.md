# LLM_MRTA

LLM-Based Disaster Mission Decomposition and CBBA Task Allocation for Heterogeneous
Unmanned Systems

학부 학술대회 발표용 독립 연구 프로젝트. `/home/jiho/LLM_CBBA`와 Git 이력·연구 계약을
공유하지 않는다.

- 연구 계약 (단일 진실 원천): [`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md)
- 설계 결정 이력: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- 이식 코드 등록부: [`docs/PROVENANCE.md`](docs/PROVENANCE.md)

## 현재 단계

**P1 승인. P2 구현 완료**(Codex 검토 2회 반영, 재검토 대기) — `validator/`에 deterministic
whole-graph Validator(§9 invariant #1~14)와 MissionPatch apply/reconciliation(§10, 트랜잭션
+ 다중 트랜잭션 우회 방지). 테스트 103개 통과(`python3 -m pytest -q`). 다음은 P3(platform-aware
CBBA, §11).

계약 버전 v1.6 / 최신 결정 D-007. 단계 게이트 정의는
[`docs/RESEARCH_CONTRACT.md`](docs/RESEARCH_CONTRACT.md) §15 참고.

새로운 LLM 모델이나 CBBA 알고리즘을 제안하는 연구가 아니다. 검증된 구성요소를 통합하고
재현 가능하게 시연·평가한다.
