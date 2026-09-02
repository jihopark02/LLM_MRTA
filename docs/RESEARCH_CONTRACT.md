# RESEARCH_CONTRACT.md — 단일 진실 원천

버전 v1.23 (D-025). 이 문서와 코드가 충돌하면 이 문서가 우선한다. 변경 시 이 문서를 먼저 고치고
`docs/DECISIONS.md`에 이유를 append한다.

- v1.0 (D-001): 초판.
- v1.1 (D-002): §15 P1 완료 게이트를 P1 구현 범위 전체를 검사하도록 강화하고, reference
  fixture의 고정 형상(task 12 / edge 6 / 초기 READY 6)을 §3에 명시.
- v1.2 (D-003): §7에 compiler 입력 경계(신뢰된 목록만; raw candidate는 Validator 선행)를
  명시. §6의 enum 직렬화 서술을 정정(`safe_dump` 불가, 경계에서 `.value`). incident
  `status: RESPONSE_REQUIRED`를 scene 데이터 필수 필드로 명시(§3).
- v1.3 (D-004): §8의 `travel_time` 예시를 `scene.agent_access_nodes` 기반으로 정정(core
  Agent에 `access_node` 없음). §8에 scene 로드 시점 검증 4종(incident access_node 존재,
  UGV 시작 node 존재, UGV task 도달성, `agent_id` 유일)을 명시.
- v1.4 (D-005): §10의 "operation 순서 무관" 주장을 정정 — diff reconciliation은 순서
  독립성을 보장하지 않는다. patch raw op 목록 self-일관성 검증(`E_PATCH_CONFLICT`) + canonical
  적용 순서(`AddTask → RemoveEdge → AddEdge`)를 추가. CANCELLED predecessor의 frontier
  의미를 P4로 명시 유보.
- v1.5 (D-006): §10에 reconciliation release 경로(ASSIGNED release / E_RUNNING_LOCKED /
  terminal outgoing 재배선)가 RQ3(P8) 전에는 end-to-end로 도달하지 않음을 명시(고정 5종
  어휘 + §9 #10의 결과). P2는 이를 단위테스트로 검증한다.
- v1.6 (D-007): §10에 assignment consistency invariant(§10 7단계) 명시. §7에 schema
  검증이 허용 키를 정확히 제한함을 명시(`E_SCHEMA`). graph_hash payload에 `priority` 포함,
  MissionPatch operation의 필드 schema를 런타임 검증(둘 다 P2 Codex 2차 지적).
- v1.7 (D-008): §7 `priority` 범위를 1..10으로 고정(`E_SCHEMA`). §10 assignment invariant에
  참조 무결성(규칙 6) 추가. §14에 `validator_version` bump 규칙과 rejected patch `graph_hash`
  범위 명시(P2 Codex 3차 지적).
- v1.8 (D-009): §11에 `λ = 0.999` 고정, 보상은 스케일 없는 `priority`, tie-break는 정확히
  같은 bid에서 `agent_id`→`task_id` 사전순, `bundle` 무제한을 명시(P3 구현).
- v1.9 (D-010): P3 Codex 검토 반영 — §13에 plan-time topological-wave barrier 모델(READY
  이전 이동 금지, utilization busy = travel+dwell만), §11에 tie-break를 `1e-9` 허용오차로
  명시(정확 상등 아님), §11·§10에 bundle/path 관계를 CBBA postcondition으로 확정.
- v1.10 (D-011): §11에 rolling epoch의 `held` commitment(미완료 할당은 재경매 안 함) +
  task lifecycle(ASSIGNED→RUNNING→COMPLETED) 명시, §14에 P4 구현체 `SimExecutor`의
  deadlock 판정 절차 명시(P4 구현).
- v1.11 (D-012): P4 Codex 검토 반영 — §14에 종료 사유 분리(`COMPLETED`/`DEADLOCK`/
  `STEP_LIMIT`), 실행 중 epoch 입찰의 residual-path 규칙, COMPLETED 시 assignment 정리
  명시. §10에 cancellation을 P1~P7 미지원·P8 유보로 확정.
- v1.12 (D-013): P4 Codex 재검토 — §11에 rolling epoch의 `availability_delay`(실행 중
  agent의 남은 시간)를 입찰 누적 시작값으로 명시, §14에 마지막 step 완주 시 `COMPLETED`
  판정 + precedence violation을 `task_departure` 기준으로 판정. availability-aware 후
  reference mission workload가 다시 균형(D-012의 "집중이 정상" 서술 철회).
- v1.13 (D-014): §14에 `STEP_LIMIT` 실행의 `makespan`/`agent_utilization`은 평가 지표로
  쓰지 않음을 명시(busy는 dispatch 시 예정치를 더하므로 미완 실행에서 util > 1 가능;
  `agent_utilization`은 빈 dict 반환).
- v1.14 (D-015): §14의 `patch_hash` 정리를 "P5 전"에서 "P8로 유보"로 변경 — MissionPatch는
  P5 candidate 검증에 쓰이지 않고 RQ3(P8)에서 실제 사용되므로 P8 문서 개정 시 확정.
- v1.15 (D-016): **task 어휘 변경** — `HAZARD_MARKER_DEPLOY` → `GROUND_SUPPRESSION`(symbolic),
  `Capability.MARKER_DISPENSER` → `SUPPRESSANT_APPLICATOR`, "Safety UGV" → "Ground Response
  UGV"(ID G1/G2 유지). §2·§3·§4·§5·§7·§9 #12·§15 P1 게이트 개정. `VALIDATOR_VERSION`
  1.1 → 1.2. reference fixture의 GROUND_SUPPRESSION priority = incident priority(F1 9 / F2 7).
  P3/P4 골든값 재산출.
- v1.16 (D-017): §12에 LLM 파이프라인 구현 명시 — `generate_mission`, pydantic 구조화
  출력, `LLMBackend` Protocol, `GenerationResult` 지표, `failure_category` 집합, schema
  오류는 즉시 명시적 거부.
- v1.17 (D-018): 실제 LLM backend를 OpenAI로 확정 — `OpenAIBackend`(`chat.completions.parse`,
  `OPENAI_API_KEY`, 선택적 repo-root `.env`). 평가 모델은 `gpt-5-mini`로 pin(reasoning
  model → `temperature` 미전달)하고 결과 표에 기록(§14). `llm` extra는 `openai`.
- v1.18 (D-019): P5 Codex 검토 반영 — §12에 Step 1→Step 2 순서 강제(Step 1이 schema
  통과 전에는 Step 2 호출 안 함), pydantic schema `extra="forbid"`+`strict=True` 명시,
  backend의 `ValidationError`를 명시적 SCHEMA 거부로 변환, `raw_candidate`/`raw_validation`과
  최종 `candidate`/`validation`을 분리 보존 명시.
- v1.19 (D-020): §12에 prompt task glossary(의미+담당 platform) 포함을 명시 — P6 결과가
  task 이름의 영어 의미 추측 능력이 아니라 임무 분해 능력을 재도록.
- v1.23 (D-025): §15에 P6.5(얇은 통합 runner) 게이트 추가 — NL 명령을
  `generate_mission` → `allocate` → `SimExecutor`로 관통시켜 RQ1(P6)과 RQ2(P3/P4)가
  실제로 연결됨을 대표 명령 1~3개로 시연. 새 알고리즘·계약 무결성 규칙 변경 없음.
- v1.22 (D-023): P6 재검토 반영. §7 — incident `priority` 1..10 강제를 **scene loader**로
  이동(D-022는 compiler 파생만 명시해 scene 입력 경계가 비어 있었음 — `int()` 강제 변환으로
  잘못된 값이 Validator를 통과 후 compile에서 크래시). D-022 본문의 "annotation 명시형
  schema에 int·범위 검사 복원" 서술 정정 — annotation도 `{task_type, target}`만 허용하고
  priority 키를 거부한다. 문서: `python` → `python3` 통일, `core/task.py`·`CLAUDE.md` 옛
  LLM schema 서술 갱신. VALIDATOR_VERSION 불변(scene load 경계, 판정 규칙 아님).
- v1.21 (D-022): P6 Codex 검토 반영. §7 — LLM 출력에서 `priority` 제거, task entry는
  `{task_type, target}`; `derive_priority`(incident → incident.priority, AREA_RECON →
  상수 4)가 파생. §1 RQ1을 "구조 생성"으로 재서술. §9 — candidate 경로는 invariant
  #1~#12만("14개" 서술 금지), #13~#14는 patch 전용. §14 `VALIDATOR_VERSION` 1.2 → 1.3.
  §12 — 결과 JSON에 raw·final 후보 내용·graph_hash·error_codes 저장(감사, 축소 금지),
  `X/N` 동적 분모, family B edge P/R은 N/A, repair attempted/recovered 분리,
  하네스 예외는 `harness_error`로 분리. 감사 필드 추가 후 9개 라이브 재실행.
- v1.20 (D-021): §12에 P6 평가 하네스 설계 고정 — reference annotation 파일 형식/위치
  (`data/reference_annotations/<id>.yaml`, LLM 첫 호출 전 커밋), `task_key=(task_type,target)`
  기준 비교, `allowed_graphs` 중 (task F1, edge F1) 최대인 것과 대조, raw·final 후보 둘 다
  측정, `X/9` 집계 + family 분해 + 재현성 필드(scene_hash/validator_version/resolved_models).

이 프로젝트는 `/home/jiho/LLM_CBBA`(이하 "이전 저장소")와 Git 이력을 공유하지 않는 독립
연구다. 이전 저장소의 earthquake/vehicle-inspection/fire-patrol 연구 계약, D-xxx 결정, task
어휘, UAV 전용 dataclass, domain invariant, prompt, scenario, world, 골든값은 이 프로젝트의
근거로 쓰지 않는다. 이전 저장소에서 재사용하는 것은 알고리즘 패턴뿐이며, 재사용할 때마다
`docs/PROVENANCE.md`에 원본 경로·커밋·재사용 이유를 기록한다.

---

## 0. 제목과 성격

국문: LLM 기반 복합 재난 임무 분해 및 CBBA 이종 무인체계 임무 할당
영문: LLM-Based Disaster Mission Decomposition and CBBA Task Allocation for Heterogeneous
Unmanned Systems

새로운 LLM 모델이나 CBBA 알고리즘을 제안하는 연구가 아니다. 검증된 구성요소(LLM structured
output, CBBA, 결정론적 Validator)를 통합하고 재현 가능하게 시연·평가하는 연구다.

---

## 1. 연구 질문

**RQ1 (필수)**: LLM이 고수준 복합 재난 대응 명령과 semantic scene으로부터 실행 가능한 task
graph의 **구조**(어떤 task_type을 어떤 target에, 그리고 task 간 dependency edge)를 생성할 수
있는가? 좌표·priority·capability·duration은 LLM이 만들지 않고 결정론적 compiler가 semantic
scene과 고정 매핑에서 resolve한다(§7) — RQ1은 그 구조 생성 능력을 §12 지표로 측정한다.

**RQ2 (필수)**: 결정론적으로 검증된 task graph를 CBBA가 UAV/UGV의 capability와 플랫폼별
이동비용을 고려하여 이종 무인체계에 실행 가능하게 할당할 수 있는가?

**RQ3 (후속, 선택)**: 임무 실행 중 자연어 상황 보고로 기존 graph에 신규 prerequisite가 추가될
때, 전체 재생성 없이 증분 수정하고 영향받은 commitment만 선택적으로 재할당할 수 있는가?

RQ3는 RQ1/RQ2의 모든 통과 조건이 충족되고 발표 가능한 정량 결과·시각화가 확보된 이후에만
착수한다(P8). RQ3를 구현하지 못해도 실패로 간주하지 않으며, 후속 연구로 명시한다. RQ3가
구현되기 전에는 제목·초록·결론·발표자료 어디에도 "동적 재할당" 또는 "dynamic reallocation"을
완료된 결과로 주장하지 않는다.

---

## 2. MP4MR과의 관계

참고 논문: 김연주 외, "임무 계획 자율화를 위한 LLM 기반 임무 분할 및 생성 기법" (J. ICROS
2025, 한국항공대+LIG넥스원). 이 논문의 구조(고수준 자연어 → LLM Task Generator → Critic 검증
→ BP 기반 이종 UAV/UGV 할당 → ROS2/Gazebo 시연)를 구조적으로 참고한다. 원문 재확인 완료:
Actor 1~4 단계, Critic 2/3/4a(feasibility)/4b(grammar), task 11종(표3), 실시간 피드백·동적
갱신 미구현·후속과제 명시 — 전부 확인됨.

**그대로 복제하지 않는 것**: WATER_LOAD, OBSTACLE_CLEAR, RELAY_DEPLOY, TARGET_TRACK,
인명·물자 적재/하적, MP4MR의 A~G 체계 분류. 새 시나리오는 "MP4MR-inspired"로 명시한다.

**GROUND_SUPPRESSION에 대하여(D-016)**: §4의 `GROUND_SUPPRESSION`은 지상 무인체계가 incident
접근 지점에서 수행하는 **symbolic task**다 — 위치 도달 + dwell로만 완료를 판정하고, 물리적
소화 성공이나 소화 소요시간을 산출하거나 주장하지 않는다(`SUPPRESSANT_DROP`과 같은 성격).
MP4MR의 UGV suppression과 유사한 단계가 있으나, 이 연구의 독창성 주장은 task 어휘가 아니라
**결정론적 whole-graph Validator + CBBA 축**에 둔다(아래 "핵심 차별점"). task 어휘 변경만으로
독창성을 주장하지 않는다.

**핵심 차별점**: LLM이 생성한 임무 그래프의 실현 가능성과 도메인 제약을, 또 다른 LLM Critic
호출이 아니라 **결정론적 whole-graph Validator**로 검증한다. 동일한 후보 그래프에는 항상
동일한 검증 결과가 나오며, 검증을 통과한 그래프만 CBBA와 simulator에 전달한다. MP4MR보다
우수하다고 주장하려면 동일 조건의 직접 비교가 필요하므로, 이 연구에서는 구조적 차이와
재현성 특성만 설명하고 우열을 주장하지 않는다. CBBA와 BP의 비교도 마찬가지로 주장하지 않는다.
task 명칭 변경이나 BP→CBBA 교체만으로 독창성을 주장하지 않는다 — 그 자체는 부차적 차이다.

---

## 3. 시나리오

약 200~250m 규모의 가상 산업단지 화재 대응 환경.

**구역**: ZONE_A(Warehouse), ZONE_B(Processing Area), ZONE_C(Utility Yard), ZONE_D(Tank
Farm).

**incident**: FIRE_SITE_1(ZONE_B, priority 9), FIRE_SITE_2(ZONE_D, priority 7). 초기 상태
`RESPONSE_REQUIRED` — reference scene에서 이미 대응이 필요한 것으로 주어지며, LLM이나 agent가
화재 여부를 판정하지 않는다. False alarm과 perception 기반 조건부 graph는 범위 밖이다. 이
`status`는 주석이 아니라 scene 데이터의 필수 필드로 명시하고 loader가 검증한다(`IncidentStatus`).

화재 위치·상태는 semantic scene 또는 운용자·외부 시스템 보고로만 시스템에 진입한다. 실제
영상 분석, 화재 탐지, 화재 안정성 판정은 구현하지 않는다. Task 완료는 위치 도달과 dwell
time으로만 판정한다.

**reference fixture 고정 형상** (P1~P4에서 쓰는 canonical full-response graph, §12 Family A에
대응). 이 값은 게이트 기준이며 LLM이 개입하기 전까지 사람이 손으로 고정한다:

| 항목 | 값 | 구성 |
|---|---|---|
| task | 12 | `AREA_RECON` 4 (ZONE_A~D) + incident workflow 4단계 × incident 2 = 8 |
| edge | 6 | incident 체인당 3 (§4 workflow) × incident 2 |
| 초기 READY | 6 | predecessor 없는 task = `AREA_RECON` 4 + `THERMAL_RECON` 2 |
| 초기 PENDING | 6 | `SUPPRESSANT_DROP` 2 + `GROUND_INSPECTION` 2 + `GROUND_SUPPRESSION` 2 |

READY/PENDING은 fixture YAML에 적지 않고 graph의 predecessor 상태에서 계산한다(§7, §9).

---

## 4. Task vocabulary

5종으로 고정한다. 추가 제안은 하지 않는다.

| task_type | 의미 | 완료 조건 |
|---|---|---|
| `AREA_RECON` | Scout UAV가 지정 구역을 정찰 | 위치 도달 + dwell |
| `THERMAL_RECON` | 이미 보고된 incident 위치에 UAV가 접근해 대응 전 열원 확인 절차를 수행하는 symbolic task. 열분포 지도, 새 좌표, 센서 데이터를 산출하지 않는다 | 위치 도달 + dwell |
| `SUPPRESSANT_DROP` | Response UAV가 사전 탑재한 대응 payload를 투하. 완료는 물리적 화재 진압 성공을 의미하지 않는다 | 위치 도달 + dwell |
| `GROUND_INSPECTION` | SUPPRESSANT_DROP workflow 완료 후 Ground Response UGV가 incident 접근 지점으로 이동해 지상 상태 점검 | 위치 도달 + dwell |
| `GROUND_SUPPRESSION` | GROUND_INSPECTION 완료 후 Ground Response UGV가 incident 접근 지점에서 지상 진압을 수행하는 symbolic task. 완료는 물리적 소화 성공·소화 소요시간을 의미하지 않는다(D-016) | 위치 도달 + dwell |

`THERMAL_RECON`을 `THERMAL_MAPPING`으로 부르지 않는다 — "mapping"은 위치를 도출하는 것처럼
들리는데 실제로는 아무 데이터도 산출하지 않는다.

**정적 incident workflow** (Phase 1, 조건부 규칙 — 아래 항상 강제되는 게 아님에 주의):

```
THERMAL_RECON → SUPPRESSANT_DROP → GROUND_INSPECTION → GROUND_SUPPRESSION
```

이 규칙은 "downstream task가 **존재하면** 같은 incident의 올바른 predecessor가 필요하다"는
조건부 규칙이지, "모든 incident가 반드시 4단계를 전부 생성해야 한다"는 강제가 아니다. 어떤
NL 명령이 THERMAL_RECON까지만 요청했다면 그 부분 graph도 구조적으로 유효하다. "이 부분
graph가 의도된 것인지 덜 만들어진 것인지"는 Validator의 역할이 아니라 §12 평가 하네스의
mission profile로 별도 판정한다(§9 참고).

`AREA_RECON`은 이 incident 대응 chain의 predecessor가 아니다 — 구역 정찰은 독립적으로
수행한다.

**dwell duration은 symbolic scenario parameter다**(D-016): 각 task_type마다 하나의 고정값을
`TASK_TABLE`에 두며, 물리적 소요시간(비행시간·소화시간 등)이라고 주장하지 않는다.
`GROUND_SUPPRESSION`의 duration도 마찬가지로 하나로 고정한다.

---

## 5. Agent 구성

총 6대, 2/2/2 고정.

| Agent | 대수 | capability |
|---|---|---|
| Scout UAV (S1, S2) | 2 | `AERIAL_RECON`, `THERMAL_SENSOR` |
| Response UAV (R1, R2) | 2 | `THERMAL_SENSOR`, `SUPPRESSANT_PAYLOAD` |
| Ground Response UGV (G1, G2) | 2 | `GROUND_MOBILITY`, `SUPPRESSANT_APPLICATOR` |

Task별 eligible bidder: `AREA_RECON`=Scout 2, `THERMAL_RECON`=Scout+Response 4,
`SUPPRESSANT_DROP`=Response 2, `GROUND_INSPECTION`=Ground Response UGV 2,
`GROUND_SUPPRESSION`=Ground Response UGV 2. 모든 task type에 eligible bidder ≥2 — UGV 전용
task에서도 CBBA가 G1/G2 중 winner를 결정한다.

Response UAV의 payload는 사전 탑재된 것으로 가정한다. `WATER_LOAD`, suppressant 잔량·재보급,
same-agent resource coupling은 구현하지 않는다.

**모든 agent가 반드시 하나 이상의 task를 받아야 한다는 제약은 두지 않는다.** 대기하는 것도
비용상 합리적인 결과일 수 있다. 대신 다음을 측정한다: agent utilization, idle-agent count,
workload distribution, task별 eligible bidder 수, Response UAV의 실제 참여 여부. Response
UAV가 계속 유휴 상태라면 이는 즉시 실패가 아니라 capability 구성·bid 가중치·task 수가 의도한
이종 할당 실험을 만드는지 재검토할 근거로 취급한다.

---

## 6. Generic Agent 모델

이전 저장소의 `UAV` dataclass를 복사하지 않는다. PX4 전용 필드(`mpc_xy_vel_max` 등)를 core
model에 넣지 않는다.

아래 코드는 예시다. `StrEnum`은 Python 3.11+ 전용이므로, 3.10 환경에서는 `class X(str, Enum)`
패턴으로 구현한다. 이 경우 enum 값이 bare string과 `==` 비교되므로 YAML **읽기**는 커스텀
loader가 필요없다. 단 `yaml.safe_dump`는 이 값을 직렬화하지 못하므로(RepresenterError),
직렬화가 필요한 경계에서는 항상 `member.value`를 쓴다.

```python
class PlatformKind(StrEnum):
    UAV = "UAV"
    UGV = "UGV"

class Capability(StrEnum):
    AERIAL_RECON = "AERIAL_RECON"
    THERMAL_SENSOR = "THERMAL_SENSOR"
    SUPPRESSANT_PAYLOAD = "SUPPRESSANT_PAYLOAD"
    GROUND_MOBILITY = "GROUND_MOBILITY"
    SUPPRESSANT_APPLICATOR = "SUPPRESSANT_APPLICATOR"

@dataclass(slots=True)
class Agent:
    agent_id: str
    platform_kind: PlatformKind
    capabilities: frozenset[Capability]
    initial_position: tuple[float, float]
    position: tuple[float, float]
    speed: float
    bundle: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)
    current_task: str | None = None
```

플랫폼 전용 설정(PX4 velocity parameter, Gazebo model, UGV route node, differential-drive
parameter)은 core `Agent`가 아니라 별도 platform adapter(`execution/px4_adapter.py`,
`execution/ugv_adapter.py`, P7에서 실제 구현)에 둔다.

---

## 7. Task 데이터 모델

```python
@dataclass(slots=True)
class Task:
    task_id: str
    task_type: TaskType
    target: str                                   # area_id 또는 incident_id
    position: tuple[float, float]
    priority: int                                 # 1..10 (D-008), 클수록 우선
    required_capabilities: frozenset[Capability]   # 복수 — 예: GROUND_SUPPRESSION은 GROUND_MOBILITY+SUPPRESSANT_APPLICATOR 둘 다 필요
    eligible_platforms: frozenset[PlatformKind]
    duration: float
    status: TaskStatus
    assigned_agent: str | None = None
```

**LLM은 `position`, `priority`, `required_capabilities`, `duration`, `eligible_platforms`,
`task_id`를 직접 생성하지 않는다(D-022).** LLM 출력은 `task_type` + `target`(landmark/incident
참조)만 포함한다. 나머지는 결정론적 compiler가 semantic scene과 기본 매핑 테이블에서
resolve한다. LLM이 좌표나 priority를 직접 생성하면 semantic scene과 이중 진실 원천이 생긴다.
schema 검증(§9 #1)은 이를 강제한다 — top-level 키는 정확히 `{tasks, edges}`, task entry
키는 정확히 `{task_type, target}`여야 하며, 그 외 키(`priority`, `assigned_agent` 등)가
있으면 `E_SCHEMA`로 거부한다.

**priority 파생 규칙(D-022)**: compiler(`scenarios/compiler.py`의 `derive_priority`)가
결정한다.
- incident를 target으로 하는 task(`THERMAL_RECON`/`SUPPRESSANT_DROP`/`GROUND_INSPECTION`/
  `GROUND_SUPPRESSION`) → 그 incident의 `priority`(§3: FIRE_SITE_1 = 9, FIRE_SITE_2 = 7).
- `AREA_RECON`(zone target) → 고정 상수 `AREA_RECON_PRIORITY = 4`. zone은 사건 심각도가
  없으므로 균일하며, 두 incident priority(7·9)보다 낮아 CBBA가 진행 중 사건 대응을 zone
  정찰보다 앞세운다.

incident priority의 진실 원천은 semantic scene이므로, **scene loader가 로드 시점에**
각 incident `priority`가 정수 **1..10**임을 강제한다(D-023 — bool·문자열 `int()` 강제
변환 없음). compiler는 scene을 신뢰하므로 이 검사가 없으면 Validator가 승인한 graph가
compile 단계에서 깨질 수 있다. `core/task.py`의 `Task.__post_init__`가 최종 방어선으로
같은 범위를 재확인한다(D-008 — CBBA 보상이 0·음수에서 음수 bid·미할당을 내지 않도록).
파생된 priority는 audit hash(§14 `graph_hash`)의 node payload에 포함된다.

MissionPatch(`AddTask`, §10)의 priority 처리는 RQ3(P8) 구현 시 같은 파생 규칙으로 정렬한다.
그때까지 `AddTask.priority`는 유지하되 end-to-end로 쓰이지 않는다(D-006).

`Task.status`는 YAML에 독립적으로 기록하지 않고 graph의 predecessor 상태로부터 계산한다
(§9의 whole-graph recompute).

**입력 경계**: 결정론적 compiler는 **신뢰된** task 목록만 받는다 — 손으로 작성한 reference
fixture, 그리고 §12 파이프라인에서 이미 whole-graph Validator를 통과한 LLM 출력. compiler는
구조적으로 깨진 입력(존재하지 않는 edge 끝점, 중복 edge)에 대해 조용히 버리지 않고 예외를
던진다. raw LLM candidate의 E_UNKNOWN_REF/E_DUPLICATE_EDGE 판정은 compile 이전에 Validator가
자체 candidate 표현 위에서 수행한다(§9, §12).

---

## 8. 이동비용

`agent.access_node`는 core `Agent`(§6)에 없다 — UGV 시작 node는 `scene.agent_access_nodes[agent_id]`로
조회한다.

```python
def travel_time(agent, target_pos, scene) -> float:
    if agent.platform_kind is PlatformKind.UAV:
        return math.dist(agent.position, target_pos) / agent.speed
    start = scene.agent_access_nodes[agent.agent_id]
    dist = scene.route_graph.shortest_path_distance(start, target_access_node(target_pos))
    if dist is None:
        raise UnreachableError(agent.agent_id, target_pos)
    return dist / agent.speed
```

- UAV: 2D 또는 3D Euclidean distance / speed.
- UGV: 사전 정의된 lane/waypoint graph의 Dijkstra 최단경로 거리 / speed. 임의 좌표를 직접
  Dijkstra에 넣지 않고, target마다 `access_node_id`를 scene에 명시한다.
- **scene 로드 시점 검증(전부 실패 시 시나리오 로드 거부)**: (a) 모든 incident의 `access_node`가
  route graph node로 존재, (b) 모든 UGV agent의 시작 node가 route graph node로 존재, (c) 모든
  UGV 대상 task 위치가 route graph에서 모든 UGV 시작 node로부터 도달 가능, (d) `agent_id` 유일.
  (c)는 task 목록이 필요하므로 fixture/candidate 로드 시점에, (a)(b)(d)는 scene 로드 시점에
  검사한다. CBBA 입찰 단계까지 가지 않는다.
- 2D simulator와 향후 Gazebo가 동일한 route semantics를 공유해야 한다.

이 함수는 이전 저장소의 `travel_time()`을 그대로 이식하지 않고 `platform_kind` 분기를 새로
추가한 것이다 — §14 PROVENANCE 참고.

---

## 9. Deterministic Whole-Graph Validator

**주장 범위**: Validator는 LLM graph의 구조적·도메인적 실행 가능성을 결정론적으로 검증한다.
자연어 의미 충실도(사용자 명령에 필요한 task가 빠짐없이 생성됐는가)는 코드만으로 판정할 수
없으므로 Validator의 역할이 아니다 — 이건 §12에서 task/edge precision·recall로 별도 평가한다.
"결정론적 Validator가 LLM graph의 정확성을 보장한다"는 과장된 주장을 하지 않는다.

**mission profile**: `FULL_RESPONSE`/`AERIAL_ONLY`/`SELECTIVE_RESPONSE`는 런타임 Validator가
아니라 §12 평가 하네스의 개념이다. 실험 입력별 expected profile을 LLM 출력을 보기 전에
고정하고, 그 profile에 맞는 reference annotation과 대조해 recall을 측정한다. 런타임
Validator는 이 두 출력을 구별하지 못한다: (a) 의도적으로 THERMAL_RECON까지만 생성한
aerial-only 임무, (b) full-response 명령인데 나머지 task를 누락한 불완전 임무. 둘 다 구조적으로
유효하면 Validator는 승인한다 — 이 한계는 §12의 recall 지표로 측정한다.

**invariant 목록**:

| # | 검사 | 범위 | 오류코드 |
|---|---|---|---|
| 1 | schema 유효성 | patch 전체 | E_SCHEMA |
| 2 | task_id 유일 | 전체 graph | E_DUPLICATE_ID |
| 3 | task_type ∈ 허용집합(5종) | task별 | E_TYPE_NOT_ALLOWED |
| 4 | target이 존재하는 area/incident 참조 | task별 | E_UNKNOWN_REF |
| 5 | edge 양끝이 존재하는 task 참조 | edge별 | E_UNKNOWN_REF |
| 6 | self-loop 금지 | edge별 | E_SELF_LOOP |
| 7 | 중복 edge 금지 | 전체 graph | E_DUPLICATE_EDGE |
| 8 | DAG(비순환) | 전체 graph | E_CYCLE |
| 9 | capability 충족 agent 존재(≥1) | task별 | E_INFEASIBLE |
| 10 | incident workflow: downstream이 존재하면 같은 incident의 정확히 그 predecessor 타입을 정확히 1개 가짐(조건부, §4 참고) | incident 체인별 | E_WORKFLOW |
| 11 | cross-incident edge 금지 | workflow edge별 | E_CROSS_INCIDENT |
| 12 | UGV 대상 task 위치가 route graph에서 도달 가능 | GROUND_INSPECTION/GROUND_SUPPRESSION | E_UNREACHABLE |
| 13 | **종결(COMPLETED/CANCELLED) task는 상태·결과·target·incoming edge가 불변. 단, 아직 RUNNING이 아닌 successor를 향한 outgoing edge는 같은 atomic patch 안에서 유효한 workflow로 재배선할 수 있다** | 전체 | E_TERMINAL_IMMUTABLE |
| 14 | patch 거부 시 원본 완전 보존(트랜잭션) | patch 전체 | (부분 commit 없음) |

이 표는 **최종 후보 graph** 위에서 도는 whole-graph Validator다. patch의 raw operation 목록
self-일관성 검사(중복 op, 같은 edge Add+Remove 등, 오류코드 `E_PATCH_CONFLICT`)는 이 검증
이전 단계이며 §10 처리 절차 2단계에서 별도로 수행한다.

**적용 범위**: §12 LLM candidate 경로(P5/P6)가 받는 검사는 **#1~#12**다(그중 #1은 candidate
schema — top-level `{tasks, edges}`, task entry `{task_type, target}`). **#13~#14는
MissionPatch 경로 전용**이며 RQ3(P8) 전에는 end-to-end로 도달하지 않는다(D-006). "승인된
candidate graph가 14개 invariant를 만족한다"고 서술하지 않는다 — "#1~#12를 만족한다".

**#13은 RQ3(P8)를 염두에 둔 것**: "화재 재발 위험 보고" 시나리오는 `SUPPRESSANT_DROP_F2`(이미
COMPLETED)의 outgoing edge를 `GROUND_INSPECTION_F2`에서 신규 `THERMAL_RECHECK_F2`로 재배선해야
한다. #13이 outgoing edge까지 불변으로 두면 이 재배선 자체가 구조적으로 불가능해진다.

**멀티 트랜잭션 우회 테스트 필수**: invariant는 단일 patch뿐 아니라 여러 patch에 걸친 edge
추가·삭제 시퀀스로도 테스트한다(이전 저장소 D-079에서 실제로 겪은 교훈: 검사 대상을 그
transaction에서 새로 생긴 것으로 한정하면, 다른 종류의 patch로 기존에 이미 검증된 것을
나중에 깨는 우회가 가능해진다 — 매 patch마다 최종 후보 graph 전체를 처음부터 다시 검사해야
막힌다).

---

## 10. MissionPatch와 diff 기반 reconciliation

**operation**: `AddTask`, `RemoveEdge`, `AddEdge` 세 가지로 고정한다. `ReleaseAssignment`
같은 명시적 release operation은 만들지 않는다.

**처리 절차**:

1. 현재 `MissionState`를 clone한다.
2. **raw operation 목록을 self-일관성 검증한다** (D-005). 이 검사는 operation을 TaskGraph에
   넣기 전에 raw 목록(list) 위에서 한다 — set/graph에 들어가면 중복 정보가 사라진다.
   - 각 operation의 schema 유효성 (E_SCHEMA)
   - 같은 `task_id`에 대한 AddTask ≥2 (E_PATCH_CONFLICT)
   - 같은 edge에 대한 AddEdge ≥2, 또는 RemoveEdge ≥2 (E_PATCH_CONFLICT)
   - 같은 edge를 한 patch에서 AddEdge와 RemoveEdge 둘 다 (E_PATCH_CONFLICT)
   - 원본에도 없고 이 patch의 AddEdge도 아닌 edge에 대한 RemoveEdge (E_PATCH_CONFLICT)
3. 검증을 통과하면 canonical 순서 **`AddTask → RemoveEdge → AddEdge`**로 clone에 적용한다.
   2단계에서 self-충돌·중복을 제거했으므로 최종 후보 graph는 operation 나열 순서와 무관하게
   유일하다. (diff 기반 reconciliation은 lifecycle 부수효과만 정리할 뿐 최종 graph 자체의
   순서 의존성은 없애지 못한다 — 순서 독립성은 2·3단계가 보장한다.)
4. 최종 후보 graph 전체를 §9 invariant로 검증한다.
5. **원본 graph와 최종 candidate graph의 predecessor-set diff를 계산한다** — patch 도중의
   중간 상태가 아니라 시작과 끝만 비교한다. (서로 다른 edge를 제거·추가하는 RQ3 재배선에서
   중간 상태가 불필요한 release를 유발하지 않게 하려는 것이 "AddEdge 시점 즉시 release" 대신
   diff 기반을 쓰는 이유다.)
6. diff로 predecessor 집합이 바뀐 task에 대해 lifecycle/assignment를 reconciliation한다:
   - PENDING(새 unmet predecessor 추가): 그대로 PENDING
   - READY → PENDING
   - ASSIGNED → PENDING, assignment/bundle/path/winner-bid 기록 제거
   - RUNNING: **patch 전체를 거부**(이번 범위에서 RUNNING task의 predecessor 변경은 지원하지
     않음 — abort는 executor handshake까지 설계해야 하는 후속 과제)
   - COMPLETED/CANCELLED: 그 task 자신의 상태·결과·target·incoming이 바뀌는 diff면 거부;
     outgoing만 바뀌는 diff는 §9 #13에 따라 허용
   - predecessor 제거로 모든 조건이 충족된 PENDING: READY로 재계산. **frontier 계산은
     COMPLETED predecessor만 "충족"으로 취급한다**(D-012 확정): P1~P7에서 cancellation은
     지원하지 않으며 RQ3(P8)로 유보한다. 만약 CANCELLED predecessor가 존재하면 그 successor는
     영원히 blocked로 남고 executor는 이를 deadlock으로 보고한다 — 이게 의도된 현재 의미다.
     P8에서 cancellation을 도입할 때 cascade cancel vs blocked를 이 문서 개정으로 확정한다.
7. reconciliation 결과에 대해 state/assignment invariant를 재검사한다.
8. 유효하면 patch 전체를 commit, 아니면 전체 rollback한다. 중간 상태는 절대 외부에 노출하거나
   실행하지 않는다.

**reconciliation release 경로의 도달성(D-006)**: 고정 5종 task 어휘 + 엄격한 §9 #10 하에서는
어떤 **유효한** patch도 기존 task의 predecessor 집합을 바꾸지 못한다(workflow task는 항상
정확히 canonical predecessor 1개를 가져야 하므로). 따라서 6단계의 ASSIGNED→PENDING release,
E_RUNNING_LOCKED, terminal outgoing 재배선은 구현·단위테스트하되, RQ3(P8)가 recheck 계열
task를 도입하기 전에는 end-to-end로 도달하지 않는다. #13의 terminal incoming 불변은 P2에서
도달 가능하다.

**assignment consistency invariant(§10 7단계, D-007)**: MissionState가 commit될 때마다 검사한다.

1. `task.assigned_agent`가 설정돼 있으면 그 값은 fleet에 존재하는 agent다.
2. task가 `ASSIGNED` 또는 `RUNNING` ⟺ `assigned_agent`가 설정됨.
3. `ASSIGNED`/`RUNNING` task는 정확히 한 agent의 `bundle ∪ path`에 나타나고, 그 agent가
   `assigned_agent`다.
4. `PENDING`/`READY`/`COMPLETED`/`CANCELLED` task는 어떤 agent의 `bundle`/`path`에도 없고
   `winning_bids`에도 없다.
5. `bundle`/`path`의 세부 관계는 §11의 CBBA postcondition(D-010)으로 확정했다 — Validator
   invariant는 아니므로 여기서 `E_SCHEMA`로 강제하지 않는다. P2는 위 1~4만 강제한다.

6. **참조 무결성(D-008)**: 모든 `bundle`/`path` task_id와 모든 `winning_bids` key는 graph에
   존재하는 task를 가리킨다. `state.agents`의 dict key는 해당 `Agent.agent_id`와 일치한다.

이 invariant를 어긴 상태를 만드는 patch는 `E_SCHEMA`로 거부한다(별도 stale-assignment
오류코드는 두지 않는다).

**PatchResult**: `accepted`, `added_tasks`, `added_edges`, `removed_edges`,
`directly_released_tasks`, `status_changes`, `rejection_errors`를 기록한다.
`directly_released_tasks`(안전을 위한 필수 release)와 §16의 B0~B3류 downstream suffix reset
(비교 전략의 선택)은 서로 다른 개념이며 섞지 않는다 — 전자는 Validator/reconciliation이
구조적으로 강제하는 것이고, 후자는 실험 전략이 그 위에 추가로 선택하는 것이다.

이 설계는 이전 저장소 fire-patrol에서 얻은 교훈("release를 caller가 깜빡하면 안 된다")은
재사용하지만, 구현 세부(AddEdge 즉시 부수효과, RUNNING 자동 abort)는 그대로 복사하지 않는다.

---

## 11. CBBA 할당 방식

**Rolling READY-frontier epoch**: CBBA는 매 scheduling epoch에서 현재 READY 상태인 task만
할당 대상으로 삼는다. PENDING task는 아직 입찰 대상이 아니다. dependency가 해제되어 새 task가
READY가 되면 새 epoch를 시작한다. (precedence-aware 선점 번들링은 구현 난도만 올리고 RQ1/RQ2
검증에 필요하지 않으므로 채택하지 않는다.)

이 방식에서 Response UAV가 초기에는 대기하다 `SUPPRESSANT_DROP`이 READY가 된 뒤 투입되는 것도
정상 동작이다.

**rolling epoch의 held commitment(D-011)**: 새 epoch는 아직 완료되지 않은 기존 할당을
`held`(task → winner, bid)로 넘겨받아 재경매하지 않는다. 이게 없으면 task가 하나씩 staggered
로 READY가 될 때마다 매 epoch를 빈 bundle로 다시 경매해서 같은 agent가 연달아 이기고, 다른
동종 agent가 계속 유휴 상태가 된다. task lifecycle은 `ASSIGNED`(경매 낙찰) → `RUNNING`(agent가
이동 시작) → `COMPLETED`(위치 도달 + dwell 완료, §3).

**Bid/score**:

```
PathUtility(path) = Σ priority(task_j) × λ^projected_completion_time(task_j)
bid = max_insertion[ PathUtility(path_with_candidate) − PathUtility(current_path) ]
```

`projected_completion_time`은 현재 agent 위치, 플랫폼별 이동시간(§8), 선행 task들의 dwell
duration, 후보 task duration을 누적한 값이다. **rolling epoch에서 아직 task를 실행 중인
agent는 남은 실행시간(`availability_delay = max(0, finish_at − now)`)을 누적 시작값으로
쓴다**(D-013) — 위치는 그 task의 도착 지점으로 투영하고, 실행 중인 task 자체는 residual
path에서 제외한다. P3 `allocate`는 모든 `availability_delay = 0`으로 기존 동작을 유지한다. `λ = 0.999`로 고정한다(D-009, 이전 저장소
`DEFAULT_LAMBDA` 재사용) — 모든 조건에서 동일하게 쓴다. `priority(task_j)`는 §7의 정수
1..10을 스케일 없이 그대로 쓴다(이전 저장소의 `10·priority`가 아님). 동점 처리(D-010):
두 bid의 차가 `1e-9` 이내면 동점으로 보고 `agent_id` 사전순으로 작은 쪽이 이긴다(그 다음
`task_id` 사전순). 부동소수점 안정성을 위해 정확한 상등이 아니라 이 허용오차를 쓴다 —
코드의 `EPSILON`과 동일해야 한다. `bundle` 길이에는 상한을 두지 않는다(§17).

**bundle / path 관계(D-010, CBBA postcondition — Validator invariant 아님)**: `bundle`은
bid 획득 순서, `path`는 실행 순서. epoch 수렴 후 둘은 중복 없는 **동일 task 집합**이다. 각
task는 최종 winner 한 명의 `bundle`/`path`에만 존재한다. P3 plan-time에서 `current_task`는
`None`이다. epoch 종료 후 `bundle`/`path`는 임시 산출물이며 전체 계획의 기준은
`AllocationResult.assignments`다.

이 보상형태(우선순위×이동시간 할인)는 새로 고안한 게 아니라 이전 저장소 CBBA의 검증된 보상
구조를 재사용한 것이다 — §14 PROVENANCE 참고. bundle/consensus/tie-break 핵심 로직만
재사용하고, 이동비용 계산은 §8처럼 platform-aware로 새로 작성한다.

CBBA를 새로운 알고리즘 기여로 표현하지 않는다.

---

## 12. LLM 파이프라인과 평가

**파이프라인**:

```
자연어 명령 → Step 1(task 목록: task_type/target만) → schema validation
→ Step 2(dependency edge 제안) → whole-graph Validator → 구조화 오류 기반 repair 최대 1회
→ 전체 재검증 → 승인 또는 명시적 거부(reference로 조용히 fallback하지 않음)
```

repair 후에도 실패하면 해당 mission을 명시적 실패로 집계한다.

**구현(D-017, D-018, D-019)**: `llm/pipeline.py`의 `generate_mission(command, scene, backend)`.
Step 1/2/repair는 pydantic 구조화 출력(`llm/schemas.py`)이고, backend는 `LLMBackend`
Protocol이다 — `OpenAIBackend`(`chat.completions.parse`, `OPENAI_API_KEY`, 평가 모델
`gpt-5-mini` 고정)와 `MockBackend`(스크립트 응답). P5 게이트 테스트는 전부 `MockBackend`로
돌아 네트워크·API 키가 필요없다. 실제 LLM 평가(P6)는 §14 재현성을 위해 모델을 결과와 함께
기록한다.

**순서 강제(D-019)**: Step 1 출력은 **Step 2를 호출하기 전에** 자체적으로 schema 검증한다
(task-only `MissionCandidate.from_raw` + 중복 id 검사). Step 1이 schema를 통과하지 못하면
Step 2 backend 호출 자체가 일어나지 않는다 — mock 테스트는 이 경우 backend 호출 횟수가
정확히 1임을 검증한다.

**schema는 정확히 제한한다(D-019)**: `llm/schemas.py`의 모든 pydantic 모델은
`model_config = ConfigDict(extra="forbid", strict=True)`를 쓴다. 모델이 허용 안 된 키를
내거나(`priority`, `position`, top-level `notes` 등) 타입을 벗어나면(`target=123` 등)
조용히 버리거나 강제 변환하지 않고 `pydantic.ValidationError`로 거부되어야 한다.

**backend 예외는 명시적 SCHEMA 거부로 변환한다(D-019)**: Step 1/2/repair 중 어느 backend
호출에서든 `pydantic.ValidationError`가 나면 파이프라인이 예외로 죽지 않고
`GenerationResult(approved=False, failure_category="SCHEMA")`를 반환한다. 네트워크·인증
오류 등 다른 예외는 그대로 전파한다(P6 평가 하네스가 별도로 기록·재시도한다).

**raw와 최종을 분리 보존한다(D-019, §16)**: `GenerationResult`는 `raw_candidate`/
`raw_validation`(repair 이전, Step 1+2 직후의 후보와 검증 결과)과 `candidate`/`validation`
(최종 — repair가 있었으면 그 결과, 없었으면 raw와 동일 객체)을 둘 다 갖는다.
`raw_schema_valid`/`raw_whole_graph_valid`는 항상 raw 기준이고, `repaired_schema_valid`/
`repaired_whole_graph_valid`는 repair를 실제로 시도했을 때만 값이 있고(`repaired=True`),
시도하지 않았으면 `None`이다. "raw output과 validated output 비교"(§16)는 이 필드들로 한다.
`failure_category` ∈ {SCHEMA, WORKFLOW, STRUCTURE, REFERENCE, FEASIBILITY, OTHER}. 승인된
candidate만 `compile_reference_graph`로 실행 graph화한다(D-003 경계).

**P6 평가 하네스(D-021)**: §12의 "P6 하네스 구현" 참고. 9개 명령의 목록·family·profile은
`docs/DECISIONS.md` D-021에 고정한다.

**prompt에 task glossary를 포함한다(D-020)**: `llm/prompts.py`의 scene facts는 task_type
이름·target 종류뿐 아니라 각 task의 의미와 담당 platform을 설명하는 glossary를 포함한다.
이게 없으면 P6 결과가 LLM의 임무 분해 능력이 아니라 task 이름의 영어 의미 추측 능력을 재는
꼴이 된다. `GROUND_INSPECTION`(점검)과 `GROUND_SUPPRESSION`(진압)처럼 이름이 비슷한 쌍은
특히 구분해 설명한다.

**평가**: 최소 9개 명령(family당 3개), 시간이 있으면 18개(family당 6개)로 확장.

- Family A(full industrial response): 전체 구역 정찰 + 두 incident 전체 workflow
- Family B(aerial-focused): AREA_RECON/THERMAL_RECON만 요청 — SUPPRESSANT_DROP/UGV task가
  생성되면 안 됨
- Family C(selective incident response): 특정 incident만 전체 대응, 다른 incident는 정찰
  또는 THERMAL_RECON까지만

각 명령의 LLM 출력을 보기 전에 사람이 canonical reference annotation을 고정한다.
`task_key = (task_type, target)`, `edge_key = (predecessor_task_key, successor_task_key)`.
정답이 여러 개 가능한 경우 LLM 결과를 본 뒤 정답을 바꾸지 않고, 실험 전에 허용 가능한
reference graph를 복수로 고정한다.

**지표**: schema-valid count, raw whole-graph-valid count, repair 후 whole-graph-valid
count, task precision/recall, edge precision/recall, exact graph match, failure category,
latency. `unnecessary_task_rate`는 별도 지표로 안 쓴다 — 정답에 없는 task는 task precision의
false positive로 처리한다. 소표본 결과는 백분율만 말고 원시 개수를 함께 제시한다(예:
"7/9 valid", "family A: 2/3").

**P6 하네스 구현(D-021)**:

- **reference annotation**: `data/reference_annotations/<id>.yaml` — `id`, `family`(A/B/C),
  `profile`(FULL_RESPONSE/AERIAL_ONLY/SELECTIVE_RESPONSE), `command`, `rationale`(reference를
  이렇게 고정한 근거), `allowed_graphs`(허용 정답 복수). 각 graph는 shorthand
  `recon_zones: [...]` + `incident_chains: {FIRE_SITE_x: [<§4 workflow의 연속 prefix>]}` 또는
  명시적 `tasks`/`edges`로 적는다. **LLM을 처음 호출하기 전에 커밋한다** — git 이력이 순서를
  증명한다.
- **task_key/edge_key 비교**: `task_key = (task_type, target)` — LLM 출력이 이제
  `{task_type, target}`뿐이므로(D-022) 이게 곧 LLM이 생성하는 것 전부다. 예측 graph를
  `allowed_graphs` 중 (task F1, edge F1) 최대인 것 하나와 대조해 task/edge precision·recall·
  exact match를 낸다. 정답이 없는 예측 task는 task precision의 FP, 정답에 있는데 없는 예측은
  recall의 FN. 정답 edge가 0개인 case(family B)의 edge precision/recall은 백분율 대신 **N/A
  (0 reference edges)**로 표기하고 성공 여부는 exact match로 본다.
- **raw와 final 둘 다 측정**: `raw_candidate`(repair 이전)와 최종 `candidate` 각각에 대해
  지표를 낸다. schema 실패로 candidate가 없으면 그 지표는 N/A(집계에서 분모 제외).
- **감사 기록(§14, §16 — 축소 금지)**: 결과 JSON에 case별로 raw·final 후보의
  `tasks`(task_type/target/파생 priority)·`edges`, raw·final `graph_hash`, `accepted`,
  `error_codes`, `repaired_schema_valid`를 저장한다. 제3자가 `task_type`/`target`만으로
  precision·recall·exact match를 독립 재계산할 수 있어야 한다. 가능하면 모델의 structured
  output 원문도 남긴다.
- **집계**: schema-valid·raw/repair 후 whole-graph-valid·approved를 `X/N`(N = 실행한 case
  수, 하드코딩 금지)로, task·edge precision/recall은 candidate가 있는 case의 평균 + 원시
  분자/분모, exact match count, failure category 히스토그램, latency(초) 통계, family별 분해.
  repair는 "attempted / recovered / first-pass approved"를 분리해 적는다(attempted 0이면
  "repair는 mock·negative 테스트로만 검증"이라고 명시).
- **재현성**(§14): 결과에 `scene_hash`, `validator_version`, 명령별 `resolved_models`(실제
  `completion.model`), backend 종류를 기록한다. 하네스 자체 예외(네트워크·인증·backend
  raise)는 `failure_category`(모델 출력 실패 분류)와 섞지 않고 별도 `harness_error`로 적는다.
- **위 감사 필드를 저장하지 않은 실행은 결과로 인정하지 않는다** — 필드를 추가한 뒤 9개
  라이브 평가를 다시 실행한다.
- 실제 LLM 평가는 `OpenAIBackend`, 하네스 self-test는 `MockBackend`(스크립트 응답).

---

## 13. CBBA/실행 평가

allocation success, unassigned task count, capability violation count, precedence violation
count, total route distance, estimated makespan, agent utilization, workload distribution,
idle-agent count, CBBA consensus rounds, 동일 입력 재실행 결정성. capability/precedence
violation은 정상 실행에서 항상 0이어야 한다.

**P3 plan-time schedule 모델(D-010)**: P3은 실제 event loop가 아니라 계획 평가다.
topological-wave barrier로 계산한다 — epoch 1 시작 0, 각 epoch의 frontier task를 계획 실행,
epoch 종료 시각 = 그 frontier의 최대 completion, 다음 epoch agent 출발 시각 =
`max(agent_free_at, epoch_start)`, 그다음 travel → task_start → dwell 순서. **agent는
task가 READY가 되기 전에 이동을 시작하지 않는다**(barrier 이전 이동 금지). `agent_utilization`
의 busy time은 **실제 travel + dwell만** 포함하고 predecessor 대기시간은 제외한다.
event-driven 방식(predecessor 완료마다 즉시 새 epoch)은 P4 executor 범위이므로 P3에서는 안 쓴다.

작은 toy fixture에서 exact allocation과 비교할 수 있으나, 이는 CBBA 구현 자체의 sanity check일
뿐 전체 시나리오에서의 최적성이나 BP 대비 우월성의 근거로 쓰지 않는다.

---

## 14. 재현성 주장의 범위와 PROVENANCE

"같은 graph에는 항상 같은 검증 결과"라는 주장은 다음이 고정됐을 때만 성립한다: Validator·규칙
버전, semantic scene hash, task vocabulary, configuration, 입력 graph canonicalization.
Validator 실행 결과에는 최소한 `graph_hash`, `scene_hash`, `validator_version`, `accepted`,
`error_codes`를 기록한다.

**`validator_version` bump 규칙(D-008)**: 판정 규칙이 바뀌면(invariant 추가·제거·의미 변경,
schema 허용 범위 변경, hash payload 형식 변경) 반드시 올린다. 같은 버전 아래에서 동일 입력의
`accepted`/`error_codes`가 달라지면 안 된다. 테스트는 의도한 버전 literal을 확인한다.
현재 `VALIDATOR_VERSION = "1.3"` — 1.2 → 1.3 (D-022): candidate schema task entry 키가
`{task_type, target, priority}` → `{task_type, target}`, `priority`는 compiler가 파생.
`graph_hash` node payload는 여전히 `(task_type, target, priority)` triple이며 priority는
`derive_priority`가 채운다.

**rejected patch의 `graph_hash` 범위(D-008)**: `E_SCHEMA`/`E_PATCH_CONFLICT`로 whole-graph
단계 이전에 거부된 patch는 최종 graph가 존재하지 않으므로 `graph_hash`가 빈 문자열이다. 이
경우 `scene_hash` + `validator_version` + `error_codes`가 감사 기록이다. raw operation을
해시하는 `patch_hash` 도입은 **P8로 유보한다(D-015)** — MissionPatch는 P5 candidate 검증
경로에 쓰이지 않고 RQ3(P8)에서 실제로 사용되므로, P8 문서 개정 시 함께 확정한다.

이전 저장소에서 재사용하는 것은 전부 `docs/PROVENANCE.md`에 원본 경로·source commit·재사용
이유를 기록한다. 재사용 후보: TaskGraph 연산 패턴, 상태 전이(READY/PENDING recompute) 패턴,
CBBA consensus/bundle 핵심과 보상형태, event logger 패턴, SimExecutor event-loop 패턴,
structured-output backend 패턴, environment/reference 분리 패턴, 도메인 독립 테스트
유틸리티. 가져오지 않는 것: 이전 연구 계약, 기존 task enum, UAV 중심 타입, 기존 domain
invariant, 기존 prompt, 기존 scenario/world, 기존 결과값, 기존 테스트 파일 내용(패턴만 배우고
새로 작성).

**알려진 이식 시 위험**: 이전 저장소 `execution/mission_runner.py`는 "매 iteration 시작
시점에 계산해둔 ready_ids를, 그 iteration의 완료 이벤트 처리 이후에도 stale한 채로 deadlock
판정에 쓰는" 버그가 있었고, 자매 파일 `tools/run_urban_px4_mission.py`에는 이 버그가 아직
안 고쳐진 채 남아 있다(확인됨). 이 프로젝트의 `execution/mission_runner.py`를 작성할 때는
deadlock 판정 직전에 반드시 recompute를 한 번 더 하는 패턴으로 **처음부터** 작성하고, 최소
재현 테스트(단일 agent, A→B 체인)를 P4 게이트에 넣는다 — 옛 테스트 파일을 복사하지 않고
독립적으로 새로 작성한다.

P4 구현체는 `execution/executor.py`의 `SimExecutor`다(D-011). "아무도 작업 중이 아니고
dispatch할 것도 없다"고 판단하기 직전에 `recompute_ready()`를 호출한 뒤 epoch를 한 번 더
시도하고, 그래도 진전이 없으면 남은 task 목록과 함께 종료한다(무한 루프 없음). 최소 재현·
부분진전 후 deadlock·정상 완주 테스트가 P4 게이트다.

**종료 사유 분리(D-012)**: `ExecutionResult`는 `termination` ∈ {`COMPLETED`, `DEADLOCK`,
`STEP_LIMIT`}을 기록한다. `deadlocked`는 `termination == DEADLOCK`일 때만 참이다. `max_steps`
소진(`STEP_LIMIT`)은 deadlock이 아니다 — §13의 deadlock 집계에 섞이면 안 된다. **마지막
허용 step에서 모든 task가 완료되면 `COMPLETED`로 판정한다**(D-013) — loop 종료 후 최종
상태를 다시 확인한다.

**precedence violation 판정(D-013)**: agent가 predecessor 완료 전에 목적지로 **출발**했는지로
본다 — `task_completion[p] > task_departure[s]`이면 위반. 도착 시각(`task_start`)이 아니라
출발 시각(`task_departure`)과 비교해야 "READY 전 이동 금지"의 의미가 맞다.

**STEP_LIMIT 결과의 지표(D-014)**: busy time은 dispatch 시점에 예정 travel+dwell 전체를
더하므로, 실행 중 task가 남은 채 `STEP_LIMIT`으로 끝나면 `agent_utilization`이 1을 넘을 수
있다(미래 busy가 분자에, 완료 시각까지만 분모에). `STEP_LIMIT` 실행의 `makespan`·
`agent_utilization`은 평가 지표로 쓰지 않는다 — `agent_utilization`은 빈 dict로 반환한다.
`COMPLETED`/`DEADLOCK`에서는 실행 중 agent가 없으므로 정상이다.

**실행 중 새 epoch의 입찰(D-012)**: 이미 RUNNING인 task는 그 agent의 residual path scoring에서
제외한다(도착 지점으로 위치 투영 + RUNNING task는 path에서 임시 제거). 아직 시작 안 한
held task만 residual path에 남긴다. 경매 후 RUNNING task를 실제 실행 path 선두에 다시
병합한다. RUNNING task를 residual path에 남기면 그 이동·dwell·reward가 이중 계산돼 winner가
바뀐다.

**assignment 정리(D-012)**: task를 COMPLETED로 바꿀 때 `task.assigned_agent = None`,
`agent.current_task = None`, bundle/path에서 제거한다(§10 assignment invariant). 과거 winner는
`ExecutionResult.assignments`에만 보존한다. 완주 후 내부 MissionState는 §10 assignment
invariant를 통과해야 한다.

---

## 15. 구현 순서와 게이트

| 단계 | 내용 | 완료 게이트 |
|---|---|---|
| P0 | 독립 저장소, 이 계약 확정 | 이 문서 커밋 |
| P1 | semantic scene, Agent, TaskGraph, route graph, reference fixture | 아래 P1 게이트 전 항목 |
| P2 | deterministic whole-graph Validator + MissionPatch reconciliation | 단일 트랜잭션 + 다중 트랜잭션 우회 테스트 전부 통과 |
| P3 | platform-aware CBBA, rolling READY-frontier epoch | reference fixture에서 capability/precedence violation 0, 모든 UGV bid가 route distance 사용 확인 |
| P4 | 2D executor, end-to-end reference mission | 완주 + 위반 0 + deadlock 최소 재현 테스트 통과 |
| P5 | LLM Step1/Step2/repair(mock 테스트) | mock 기반 파이프라인 테스트 통과 |
| P6 | 최소 9개 입력 평가 + 결과 시각화 | precision/recall/원시개수 표 산출 |
| P6.5 | 얇은 통합 runner: NL → `generate_mission` → `allocate` → `SimExecutor` | 대표 명령 1~3개 완주, RQ1↔RQ2 연결 시연 (D-025) |
| P7 (선택) | Gazebo integration | 20~30초 대표 클립 |
| P8 (선택) | RQ3: MissionPatch 재배선 + 선택적 재할당 비교 | 별도 게이트, 착수 전 이 문서 개정 |

**P1 완료 게이트** (v1.1, D-002 — 전 항목 통과해야 P1 완료 선언 가능):

1. `Agent`, `Task`, `TaskGraph`, `RouteGraph` 단위테스트 통과.
2. semantic scene과 reference fixture가 오류 없이 로드됨.
3. reference fixture가 §3 고정 형상과 일치: task 12, edge 6, 계산된 초기 READY 6, 초기
   PENDING 6.
4. fixture의 모든 task_id 유일, 모든 target이 존재하는 area/incident 참조, 모든 edge 양끝이
   존재하는 task 참조, cycle 없음.
5. route graph 도달가능성 전수 검증 통과 — 모든 UGV 대상 task(`GROUND_INSPECTION`,
   `GROUND_SUPPRESSION`)의 `access_node_id`가 route graph에 존재하고 모든 UGV 시작
   노드에서 도달 가능(§8).

---

## 16. 시간 부족 시 cut-order

1. Gazebo 통합(P7)
2. exact solver 비교
3. 반복 LLM 호출
4. 18개 입력을 최소 9개로 축소
5. 시각화 애니메이션 폴리싱
6. RQ3(P8) 전체

**절대 자르지 않음**: canonical reference graph, deterministic whole-graph Validator,
heterogeneous capability allocation, platform-aware travel cost, 2D end-to-end 실행, 최소
9개 LLM 평가, raw output과 validated output 비교.

---

## 17. 명시적 범위 제외

실제 RGB/thermal perception, 자동 화재 탐지, 물리적 화재 안정성 판정, `WATER_LOAD`,
suppressant 잔량과 재보급, same-agent resource coupling, obstacle removal, relay deployment,
target tracking, 일반 조건부 task graph, SLAM, 동적 장애물 회피, 일반 road planner, LLM 직접
agent 할당, 새로운 CBBA 알고리즘 제안, P0~P7 완료 전 RQ3 구현, MP4MR A~G 체계 복제, 모든
agent가 최소 1개 task를 받아야 한다는 제약, bundle 길이 ≥2를 Phase 1 invariant나 완료 게이트로
쓰는 것(P8에서는 실험 precondition으로 재검토 가능 — §15 P8).
