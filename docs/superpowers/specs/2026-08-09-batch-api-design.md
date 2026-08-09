# Gemini Batch API 전환 설계

작성일: 2026-08-09

## 배경

실측 벤치마크(실제 SK하이닉스 2024년 사업보고서 624,293자 = 418,637토큰, 30회 API 호출)로
모델·thinking level을 비교한 결과 현재 구성에 두 가지 문제가 확인됐다.

**1. 현재 모델이 프롬프트 요구를 못 지킨다.** 프롬프트는 "확인 가능한 모든 종속회사"를
요구하는데, `gemini-3.1-flash-lite`는 실제 56개사 중 8개 안팎만 나열한다.

| 모델 | minimal | low | medium | high |
|---|---|---|---|---|
| 3.1-flash-lite | 10, 10, 58 | 10 | 10 | 7, 9, 8 |
| 3.5-flash-lite | 58, 55, 58 | 58 | 57 | 57 |
| 3.6-flash | 58 | 58 | 51 | 58 |

(종속회사 표 행 수. 실제 56개사. 쉼표는 반복 측정)

`3.1-flash-lite`는 7회 중 6회가 10행 이하이고 회차 간 편차도 크다. `3.5-flash-lite`는
6회 모두 55~58행으로 안정적이다.

**2. thinking level이 이 작업에서는 순손실이다.** 사업보고서 분석은 추론이 아니라
추출·나열 과제라 thinking이 품질을 올리지 않으면서 출력 예산만 잠식한다.
`3.5-flash-lite`는 minimal과 high의 품질이 같은데 high는 thinking 4,833토큰을 더 쓰고
2배 느리다. `3.1-flash-lite`는 high에서 오히려 출력이 짧아진다.

**3. 현재 모델은 2027-05-07 종료 예정이다.** Google이 지정한 후속이 `3.5-flash-lite`다.

### 균형점

| 구성 | 종속표 | 소요 | 1건 USD |
|---|---|---|---|
| 현재 3.1-FL @ high | 7~9행 | 16~21초 | $0.112 |
| **3.5-FL @ minimal** | 55~58행 | 14~18초 | $0.137 |
| **3.5-FL @ minimal + Batch** | **58행** | **8.3분** | **$0.068** |
| 3.6-F @ low | 58행 | 35초 | $0.665 |

Batch API는 정확히 50% 할인이므로, 모델을 올리면서도 현재보다 **39% 저렴**해진다.

### Batch API 실측 (2026-08-09)

실제 batch job 1건(대형 보고서 + 소형 보고서 2요청)을 제출해 확인했다.

- **turnaround 8.3분** (제출→SUCCEEDED 501초). 문서상 SLO는 24시간이나 실제로는 훨씬 빠름
- **`thinkingLevel`이 batch에서 정상 작동** — `thoughtsTokenCount=0`. 공식 문서에
  batch+thinking 예제가 없어 불확실했던 부분을 검증함
- 품질이 실시간 API와 동일 (종속회사 표 58행), JSON 파싱 성공, `finishReason=STOP`
- JSONL 파일 방식 필수 — inline은 총 20MB 제한인데 보고서 1건이 UTF-8로 약 1.7MB

## 결정 사항

- 모든 분석(수동 3경로 + 스케줄러)을 batch로 보낸다. 실시간 경로는 남기지 않는다
- `gemini_client.py`는 삭제한다
- 오래 걸리는 job은 그냥 기다린다. 자동 폴백·재시도 없음
- 스케줄러 자동 분석은 설정 플래그로 두되 **기본 off** (의도치 않은 비용 방지)
- Batch 현황은 신규 페이지 `/settings/batches`

## 데이터 모델

`Analysis` 테이블은 변경하지 않는다. JSONL의 `key`를 `report_id`로 쓰고,
`BatchJob`이 담당 `report_ids`를 JSON으로 들고 있으면 매칭에 충분하다.
신규 테이블 1개뿐이라 기존 `Base.metadata.create_all` 방식 그대로 처리된다
(이 프로젝트에는 Alembic이 없다).

```
BatchJob
  id
  job_name          unique — Gemini batch 리소스명 (batches/xxx)
  file_name         업로드한 JSONL 파일명 (files/xxx)
  model_name
  thinking_level
  state             JOB_STATE_* (PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED/EXPIRED)
  report_ids        담당 report_id 목록 (JSON 배열)
  request_count
  success_count
  failed_count
  error_message
  submitted_at
  completed_at
```

## 흐름

```
enqueue(report_id)                    ← 기존 API 그대로 (수동 3경로 + 스케줄러)
   ↓ 워커가 큐를 드레인해 한 번에 묶음
JSONL 빌드 → files.upload → batches.create
   ↓ BatchJob 저장, 담당 Analysis들 running
폴링 (APScheduler, 60초 간격)
   ↓ SUCCEEDED → files.download → key(report_id)로 분배
Analysis completed / failed
```

큐는 없애지 않고 **묶는 버퍼**로 남긴다. `analyze-all`이 보고서 10개를 연속
enqueue하면 batch 1개로 묶여 제출된다.

## 파일 변경

| 파일 | 변경 |
|---|---|
| `services/gemini_batch.py` | 신규 — JSONL 빌드·업로드·제출·상태조회·결과 파싱 |
| `services/analysis_queue.py` | 드레인 후 batch 제출로 교체. `analysis_interval_secs` 대기 제거 |
| `services/analysis_service.py` | 프롬프트 조립·결과 저장을 함수로 분리 (batch가 재사용) |
| `services/gemini_client.py` | **삭제** |
| `routers/batches.py` | 신규 — `GET /api/batches`, `POST /api/batches/{id}/cancel` |
| `models.py` | `BatchJob` 추가 |
| `scheduler.py` | 폴링 job 추가 + `scheduler_auto_analyze` 시 enqueue |
| `main.py` | 시작 시 고아 pending 재투입 |
| `frontend/pages/BatchList.tsx` | 신규 `/settings/batches` |

## 재시작 복구

미완료 `BatchJob`은 DB에 있으므로 폴링이 자동으로 이어받는다. 제출 전에 죽어
`pending`으로 남은 `Analysis`는 앱 시작 시 다시 enqueue한다.
현재 in-memory 큐(`asyncio.Queue` + 전역 set)의 유실 문제가 함께 해결된다.

## 설정 변경

```
MODEL_NAME                gemini-3.1-flash-lite → gemini-3.5-flash-lite
THINKING_LEVEL            HIGH → MINIMAL
ANALYSIS_INTERVAL_SECS    제거 (batch는 별도 한도)
SCHEDULER_AUTO_ANALYZE    신규, 기본 false
BATCH_POLL_INTERVAL_SECS  신규, 기본 60
```

## 오류 처리

- **개별 요청 실패**: 잡이 `SUCCEEDED`여도 발생한다. 결과 JSONL 줄마다 `error` 키를
  확인해 해당 `Analysis`만 failed 처리
- **잡 단위 실패** (`FAILED`/`EXPIRED`/`CANCELLED`): 담당 `Analysis` 전부 failed + 사유 기록
- **48시간 만료**: 자동 재시도 없이 failed. 관리자가 다시 요청

## 관리자 화면

`/settings/batches` — 제출 시각, 상태, 요청 수(성공/실패), 경과 시간, 모델, 취소 버튼.
취소는 관리자 전용(`require_admin`).

## 테스트

`tests/test_batch.py` — JSONL 빌드와 결과 파싱은 순수 함수이므로 API 없이 검증한다.

- 정상 응답 파싱
- 개별 요청 error 줄 처리
- JSON이 깨진 응답 처리

기존 `test_admin_auth.py`에 신규 라우트(`POST /api/batches/{id}/cancel`) 게이팅 추가.

## 부수 확인 사항

- 실측 토큰 비율은 **1.49자/토큰**으로, 코드 주석의 1.65자/토큰 가정보다 토큰을 더 먹는다.
  `MAX_CHARS=1,400,000`이면 약 94만 토큰으로 컨텍스트 상한(1,048,576)에 근접한다
- 벤치마크 30회 중 `finish_reason`은 전부 `STOP`이었다. `max_output_tokens=24,576`
  잠식으로 인한 JSON 절단은 실제로는 발생하지 않았다

## 후속 (별도 작업)

섹션 추출로 입력을 1/10로 줄이면 $0.031/건까지 내려간다. 다만 품질 영향 검증이
선행되어야 하므로 이번 범위에서 제외한다.
