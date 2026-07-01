# 기업 DART 사업보고서 AI 분석 시스템

OpenDART API로 상장기업의 사업보고서를 수집하고, Google Gemini로 3가지 분석(종속회사 변동 / R&D·투자 / 국가전략기술)을 자동으로 수행하는 웹 서비스입니다.

## 주요 기능

- **기업 관리**: OpenDART 기업 검색 및 등록, 활성/비활성 관리
- **보고서 수집**: 사업보고서 수동 다운로드 / 스케줄러 자동 수집 (24시간 주기)
- **AI 분석**: Gemini 1회 호출로 3가지 분석 동시 처리, 비동기 큐 기반 처리
- **결과 조회**: 연도별 분석 결과 열람, PDF 출력 (선택 연도의 3개 분석 통합 출력)
- **프롬프트 관리**: 분석 유형별 시스템 프롬프트 편집
- **관리자 게이팅**: 관리자키(`ADMIN_KEY`)로 삭제·재다운로드·AI 분석·프롬프트 수정·스케줄러 수동 실행을 보호 (조회·다운로드·기업/태그 등록은 공개)

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 백엔드 | FastAPI, SQLAlchemy, SQLite, APScheduler |
| AI | Google Gemini (`gemini-3-flash-preview`) |
| 공시 데이터 | OpenDART API |
| 프론트엔드 | React, TypeScript, Vite, Tailwind CSS v4 |

## 시작하기

### 사전 요구사항

- Python 3.11+
- Node.js 18+
- [OpenDART API 키](https://opendart.fss.or.kr/intro/main.do)
- [Google Gemini API 키](https://aistudio.google.com/)

### 환경 변수 설정

프로젝트 루트에 `.env` 파일 생성:

```env
OPENDART_API_KEY=your_opendart_api_key
GEMINI_API_KEY=your_gemini_api_key
DATA_DIR=./data
BACKEND_PORT=8016
FRONTEND_PORT=8097
SCHEDULER_INTERVAL_HOURS=24
ANALYSIS_INTERVAL_SECS=30
ADMIN_KEY=                     # 관리 기능 보호용 키 (비우면 인증 비활성화)
```

### 로컬 개발 서버 실행

**백엔드**
```bash
cd backend
DATA_DIR=./data python -m uvicorn app.main:app --reload --port 8016
```

**프론트엔드**
```bash
cd frontend
npm install
npm run dev
```

- 프론트엔드: http://localhost:5185
- 백엔드 API 문서: http://localhost:8016/docs

### Docker Compose (프로덕션)

```bash
cp .env.example .env   # 환경 변수 편집 후
docker-compose up --build
```

- 프론트엔드: http://localhost:8097
- 백엔드: http://localhost:8016

## 사용 방법

1. **기업 등록**: 기업 목록 화면에서 `+ 기업 등록` → OpenDART 기업 검색 후 선택
2. **보고서 수집**: 기업 상세 → `보고서 다운로드` → 사업연도 선택
3. **AI 분석**: 보고서 목록에서 `분석` 버튼 클릭 (Gemini 1회 호출로 3종 동시 처리)
4. **결과 확인**: 종속회사 분석 / R&D·투자 분석 / 국가전략기술 탭에서 연도별 조회
5. **PDF 출력**: 분석 탭에서 `PDF 출력` 버튼 (선택 연도의 3개 분석 통합 출력)

## 관리자 기능 (게이팅)

`.env`에 `ADMIN_KEY`를 설정하면 위험·비용 액션이 관리자 전용으로 잠깁니다. 값을 비워두면 인증이 비활성화되어 기존처럼 모든 기능이 열립니다 (개발용).

- **관리자 전용** (키 필요): 기업·보고서·태그 **삭제**, 보고서 **재다운로드**, **AI 분석**(단건·일괄·전체), **프롬프트 수정**, **스케줄러 수동 실행**
- **공개** (키 불필요): 모든 조회, 보고서 수집·다운로드, 기업 등록/수정, 태그 생성/수정/할당·해제

**동작 방식**
- 백엔드: 관리 라우트에 관리자 인증 의존성이 붙어, 요청 헤더 `X-Admin-Key`가 `ADMIN_KEY`와 일치해야 통과 (불일치 시 401). `GET /api/admin/verify`로 키 검증.
- 프론트: 우측 상단 **관리자 로그인**에서 키 입력 → `localStorage` 저장 후 관리 요청에 헤더 자동 첨부. 미로그인 시 관리 버튼은 **비활성화**되고 "관리자 로그인이 필요합니다" 안내를 표시.

## 분석 항목

| 탭 | 분석 내용 |
|----|---------|
| 종속회사 변동 분석 | 연결대상 종속회사 신규 편입·제외, 지분율 변동 |
| R&D/투자 분석 | 연구개발비 규모·추이, 주요 투자 내역 |
| 국가전략기술 분석 | 반도체·배터리·바이오 등 국가전략기술 관련 사업 현황 |

## 주요 설정

| 항목 | 기본값 | 설명 |
|------|--------|------|
| `SCHEDULER_INTERVAL_HOURS` | 24 | 신규 보고서 자동 수집 주기 |
| `ANALYSIS_INTERVAL_SECS` | 30 | 보고서 간 Gemini 호출 최소 간격 (TPM 한도 대응) |
| `DATA_DIR` | `/app/data` | SQLite DB 및 보고서 파일 저장 경로 |
| `ADMIN_KEY` | (빈 값) | 관리 기능 보호용 키. 비우면 인증 비활성화 |

## 수집 대상 보고서

- **사업보고서만** 수집 (반기·분기보고서, 정정보고서 제외)
- 스케줄러는 DB에 사업보고서가 1건 이상 있는 기업만 대상으로 최신 연도 이후 신규 보고서 자동 수집

## 포트

| 서비스 | 포트 |
|--------|------|
| 백엔드 (FastAPI) | 8016 |
| 프론트엔드 prod (Nginx) | 8097 |
| 프론트엔드 dev (Vite) | 5185 |
