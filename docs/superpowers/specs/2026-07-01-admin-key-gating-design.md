# 관리자키 기반 관리 기능 게이팅 설계

- 작성일: 2026-07-01
- 상태: 승인 대기

## 배경 및 목표

현재 백엔드의 모든 엔드포인트는 인증 없이 공개되어 있다(`main.py`에 CORS 미들웨어만 존재). 누구나 데이터를 삭제하거나 비용이 드는 Gemini 분석을 트리거할 수 있다.

목표: **단일 관리자키(.env)** 를 도입하여, 조회 및 기본 기능은 공개로 두되 **파괴적(삭제) 액션과 비용이 드는 LLM 분석 액션**을 관리자 전용으로 잠근다.

## 접근 모델

- 조회 기능과 기본 편집/다운로드는 공개.
- 관리자키가 입력되어야만 관리 기능이 UI에서 활성화되고 백엔드에서 작동.
- 키 방식: `.env`의 단일 `ADMIN_KEY`.

## 권한 분류

### 관리자 전용 (X-Admin-Key 헤더 필요)

| 그룹 | 엔드포인트 | 사유 |
|------|-----------|------|
| 삭제 | `DELETE /api/companies/{id}` | 파괴적 |
| 삭제 | `DELETE /api/reports/{id}` | 파괴적 |
| 삭제 | `DELETE /api/tags/{id}` | 파괴적 |
| 삭제 | `DELETE /api/companies/{id}/tags/{tag_id}` | 데이터 변경(태그 해제) |
| 재다운로드 | `POST /api/reports/{id}/redownload` | 기존 분석 초기화(파괴적) |
| LLM 분석 | `POST /api/reports/{id}/analyze` | Gemini 비용 |
| LLM 분석 | `POST /api/reports/{id}/analyze-all` | Gemini 비용 |
| LLM 분석 | `POST /api/companies/{id}/analyze-all` | Gemini 비용 |
| 스케줄러 | `POST /api/scheduler/run-now` | 수집+분석 트리거(비용) |
| 프롬프트 | `PUT /api/prompts/{type}` | 분석 동작을 전역으로 바꾸는 설정 |

### 공개 (키 불필요)

- 모든 `GET` 조회 엔드포인트 (기업/보고서/분석/큐 상태/스케줄러 상태/프롬프트 조회/태그)
- `POST /api/companies` (기업 등록), `PUT /api/companies/{id}` (기업 수정)
- `POST /api/tags` (태그 생성), `PUT /api/tags/{id}` (태그 수정)
- `POST /api/companies/{id}/tags/{tag_id}` (기업에 태그 할당)
- `POST /api/companies/{id}/reports/download` (보고서 수집·다운로드)
- `GET /api/reports/{id}/download` (ZIP 다운로드), `GET /api/reports/{id}/content` (본문 열람)

원칙: 비파괴적 create/edit는 공개, 파괴적 delete와 LLM 비용 액션은 관리자 전용.

## 기술 구현

### 백엔드

- `config.py`: `admin_key: str = ""` 추가 (환경변수 `ADMIN_KEY`에서 로드).
- `dependencies.py` 신설 — `require_admin()` FastAPI 의존성:
  - 요청 헤더 `X-Admin-Key`를 `settings.admin_key`와 비교. 불일치 시 `HTTPException(401)`.
  - `settings.admin_key`가 빈 문자열이면(.env 미설정) 인증 비활성화로 간주하여 전부 통과 → 기존 개발 환경 호환.
- 관리자 전용 라우트에 `dependencies=[Depends(require_admin)]` 부착.
- `GET /api/admin/verify` 추가 — 프론트 로그인 검증용. `require_admin` 통과 시 200, 실패 시 401. `admin_key` 미설정 시에도 200(인증 비활성 상태 알림 포함 가능).
- `.env.example`에 `ADMIN_KEY=` 항목 추가.

### 프론트엔드

- 관리자키를 `localStorage`에 저장.
- `api/client.ts` fetch 래퍼: 관리 요청 시 `X-Admin-Key` 헤더를 자동 첨부(저장된 키가 있으면 항상 첨부해도 무방).
- 전역 관리자 상태(`isAdmin`)를 React Context 또는 경량 store로 관리.
- 우상단 "관리자 로그인" 진입 → 키 입력 → `GET /api/admin/verify` 검증 → 성공 시 저장 및 `isAdmin=true`, 실패 시 오류 안내.
- 로그인 상태에서 "로그아웃"으로 키 제거 가능.

### 프론트 UX

- 관리 버튼(삭제, 분석, 재다운로드, 프롬프트 저장, 스케줄러 실행 등)은 **숨기지 않고 항상 표시하되 비활성화(disabled)**.
- 비활성 버튼 hover 시 툴팁/안내 문구: "관리자 로그인이 필요합니다".
- 관리 기능 집약 화면(프롬프트 설정, 태그 관리 등) 상단에 안내 배너.
- 로그인 성공 시 전 관리 기능 활성화, 실패 시 오류 안내.

## 영향 받는 파일

- 백엔드: `config.py`, `dependencies.py`(신설), `main.py`(admin verify 라우터 등록), `routers/companies.py`, `routers/reports.py`, `routers/analyses.py`, `routers/scheduler.py`, `routers/prompts.py`, `routers/tags.py`, `.env.example`
- 프론트엔드: `api/client.ts`, 관리자 상태 Context(신설), `components/`·`pages/` 중 관리 버튼 보유 컴포넌트(CompanyList, CompanyDetail, ReportTable, AnalysisView, PromptSettings, TagSettings), 헤더/레이아웃 컴포넌트(로그인 진입점)

## 테스트

- 백엔드: `admin_key` 미설정 시 관리 엔드포인트가 통과하는지, 설정 시 헤더 없음/오류 키 → 401, 정상 키 → 성공. 공개 엔드포인트는 키 없이 항상 200.
- 프론트: 미로그인 시 관리 버튼 비활성 + 안내 노출, 로그인 후 활성화, 잘못된 키 입력 시 오류.

## 비고 / 보안 한계

- 단일 공유키 방식이므로 사용자별 감사 추적은 불가(추후 필요 시 계정/세션 방식으로 확장).
- 키는 프론트 `localStorage`에 평문 저장되고 HTTPS 전제. 프로덕션에서는 TLS 필수.
