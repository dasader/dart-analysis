# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
FRONTEND_PORT=8097
SCHEDULER_INTERVAL_HOURS=24  # 신규 보고서 자동 수집 주기
ANALYSIS_INTERVAL_SECS=30    # 보고서 간 Gemini 호출 최소 간격 (TPM 한도 대응)
```

## 아키텍처

### 백엔드 (`backend/app/`)

```
main.py          FastAPI 앱, lifespan(DB 초기화·프롬프트 시딩·스케줄러·큐 워커 시작)
config.py        pydantic-settings, .env 탐색 순서: [".env", "../.env"], extra="ignore"
database.py      SQLAlchemy engine + SessionLocal + Base
models.py        Company · Report · Analysis · PromptTemplate
schemas.py       Pydantic 요청/응답 모델
seed_prompts.py  3가지 기본 프롬프트 템플릿 DB 시딩
scheduler.py     APScheduler — 활성 기업의 신규 사업보고서 자동 수집

routers/
  companies.py   CRUD + OpenDART 기업 검색
  reports.py     보고서 다운로드·삭제·재다운로드·ZIP 다운로드·내용 조회
  analyses.py    분석 요청·조회·큐 상태
  scheduler.py   스케줄러 상태 조회·즉시 실행
  prompts.py     프롬프트 템플릿 CRUD

services/
  dart_client.py      OpenDART API 연동 (corpCode.xml ZIP 파싱, list.json, document.xml)
  report_service.py   ZIP 다운로드·추출, XML/HTML 텍스트 추출
  gemini_client.py    Gemini API (run_in_executor로 블로킹 호출 분리, 429 자동 재시도)
  analysis_service.py run_combined_analysis() — 보고서 1건에 대해 Gemini 1회 호출로 3가지 분석 동시 처리
  analysis_queue.py   asyncio.Queue, report_id 기반, 중복 투입 방지, TPM 간격 제어
```

### 분석 흐름

1. 엔드포인트가 `Analysis` 레코드(status=pending) 생성 후 `enqueue(report_id)` 호출
2. 큐 워커가 `run_combined_analysis(db, report_id)` 실행
3. pending 상태인 분석 유형을 한꺼번에 수집, **Gemini 1회 호출**로 JSON 응답 수신
4. JSON 파싱 후 각 `Analysis` 레코드에 저장 (status→completed/failed)
5. 프론트엔드는 5초 폴링으로 상태 감지

**중요**: `gemini_client.generate()`는 동기 함수(`generate_content`)를 `loop.run_in_executor()`로 래핑 — 직접 호출하면 이벤트 루프가 블로킹되어 다른 API 요청 불가.

### 스케줄러 동작

- 대상: `is_active=True`인 기업 중 사업보고서가 1건 이상 있는 기업만
- 범위: DB 내 최신 사업보고서 `fiscal_year + 1` 이후 공시된 신규 보고서
- 사업보고서 없는 기업은 건너뜀 (수동으로 최초 1건 수집 필요)

### 보고서 수집 정책

`_classify_report()` (`dart_client.py`) 기준:
- **수집**: 사업보고서만
- **제외**: 반기보고서, 분기보고서, 정정보고서 (`"정정"` 포함 시 제외)

### 프론트엔드 (`frontend/src/`)

```
api/client.ts    fetch 래퍼, 모든 API 함수 정의 (BASE="/api", Vite proxy → 백엔드)
types/           TypeScript 인터페이스
pages/
  CompanyList.tsx    기업 목록 CRUD, 컬럼별 정렬 (기업명·코드·보고서수·분석일)
  CompanyDetail.tsx  탭(보고서·분석 3종), 토스트 알림, 분석 상태 관리
  PromptSettings.tsx 프롬프트 템플릿 편집
components/
  ReportTable.tsx      정렬·분석·재다운로드·삭제, 보고서명 클릭 시 ZIP 다운로드
  AnalysisView.tsx     분석 결과 표시, 5초 폴링, ReactMarkdown + remark-gfm, 인쇄 전용 통합 뷰
  PrintableReport.tsx  (미사용 — AnalysisView 내 인라인으로 대체됨)
  CompanySearch.tsx    OpenDART 기업 검색 자동완성
  CompanyEditModal.tsx 기업 정보 수정 모달
  DownloadModal.tsx    보고서 다운로드 연도 선택 (사업보고서 고정)
```

**CSS**: Tailwind v4 (`@import "tailwindcss"` + `@plugin "@tailwindcss/typography"`), `@theme` 블록에 커스텀 색상 변수 정의. 폰트: Pretendard(한글) + DM Sans(영문) + JetBrains Mono — mono 폰트 스택에 Pretendard 포함하여 한글 fallback 처리.

**인쇄**: `window.print()` 호출 시 화면 UI는 `no-print`로 숨기고, `print-only` 클래스의 통합 보고서(선택 연도 3개 분석)만 출력. 표 깨짐 방지를 위해 `index.css`에 전용 `@media print` 스타일 정의.

### OpenDART API

- `corpCode.xml` (ZIP) → 기업 코드 검색
- `list.json` → 공시 목록 (`pblntf_ty=A` 정기공시만)
- `document.xml` → 보고서 ZIP 다운로드, `{DATA_DIR}/reports/{corp_code}/{fiscal_year}/{rcept_no}.zip` 저장
- 보고서 ZIP 다운로드 엔드포인트: `GET /api/reports/{id}/download` → `Content-Disposition` 헤더로 `회사명_연도_사업보고서.zip` 파일명 설정

### Gemini 모델 및 한도

- 모델: `gemini-3-flash-preview`
- TPM 한도: 2M tokens/min → `analysis_interval_secs=30` (보고서 간 최소 간격)
- 입력 상한: 1,400,000자 (앞 80% + 뒤 20% 방식 트런케이션)
- 출력 토큰: 분석 유형당 8,192 × 유형 수 (combined 시 최대 24,576)
- 429 RESOURCE_EXHAUSTED 시 retryDelay 파싱 후 최대 5회 자동 재시도

### 포트

| 서비스 | 호스트 포트 |
|--------|------------|
| 백엔드 (FastAPI) | 8016 |
| 프론트엔드 prod (Nginx) | 8097 |
| 프론트엔드 dev (Vite) | 5185 |
