# 기업 DART 사업보고서 분석 웹서비스 — 설계 문서

> 프로젝트: `16_firm-dart-analysis`
> 작성일: 2026-04-11

---

## 1. 개요

OpenDART API를 통해 기업의 사업보고서를 다운받고, Gemini LLM으로 분석하여 기업의 사업 변화, R&D 투자, 국가전략기술 관련 활동을 파악하는 웹서비스.

### 핵심 분석 3가지

1. **종속회사 변동 분석** — 연결대상 종속회사 현황 추출, 연도별 변동 내역 조사, 주요 사업영역 변화 분석, 시사점 제시
2. **R&D/투자 분석** — 핵심 기술 투자 영역, 시설 투자, 유무형 투자, 세부 전략, 투자금액(가능 시)
3. **국가전략기술 분석** — 해당 기업의 국가전략기술 분야 사업/연구 내용 정리 및 분석

---

## 2. 기술 스택

| 구분 | 기술 | 비고 |
|------|------|------|
| Frontend | React + Vite → Nginx (정적 빌드) | 기존 프로젝트와 일관성 |
| Backend | FastAPI + APScheduler | 경량 스케줄러 내장 |
| Database | SQLite | 단일 파일, 별도 컨테이너 불필요 |
| File Storage | 로컬 파일 시스템 | `data/reports/{corp_code}/{year}/` |
| AI | Google Gemini 3 Flash Preview | 최대 1M 토큰 입력 컨텍스트 |
| PDF 출력 | 브라우저 인쇄 (window.print) | 서버사이드 의존성 없음 |
| 배포 | Docker Compose (시놀로지 서버) | 경량화 목표 |

### 환경변수 (.env)

```env
OPENDART_API_KEY=...
GEMINI_API_KEY=...
BACKEND_PORT=8016
FRONTEND_PORT=8097
FRONTEND_DEV_PORT=5185
SCHEDULER_INTERVAL_HOURS=24
```

---

## 3. 포트 할당

| 서비스 | 호스트 포트 | 컨테이너 포트 | 기술 |
|--------|------------|--------------|------|
| backend | **8016** | 8000 | FastAPI + APScheduler |
| frontend (prod) | **8097** | 80 | Nginx (정적 빌드) |
| frontend (dev) | **5185** | 5173 | Vite dev 서버 |

---

## 4. 데이터 모델

### 4.1 companies (분석 대상 기업)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| corp_code | VARCHAR UNIQUE | DART 기업 고유코드 |
| corp_name | VARCHAR | 기업명 |
| stock_code | VARCHAR NULL | 종목코드 (상장사만) |
| is_active | BOOLEAN DEFAULT TRUE | 활성 여부 |
| created_at | DATETIME | 생성일 |
| updated_at | DATETIME | 수정일 |

### 4.2 reports (보고서 메타데이터)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| company_id | INTEGER FK → companies.id | 기업 참조 |
| rcept_no | VARCHAR | 접수번호 |
| report_name | VARCHAR | 보고서명 |
| report_type | VARCHAR | 사업보고서 / 분기보고서 / 반기보고서 |
| fiscal_year | INTEGER | 사업연도 |
| filing_date | DATE | 공시일 |
| file_path | VARCHAR | 저장 경로 |
| downloaded_at | DATETIME | 다운로드 일시 |
| created_at | DATETIME | 생성일 |

- UNIQUE 제약: `(company_id, rcept_no)` — 동일 보고서 중복 방지

### 4.3 analyses (분석 결과)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| company_id | INTEGER FK → companies.id | 기업 참조 |
| report_id | INTEGER FK → reports.id | 보고서 참조 |
| analysis_type | VARCHAR | subsidiary / rnd / national_tech |
| status | VARCHAR DEFAULT 'pending' | pending / running / completed / failed |
| result_json | TEXT | 구조화된 분석 결과 (JSON) |
| result_summary | TEXT | 요약 텍스트 (마크다운) |
| error_message | TEXT NULL | 실패 시 에러 메시지 |
| model_name | VARCHAR | 사용된 모델명 |
| created_at | DATETIME | 생성일 |
| updated_at | DATETIME | 수정일 |

- UNIQUE 제약: `(company_id, report_id, analysis_type)` — 분석 유형별 단일 결과, 재분석 시 UPSERT
- 분석 요청 시 `status=pending`으로 즉시 생성, 백그라운드 큐에서 순차 처리
- `asyncio.Queue` 기반 — 별도 인프라(Redis/Celery) 없이 FastAPI 프로세스 내 동작

### 4.4 prompt_templates (프롬프트 템플릿)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| analysis_type | VARCHAR UNIQUE | subsidiary / rnd / national_tech |
| label | VARCHAR | 표시명 (예: "종속회사 변동 분석") |
| system_prompt | TEXT | 시스템 프롬프트 |
| user_prompt_template | TEXT | 유저 프롬프트 템플릿 ({corp_name}, {fiscal_year}, {report_text} 플레이스홀더) |
| updated_at | DATETIME | 수정일 |

- 앱 시작 시 기본 프롬프트 자동 시딩 (DB에 없을 때만)
- �� UI에서 실시간 편집 → 서버 재시작 없이 즉시 반영

### 파일 저장 구조

```
data/reports/
  └── {corp_code}/
      └── {year}/
          ├── {rcept_no}.zip          # 원본 ZIP
          └── extracted/              # 추출된 문서
              └── *.xml / *.html
```

---

## 5. API 엔드포인트

### 5.1 기업 관리 — `/api/companies`

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/companies` | 등록된 기업 목록 조회 |
| POST | `/api/companies` | 기업 등록 (기업명 → DART 코드 자동 조회) |
| PUT | `/api/companies/{id}` | 기업 정보 수정 |
| DELETE | `/api/companies/{id}` | 기업 삭제 (관련 보고서/분석도 CASCADE 삭제) |
| GET | `/api/companies/search?name={name}` | OpenDART에서 기업명으로 검색 |

### 5.2 보고서 관리 — `/api/reports`

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/companies/{id}/reports` | 해당 기업의 보고서 목록 |
| POST | `/api/companies/{id}/reports/download` | 보고서 다운로드 요청 (연도/유형 지정) |
| GET | `/api/companies/{id}/reports/check` | DART에서 새 보고서 존재 여부 확인 |
| GET | `/api/reports/{id}/content` | 보고서 원문 텍스트 조회 |

### 5.3 ���석 — `/api/analyses`

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/reports/{id}/analyze` | 분석 큐에 추가 (body: `{ "analysis_type": "subsidiary" }`). 즉시 반환, 백그라운드 처리 |
| POST | `/api/companies/{id}/analyze-all` | 해당 기업의 전체 보고서 × 전체 분석 유형을 일괄 큐에 추가 |
| GET | `/api/reports/{id}/analyses` | 해당 보고서의 분석 결과 목록 (status 포함) |
| GET | `/api/analyses/{id}` | 분석 결과 상세 조회 |
| GET | `/api/companies/{id}/analyses` | 기업의 전체 분석 결과 (연도별 종합, status 포함) |
| GET | `/api/queue/status` | 큐 상태 (대기 건수, 현재 처리 중인 분석 정보) |

### 5.4 스케줄러 — `/api/scheduler`

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/scheduler/status` | 스케줄러 상태 (다음 실행 시각 등) |
| POST | `/api/scheduler/run-now` | 즉시 전체 기업 보고서 체크 실행 |

### 5.5 프롬프트 관리 — `/api/prompts`

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/prompts` | 전체 프롬프트 템플릿 목록 |
| GET | `/api/prompts/{analysis_type}` | 특정 분석 유형의 프롬프트 조회 |
| PUT | `/api/prompts/{analysis_type}` | 프롬프트 수정 (system_prompt, user_prompt_template) |

---

## 6. 화면 구성

### 6.1 메인 — 기업 목록 대시보드 (`/`)

- 등록된 기업 테이블 (기업명, 종목코드, 보고서 수, 최근 분석일, 상태)
- 기업명 검색 필터
- 스케줄러 상태 표시 (동작중/정지)
- 기업 등록 버튼 → 모달에서 OpenDART 검색 후 선택

### 6.2 기업 상세 페이지 (`/companies/:id`)

- 상단: 기업 정보 (기업명, 종목코드, DART 코드), 보고서 다운로드/수정 버튼
- 탭 구성:
  - **보고서 탭** — 보고서 목록 테이블 (보고서명, 유형, 연도, 공시일, 분석 진행률)
  - **종속회사 분석 탭** — 연도 선택, 분석 결과 표시 (요약/신규 편입/제외/시사점)
  - **R&D/투자 분석 탭** — 연도 선택, 핵심 기술/시설/유무형 투자/전략 분석
  - **국가전략기술 탭** — 연도 선택, 국가전략기술 관련 사업/연구 분석

### 6.3 분석 결과 뷰 (탭 내부)

- 연도 선택 UI (칩/태그 형태)
- 분석 결과 마크다운 렌더링
- 재분석 버튼, PDF 출력 버튼 (`window.print()`)
- "전체 비교" 모드 — 선택된 연도들의 분석 결과 나란히 비교

### 6.4 프롬프트 설정 페이지 (`/settings/prompts`)

- 3개 분석 유형별 프롬프트 카드 표시
- 각 카드에 시스템 프롬프트 / 유저 프롬프트 텍스트에어리어
- 플레이스홀더 안내: `{corp_name}`, `{fiscal_year}`, `{report_text}`
- 저장 버튼 → 즉시 반영 (서버 재시작 불필요)
- 상단 네비게이션에 "설정" 링크 추가

### 페이지 흐름

```
메인 (기업 목록) → 기업 상세 (보고서 + 탭) → 분석 결과 (탭 내 콘텐츠) → PDF 출력
                 → 설정 (프롬프트 편집)
```

---

## 7. 핵심 로직

### 7.1 기업 등록 플로우

1. 사용자가 기업명 입력
2. `/api/companies/search` → OpenDART `corpCode.xml` 에서 기업명 검색
3. 검색 결과 목록 표시, 사용자가 선택
4. 선택된 기업의 `corp_code`, `corp_name`, `stock_code`를 DB에 저장

### 7.2 보고서 다운로드 플로우

1. OpenDART 공시검색 API(`list.json`)로 해당 기업의 보고서 목록 조회
2. 사용자가 연도/유형 선택 또는 스케줄러가 자동 체크
3. OpenDART 문서 다운로드 API(`document.xml`)로 ZIP 다운로드
4. ZIP 해제 → 텍스트 추출 → `data/reports/{corp_code}/{year}/` 저장
5. DB `reports` 테이블에 메타데이터 기록

### 7.3 Gemini 분석 플로우

1. 보고서 원문 텍스트를 로드
2. 분석 유형별 프롬프트 구성 (시스템 프롬프트 + 보고서 전문)
3. Gemini API 호출 (모델: `gemini-2.0-flash-preview`, 1M 컨텍스트 활용)
4. 응답을 구조화된 JSON + 요약 마크다운으로 파싱
5. DB `analyses` 테이블에 UPSERT

### 7.4 스케줄러

- APScheduler `IntervalTrigger` 사용, 기본 24시간 주기 (환경변수로 설정)
- 등록된 활성 기업 순회 → OpenDART에서 새 보고서 존재 여부 체크
- 새 보고서 발견 시 자동 다운로드

---

## 8. Docker 구성

### 컨테이너 구조

```yaml
services:
  backend:
    # Python 3.12-slim 기반
    # FastAPI + APScheduler
    # SQLite 파일 + data/reports/ 볼륨 마운트
    ports: "8016:8000"
    volumes:
      - ./data:/app/data    # SQLite DB + 보고서 파일

  frontend:
    # Node 빌드 → Nginx 서빙 (multi-stage)
    ports: "8097:80"
```

### 경량화 전략

- **backend**: `python:3.12-slim` 기반, 불필요한 패키지 최소화
- **frontend**: multi-stage 빌드 (Node로 빌드 → `nginx:alpine`으로 서빙)
- **DB 별도 컨테이너 없음**: SQLite는 backend 볼륨에 포함
- **Celery/Redis 불필요**: APScheduler가 FastAPI 프로세스 내에서 동작

---

## 9. 프로젝트 디렉터리 구조

```
16_firm-dart-analysis/
├── docker-compose.yml
├── .env
├── .gitignore
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py              # FastAPI 앱 + APScheduler 초기화
│   │   ├── config.py            # 환경변수 설정
│   │   ├── database.py          # SQLite 연결 + 테이블 생성
│   │   ├── models.py            # SQLAlchemy 모델
│   │   ├── routers/
│   │   │   ├── companies.py     # 기업 관리 API
│   │   │   ├── reports.py       # 보고서 관리 API
│   │   │   ├── analyses.py      # 분석 API
│   │   │   └── scheduler.py     # 스케줄러 API
│   │   ├── services/
│   │   │   ├── dart_client.py   # OpenDART API 클라이언트
│   │   │   ├── gemini_client.py # Gemini API 클라이언트
│   │   │   ├── report_service.py    # 보고서 다운로드/추출
│   │   │   └── analysis_service.py  # 분석 실행 로직
│   │   ├── prompts/
│   │   │   ├── subsidiary.py    # 종속회사 분석 프롬프트
│   │   │   ├── rnd.py           # R&D/투자 분석 프롬프트
│   │   │   └── national_tech.py # 국가전략기술 분석 프롬프트
│   │   └── scheduler.py        # APScheduler 작업 정의
│   └── data/                    # 볼륨 마운트 대상
│       ├── db.sqlite3
│       └── reports/
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── api/                 # API 호출 함수
│       │   └── client.ts
│       ├── pages/
│       │   ├── CompanyList.tsx   # 메인 — 기업 목록
│       │   └── CompanyDetail.tsx # 기업 상세 (탭 포함)
│       └── components/
│           ├── CompanyForm.tsx       # 기업 등록/수정 모달
│           ├── ReportTable.tsx       # 보고서 목록 테이블
│           ├── AnalysisView.tsx      # 분석 결과 뷰
│           └── PrintableReport.tsx   # PDF 출력용 레이아웃
└── docs/
```
