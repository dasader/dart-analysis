# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 포트 배분 규칙·레지스트리: https://github.com/dasader/code/blob/main/PORTS.md (이 서비스 NN=16). 신규 포트 배정 시 준수.

## 개발 서버 실행

**백엔드** (포트 8016, 프로젝트 루트의 `.env` 파일 필요):
```bash
cd backend
DATA_DIR=./data python -m uvicorn app.main:app --reload --port 8016
```
- `uvicorn` 바이너리 대신 반드시 `python -m uvicorn` 사용 (Python 3.14 환경)
- `.env` 파일은 프로젝트 루트에 위치, `backend/` 또는 `../` 양쪽에서 자동 탐색
- `DATA_DIR=./data`는 로컬 개발용 오버라이드 (Docker에서는 `/app/data` 사용)
- `--reload`는 변경 감지 후 서브프로세스 재시작이 누락될 수 있음 → 신규 라우트 추가 시 반드시 완전 재시작
- 완전 재시작 시 `__pycache__` 삭제 권장 (캐시로 인해 신규 라우트가 등록되지 않는 현상 있음)

**프론트엔드** (포트 5185):
```bash
cd frontend
npm run dev
```

**프론트엔드 타입 검사** (Docker 빌드와 동일한 `tsc -b` 모드):
```bash
cd frontend
npm run typecheck
```
- `npx tsc --noEmit`은 Docker 빌드(`tsc -b`)와 검사 방식이 달라 로컬에서 통과해도 Docker 빌드가 실패할 수 있음
- 프론트엔드 코드 수정 후 Docker 빌드 전에 반드시 `npm run typecheck`로 사전 검증

**프론트엔드 E2E** (실제 헤드리스 브라우저 — 타입 검사가 못 보는 렌더·라우팅):
```bash
~/code/e2e-headless/run.sh http://localhost:8116 frontend/e2e
```
- `code/` 공용 실행기가 도커 이미지 안에서 브라우저를 띄운다 — 이 레포에는 설치·설정이 필요 없다
- `docker compose up -d`로 스택이 떠 있어야 한다(nginx가 `backend` 업스트림을 요구해 frontend 단독 기동 불가)
- 데이터에 의존하지 않는 셸·라우팅만 본다 — 등록 기업이 0건이어도 통과한다

**백엔드 테스트** (관리자 인증 게이팅 검증):
```bash
cd backend
python -m pytest tests/ -v
```
- 환경에 `python`이 없으면 venv 경로로 실행 (예: `.venv/bin/python -m pytest tests/`)
- `tests/conftest.py`가 필수 API 키를 주입하므로 `.env` 없이도 import 가능

**프로덕션 (Docker Compose)**:
```bash
docker-compose up --build
```

## 환경 변수 (`.env`)

`.env.example` 참조. 주요 항목:

```env
OPENDART_API_KEY=...
GEMINI_API_KEY=...
DATA_DIR=./data              # 로컬 개발용 (Docker: /app/data)
BACKEND_PORT=8016
FRONTEND_PORT=8116
SCHEDULER_INTERVAL_HOURS=24  # 신규 보고서 자동 수집 주기
BATCH_POLL_INTERVAL_SECS=60  # batch 작업 상태 확인 주기
SCHEDULER_AUTO_ANALYZE=false # 수집한 신규 보고서를 자동 분석할지 (화면에서 변경 가능)
SECTION_EXTRACT_ENABLED=true # 분석에 필요한 구역만 추려 LLM에 전달 (화면에서 변경 가능)
ADMIN_KEY=                   # 관리 기능 보호용 키 (비우면 인증 비활성화)
```

## 아키텍처

### 백엔드 (`backend/app/`)

```
main.py          FastAPI 앱, lifespan(DB 초기화·프롬프트 시딩·고아 pending 재투입·스케줄러·큐 워커)
config.py        pydantic-settings, .env 탐색 순서: [".env", "../.env"], extra="ignore" (admin_key 포함)
dependencies.py  require_admin — X-Admin-Key 헤더 검증 (admin_key 미설정 시 통과)
database.py      SQLAlchemy engine + SessionLocal + Base
models.py        Company · Report · Analysis · PromptTemplate · BatchJob · AppSetting
                 · ApplicantCorp · DartCorp · ApiCall
migrate.py       누락 컬럼 추가 (create_all은 기존 테이블에 컬럼을 못 붙인다)
schemas.py       Pydantic 요청/응답 모델
seed_prompts.py  3가지 기본 프롬프트 템플릿 DB 시딩
scheduler.py     APScheduler — 신규 사업보고서 자동 수집 + batch 상태 폴링(60초)

routers/
  companies.py   CRUD + OpenDART 기업 검색 (삭제는 관리자 전용)
  reports.py     보고서 다운로드·삭제·재다운로드·ZIP 다운로드·내용 조회 (삭제·재다운로드는 관리자 전용)
  analyses.py    분석 요청·조회·큐 상태 (분석 요청은 관리자 전용)
  scheduler.py   스케줄러 상태 조회·즉시 실행 (즉시 실행은 관리자 전용)
  prompts.py     프롬프트 템플릿 CRUD (수정은 관리자 전용)
  batches.py     batch 작업 목록·취소·구역추출 실패 목록 (취소는 관리자 전용)
  app_settings.py 동작 설정 조회·변경 (변경은 관리자 전용)
  tags.py        태그 CRUD (삭제는 관리자 전용)
  admin.py       GET /api/admin/verify — 관리자 키 검증

services/
  dart_client.py      OpenDART API 연동 (corpCode.xml ZIP 파싱, list.json, document.xml)
  report_service.py   ZIP 다운로드·추출, XML/HTML 텍스트 추출
  gemini_batch.py     Gemini Batch API — JSONL 빌드·업로드·제출·상태조회·결과 파싱
  section_extract.py  보고서에서 분석에 쓰이는 구역(I·II·XII)만 추출. 실패 시 예외
  app_settings.py     런타임 설정 — DB 저장, 없으면 .env 기본값 폴백
  batch_poller.py     진행 중 BatchJob 상태 확인 → 완료 시 결과를 Analysis에 분배
  analysis_service.py 프롬프트 조립(build_prompts)·결과 저장(save_result)·JSON 추출
  analysis_queue.py   asyncio.Queue — 요청을 5초 창으로 모아 batch 1건으로 제출
```

### 분석 흐름 (Gemini Batch API)

모든 분석은 Batch API로 처리된다. 실시간 경로는 없다.

1. 엔드포인트가 `Analysis` 레코드(status=pending) 생성 후 `enqueue(report_id)` 호출
2. 큐 워커가 첫 요청 후 **5초 창** 동안 더 모아 한 batch로 묶는다
3. 보고서별로 JSONL 1줄 생성(3종 분석을 1요청으로 통합) → 업로드 → `batches.create`
4. `BatchJob` 저장, 담당 `Analysis`들 running 전환
5. 스케줄러가 60초마다 `poll_batches()` — 완료 시 결과 JSONL을 `key`(=report_id)로 분배
6. 프론트엔드는 5초 폴링으로 상태 감지, `/settings/batches`에서 작업 현황 확인

**중요**:
- 큐는 실행 대기열이 아니라 **묶는 버퍼**다. 진행 상태의 원본은 DB(`BatchJob`)이므로
  재시작해도 폴링이 이어받는다. 제출 전에 죽어 pending으로 남은 건은 시작 시 재투입된다
- JSONL은 REST 원형 스키마 — `systemInstruction`은 top-level, `maxOutputTokens`·
  `thinkingConfig`는 `generationConfig` 안 (inline 방식의 평면 config와 형태가 다르다)
- 보고서 1건이 UTF-8로 ~1.7MB라 inline 방식(총 20MB 제한)은 쓸 수 없다
- 잡이 `SUCCEEDED`여도 개별 요청은 실패할 수 있다 — 결과 줄마다 `error` 키를 확인한다

### 관리자 게이팅

- `require_admin` (`dependencies.py`) 의존성을 관리 라우트에 `dependencies=[Depends(require_admin)]`로 부착
- 요청 헤더 `X-Admin-Key`를 `settings.admin_key`와 비교, 불일치 시 401
- **`admin_key`가 빈 문자열이면 인증 비활성화** — 모든 관리 요청 통과 (기존 개발 환경 하위호환). FastAPI는 라우트 의존성을 body 검증보다 먼저 평가하므로 body 유무와 무관하게 401이 먼저 반환됨
- **관리자 전용**: 삭제(기업·보고서·태그), 재다운로드, 분석(단건·일괄·전체), 프롬프트 수정, 스케줄러 즉시 실행
- **공개**: 모든 GET, 기업 등록/수정, 태그 생성/수정, 태그 할당/해제, 보고서 수집·다운로드
- 프론트: `X-Admin-Key`를 `client.ts` fetch 래퍼가 자동 첨부(`localStorage` 키 `dart_admin_key`), `AdminButton`이 미로그인 시 버튼 비활성화

### 스케줄러 동작

- 대상: `is_active=True`인 기업 중 사업보고서가 1건 이상 있는 기업만
- 범위: DB 내 최신 사업보고서 `fiscal_year + 1` 이후 공시된 신규 보고서
- 사업보고서 없는 기업은 건너뜀 (수동으로 최초 1건 수집 필요)

### 보고서 수집 정책

`_classify_report()` (`dart_client.py`) 기준:
- **수집**: 사업보고서만
- **제외**: 반기보고서, 분기보고서, 정정보고서 (`"정정"` 포함 시 제외)

### 화면 계층

보고서가 부모, 분석 3종이 자식이다. 분석은 특정 보고서(=특정 연도)에 딸린 결과이므로
같은 층에 나란히 두지 않는다.

```
/                                  기업 목록
/companies/:id                     기업 상세 — 사업보고서 목록만
/companies/:id/reports/:reportId   보고서 상세 — 분석 3종 탭
```

연도 선택은 보고서 목록에서 한 번만 한다. 예전에는 분석 유형 탭마다 연도 선택기가
따로 있어 탭을 옮길 때마다 연도를 다시 골라야 했다.

**진행 상태 폴링**: pending·running이 하나라도 있으면 10초 간격으로 갱신한다.
기업 상세는 보고서와 분석을 **함께** 받아야 목록의 분석 상태가 같이 최신이 된다
(보고서만 따로 받으면 `analysis_count`가 옛날 값으로 남는다).
Batch는 분 단위라 5초 폴링은 과하다.

### 프론트엔드 (`frontend/src/`)

```
api/client.ts    fetch 래퍼, 모든 API 함수 정의 (BASE="/api", Vite proxy → 백엔드). 저장된 관리자키를 X-Admin-Key 헤더로 자동 첨부, verifyAdminKey() 포함
lib/adminKey.ts  관리자키 localStorage 저장소 (키 이름 dart_admin_key)
context/AdminContext.tsx  AdminProvider + useAdmin() — isAdmin·login·logout
types/           TypeScript 인터페이스
pages/
  CompanyList.tsx    기업 목록 CRUD, 컬럼별 정렬 (기업명·코드·보고서수·분석일)
  CompanyDetail.tsx  기업 상세 — 사업보고서 목록. 진행 중이면 10초 폴링(보고서+분석 동시)
  ReportDetail.tsx   /companies/:id/reports/:reportId — 분석 3종 탭·재분석·PDF 출력
  PromptSettings.tsx 동작 설정 토글 + 프롬프트 템플릿 편집
  BatchList.tsx      /settings/batches — batch 작업 현황·취소 (15초 폴링)
  SettingToggles.tsx 동작 설정 토글 — 끄면 비용이 느는 항목은 확인 후 변경
components/
  ReportTable.tsx      정렬·분석·재다운로드·삭제. 보고서명 클릭 시 보고서 상세로 이동.
                       분석 열은 analysis_count가 아니라 실제 분석 상태에서 파생
  AnalysisView.tsx     보고서 1건 × 분석 1종의 결과 렌더 (ReactMarkdown + remark-gfm)
  AdminButton.tsx      관리 버튼 래퍼 — 미로그인 시 disabled + "관리자 로그인이 필요합니다" 툴팁
  CompanySearch.tsx    OpenDART 기업 검색 자동완성
  CompanyEditModal.tsx 기업 정보 수정 모달
  DownloadModal.tsx    보고서 다운로드 연도 선택 (사업보고서 고정)
```

**CSS**: Tailwind v4 (`@import "tailwindcss"` + `@plugin "@tailwindcss/typography"`), `@theme` 블록에 커스텀 색상 변수 정의. 폰트: Pretendard(한글) + DM Sans(영문) + JetBrains Mono — mono 폰트 스택에 Pretendard 포함하여 한글 fallback 처리.

**인쇄**: 보고서 상세에서 `window.print()` 호출 시 화면 UI는 `no-print`로 숨기고,
`print-only` 클래스의 통합 보고서(그 보고서의 분석 3종)만 출력. 표 깨짐 방지를 위해 `index.css`에 전용 `@media print` 스타일 정의.

### OpenDART API

- `corpCode.xml` (ZIP) → 기업 코드 검색
- `list.json` → 공시 목록 (`pblntf_ty=A` 정기공시만)
- `document.xml` → 보고서 ZIP 다운로드, `{DATA_DIR}/reports/{corp_code}/{fiscal_year}/{rcept_no}.zip` 저장
- 보고서 ZIP 다운로드 엔드포인트: `GET /api/reports/{id}/download` → `Content-Disposition` 헤더로 `회사명_연도_사업보고서.zip` 파일명 설정

### 특허 출원인 ↔ DART 기업 조인

특허 출원인명은 **한글 표기**("주식회사 엘지화학"), DART는 **영문 표기**("(주)LG화학")를 쓴다.
실측에서 "이차전지 양극재" 상위 출원인 3곳(LG화학·LG에너지솔루션·POSCO홀딩스, 표본의 46%)이
문자열 매칭으로 통째로 누락됐다. **이름으로 매칭하지 마라. 법인등록번호로 조인한다.**

```sql
select co.* from companies co
  join applicant_corps ac on ac.jurir_no = co.jurir_no
```

- `applicant_corps` — KIPRIS "출원인 법인 및 사업자 번호" 벌크(수수료 없음).
  실측 385,256건 중 법인번호 보유 **99.4%**
- `Company.jurir_no` — `corpCode.xml`에는 법인번호가 없다(4개 필드뿐). 기업마다
  `company.json`을 한 번 더 호출해야 한다. 신규 등록은 라우터가 자동으로 채운다
- 분기별 갱신이라 적재는 **전량 교체**다. 증분 병합은 삭제된 출원인을 남겨 조인을 오염시킨다

```bash
cd backend
python -m scripts.load_applicant_corps ~/Corporate_20260720.zip   # ZIP 그대로 (5초)
python -m scripts.backfill_jurir_no                               # 기존 기업 채우기
```

### 기술 → 기업 파이프라인 (프로토타입)

기술 설명에서 출발해 관련 기업을 찾고 기존 분석 파이프라인에 태우는 경로.
현재 서비스(기업이 출발점)의 **앞단에 얹는** 구조라 뒷단은 그대로 재사용한다.

```
기술 설명 → keyword_extract(LLM) → patent_search(KIPRIS) → 출원인 집계
         → 법인번호 조인 → tech_pipeline.onboard → 기존 분석 큐
```

```bash
cd backend
python -m scripts.tech_to_companies "전고체 배터리용 황화물계 고체전해질"      # 조회만
python -m scripts.tech_to_companies "..." --onboard --max 3                # 등록·수집·분석
python -m scripts.tech_to_companies --usage                                # 호출량
```

매칭 결과를 셋으로 나눈다 — 처방이 다르기 때문이다.
`tracked`(추적 중) / `available`(DART에 있으나 미등록 → 등록만 하면 됨) /
`excluded`(법인번호 없음 — 개인·대학·연구소·외국).

**비용이 기업 수만큼 곱해진다.** 보고서 1건당 약 $0.0135이므로 `--max`로 반드시 상한을 둔다.

### 외부 API 호출 계측 (ApiCall)

KIPRIS 무료 한도가 **월 1,000회**뿐이라 세지 않으면 조용히 말라죽는다.
`api_usage.check()`가 호출 **전에** 잔여를 보고 모자라면 아예 보내지 않는다(`QuotaExceeded`).
실패도 센다 — 한도 집계가 성공 여부와 무관할 수 있어 보수적으로 잡았다.

### DART 기업 색인 (DartCorp)

`Company`는 **추적하기로 한** 기업, `DartCorp`는 DART에 있는 전체 목록이다.
특허 출원인의 법인번호로 corp_code를 역인출하려면 이 색인이 필요하다.

**DART는 몰아치면 응답 없이 TCP 연결을 끊는다.** 동시 5개로 약 1,000회를 넘기자
`RemoteProtocolError`가 시작됐고 이후 다른 엔드포인트까지 전부 차단됐다.
순차 호출 + 간격을 둬야 하고, 스크립트는 연속 실패 30회에서 스스로 멈춘다.

```bash
python -m scripts.build_dart_index --delay 0.3    # 이어서 채운다(확인분은 건너뜀)
```

### KIPRIS 특허 검색

게이트웨이가 **두 개**이고 인증 파라미터명이 다르다. 섞으면 `INVALID_REQUEST_PARAMETER_ERROR`가
나는데 키를 빼도 같은 오류라 원인이 안 드러난다.

| 게이트웨이 | 인증 파라미터 | 키 출처 |
|---|---|---|
| `/kipo-api/kipi/` | `ServiceKey` | data.go.kr |
| `/openapi/rest/` | `accessKey` | KIPRIS Plus 가입 |

```
https://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice/getWordSearch
  ?word=<검색어>&patent=true&utility=true&pageNo=1&numOfRows=100&ServiceKey=<KEY>
```

- 서비스 경로의 `Sevice`는 **오타가 아니라 실제 경로**다
- `patent`·`utility`는 **필수**. 빠지면 파라미터 오류
- 상품별로 따로 신청해야 한다. 미신청 시 `code=30`
- 응답 필드: `applicantName`(공동출원은 `|` 구분), `astrtCont`(초록), `ipcNumber`, `registerStatus`

**검색어는 10~30자가 적정**이다. 실측: 7자 2,440건 → 27자 318건(가장 정밀) → 86자 8건(너무 좁음)
→ 251자 20,029건(노이즈 폭증). 긴 기술 설명문을 그대로 넣으면 안 되고, LLM으로
키워드 3~5개를 뽑아 각각 검색한 뒤 출원인을 합산하는 편이 안전하다.

### 런타임 설정 (AppSetting)

`.env`는 앱 시작 시 한 번만 읽히므로, 운영 중 바꿔야 하는 값은 `app_settings` 테이블에 둔다.
DB에 값이 없으면 `.env` 기본값으로 폴백하므로 기존 동작이 유지된다.

- 화면: `/settings/prompts` 상단 "동작 설정" (관리자만 변경 가능, 재시작 불필요)
- 대상: `scheduler_auto_analyze`, `section_extract_enabled`
- 새 토글을 추가하려면 `services/app_settings.py`의 `TOGGLES`에 항목 하나만 넣으면
  API·화면이 자동으로 따라온다
- `batch_poll_interval_secs`는 APScheduler 등록 시점에 쓰이므로 `.env` 전용이다

### 프롬프트 갱신 절차

`seed_default_prompts()`는 **DB에 없는 항목만 넣는다.** 화면에서 편집한 프롬프트를
재시작 때마다 날리면 안 되기 때문이다. 따라서 `seed_prompts.py`를 고쳐도 **이미 돌고
있는 인스턴스에는 반영되지 않는다.** 실제 분석은 DB의 `prompt_templates`를 쓴다.

프롬프트를 바꿨으면 둘 다 해야 한다.
1. `seed_prompts.py` 수정 (신규 배포용)
2. `/settings/prompts` 화면에서 붙여넣기 (운영 중인 인스턴스용)

바꾼 뒤에는 반드시 **실제 batch를 한 번 돌려** 확인한다. 직접 API 호출로 검증하면
`seed_prompts.py`를 읽지만 서비스는 DB를 읽으므로, 둘이 어긋난 채 통과할 수 있다.

### 분석 프롬프트 원칙

**보고서에 없는 것은 쓰지 않는다.** 프롬프트 첫머리에 "기재 없으면 '보고서에 기재 없음'
이라 쓰고 추측하지 마라"를 둔다. 원문 정보량이 기업마다 크게 다르므로(NAVER는 연구개발
서술이 몇 줄뿐이다) 고정 섹션을 요구하면 모델이 일반론으로 채운다.

**모델은 프롬프트의 예시를 그대로 흉내낸다.** 예시 표에 GFM 구분선(`|---|`)이
없었더니 출력에서도 빠졌고(실측 표 31개 중 5개), `remark-gfm`이 표로 인식하지 못해
파이프 문자가 그대로 노출됐다. 한 응답 안에서 뭉쳐서 실패하는 경향이 있다.
예시를 올바르게 쓰고, 렌더 직전에 `lib/markdown.ts`의 `normalizeTables()`로 한 번 더
보정한다(모델 출력에 100%를 기대할 수는 없다).

**개수를 세는 항목은 검증 기준을 원문에서 찾아 주면 편차가 사라진다.**
종속회사 목록은 큰 기업에서 회차마다 12~166행으로 튀었는데, "행 수는 요약표의
'기말' 연결대상회사수와 일치해야 한다"는 자기 검증 지시를 넣자 3사 × 3회가
모두 정답과 일치했다(NAVER 82, 현대자동차 166, 두산에너빌리티 62).

분석 유형별로 처방이 다르다.

- **종속회사·R&D**: 원문에 표준 공시 표가 있다. **그대로 옮기게 하면 분량이 는다.**
  R&D는 연구개발비용 3개년 표(비용 성격별 분류·회계처리·정부보조금·매출액 대비 비율),
  지식재산권 현황, 연구개발 조직·실적이 근거다. 연구분야별 투자금액은 원문에 없으므로
  요구하지 마라(전부 "-"로 돌아온다)
- **국가전략기술**: 7개 기업 실측 결과 `국가전략기술`·`조세특례`·`세액공제`가 원문에
  **0회**다. 공시 항목이 아니라 사업 내용에서 추론하는 과제다. 따라서 **길이를 늘리면
  환각이 는다.** 대신 12개 분야를 모두 검토해 해당 없음을 명시하게 하고, 해당 분야는
  원문을 인용하게 하며, 시사점마다 [보고서 근거]/[분석가 추정]을 달게 한다

7개 기업 실측(개선 전 → 후): R&D 표 6행 → 21~36행, 국가전략기술은 분량은 그대로
두고 검토 분야가 3~7행 → 13~14행. "기재 없음" 표기가 0회 → 최대 25회로 늘었는데,
이는 품질 저하가 아니라 근거 없는 서술이 걸러진 것이다.

### 구역 추출

보고서 전문을 그대로 보내면 입력의 대부분이 재무제표·임원 명단이라 3종 분석에 쓸모가 없다.
`section_extract.py`가 대제목 기준으로 **I(회사의 개요) · II(사업의 내용) · XII(상세표)**만 남긴다.

- 7개 기업 실측: 원문 대비 **8~21%**로 축소. 품질은 유지되거나 소폭 향상
  (SK하이닉스 기준 입력 418,637 → 52,192토큰, 골든 21개 중 적중 14~15 → 15~17)
- 대제목은 같은 문구가 목차·본문·재무제표 안에 여러 번 나온다. **정규 순서(I→XII)로
  이어지는 체인 중 가장 넓게 퍼진 것**을 본문으로 고른다 — 목차는 12개가 수천 자 안에
  몰려 있어 자연히 탈락하고, 목차가 없는 보고서도 같은 규칙으로 처리된다
- 마지막 구역(XII) 뒤에는 감사보고서가 이어지므로 `【 전문가의 확인 】`으로 자른다

**추출 실패는 LLM으로 넘기지 않는다.** 필수 구역을 못 찾거나, 거의 줄지 않았거나(>70%),
지나치게 짧으면(<20,000자) `ExtractionFailed`를 던지고 해당 분석을 failed로 둔다.
조용히 전문을 흘려보내면 서식이 바뀐 걸 아무도 모른 채 비용만 나가기 때문이다.
실패는 `[구역추출실패]` 접두어가 붙어 `/settings/batches` 경고 배너와 헤더 배지로 드러난다
— 이 알림이 뜨면 `section_extract.py`의 규칙을 고쳐야 한다는 뜻이다.

### Gemini 모델 및 한도

- 모델: `gemini-3.5-flash-lite`, thinking level `MINIMAL`
- **thinking을 올리지 마라.** 사업보고서 분석은 추론이 아니라 추출·나열 과제다.
  실측상 minimal과 high의 품질이 같은데 high는 thinking 토큰을 추가 과금하고 2배 느리다.
  이전 모델(`3.1-flash-lite`)은 high에서 오히려 출력이 짧아졌다
- 입력 상한: 1,400,000자 (앞 80% + 뒤 20% 방식 트런케이션).
  실측 **1.49자/토큰**이라 약 94만 토큰 — 컨텍스트 상한 1,048,576에 근접하니 늘리지 마라
- 출력 토큰: 분석 유형당 8,192 × 유형 수 (combined 시 최대 24,576)
- Batch API는 표준 대비 **50% 할인**. 실측 turnaround 8.3분 (문서상 SLO는 24시간)
- 보고서 1건당 실측 비용: **$0.0135** (구역추출 + batch). 전환 전 구성 대비 88% 절감
- batch 작업은 pending/running 48시간 초과 시 `JOB_STATE_EXPIRED`로 만료된다 (자동 재시도 없음)

**모델 선정 근거** (실제 SK하이닉스 2024년 사업보고서로 30회 실측):

| 모델 | 종속회사 표 행 수 (실제 56개사) | 1건 USD |
|---|---|---|
| 3.1-flash-lite | 7~10행 (56개 중 8개만 나열) | $0.112 |
| **3.5-flash-lite** | **55~58행** | $0.137 (batch $0.068) |
| 3.6-flash | 51~58행 | $0.665 |

`3.1-flash-lite`는 2027-05-07 종료 예정이기도 하다.

### 포트

| 서비스 | 호스트 포트 |
|--------|------------|
| 백엔드 (FastAPI) | 8016 |
| 프론트엔드 prod (Nginx) | 8116 |
| 프론트엔드 dev (Vite) | 5185 |
