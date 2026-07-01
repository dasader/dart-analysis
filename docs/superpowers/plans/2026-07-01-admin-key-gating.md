# 관리자키 기반 관리 기능 게이팅 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단일 관리자키(.env `ADMIN_KEY`)로 파괴적 삭제·재다운로드·LLM 분석·프롬프트 수정·스케줄러 수동 실행을 백엔드에서 잠그고, 프론트에서는 미로그인 시 해당 버튼을 비활성화 + 안내한다.

**Architecture:** 백엔드는 FastAPI `require_admin` 의존성을 관리 라우트에 부착하고 `X-Admin-Key` 헤더를 `settings.admin_key`와 비교한다(키 미설정 시 인증 비활성). 프론트는 관리자키를 `localStorage`에 저장하고 fetch 래퍼가 헤더를 자동 첨부하며, React Context(`useAdmin`)로 `isAdmin`을 관리해 `AdminButton`이 미로그인 시 버튼을 비활성화한다.

**Tech Stack:** 백엔드 FastAPI 0.115 / pydantic-settings / pytest(신규) + httpx TestClient. 프론트 React 19 / react-router 7 / TypeScript / Tailwind v4.

## Global Constraints

- 백엔드는 `python -m uvicorn`(Python 3.14) 환경. 테스트는 `cd backend && python -m pytest`로 실행.
- `settings.admin_key`가 빈 문자열이면 인증 **비활성화**(모든 관리 요청 통과) — 기존 개발 환경 하위호환 필수.
- 프론트 타입 검사는 Docker 빌드와 동일한 `npm run typecheck`(`tsc -b`)로 검증 — `npx tsc --noEmit` 아님.
- 관리자 미로그인 시 버튼은 **숨기지 말고** `disabled` + `title="관리자 로그인이 필요합니다"`.
- 관리자 안내 문구 문자열은 정확히 `관리자 로그인이 필요합니다` (버튼 툴팁), 배너는 `관리 기능을 사용하려면 우측 상단에서 관리자 로그인이 필요합니다.`
- localStorage 키 이름은 정확히 `dart_admin_key`, 요청 헤더 이름은 정확히 `X-Admin-Key`.

## 권한 분류 (구현 기준)

**관리자 전용 (require_admin 부착):**
- `DELETE /api/companies/{company_id}`
- `DELETE /api/reports/{report_id}`
- `POST /api/reports/{report_id}/redownload`
- `POST /api/reports/{report_id}/analyze`
- `POST /api/reports/{report_id}/analyze-all`
- `POST /api/companies/{company_id}/analyze-all`
- `POST /api/scheduler/run-now`
- `PUT /api/prompts/{analysis_type}`
- `DELETE /api/tags/{tag_id}`

**공개 (변경 없음):** 모든 GET, `POST/PUT /api/companies`, `POST/PUT /api/tags`, `POST /api/companies/{id}/reports/download`, `POST` 및 `DELETE /api/companies/{id}/tags/{tag_id}`(태그 할당/해제).

## 파일 구조

**백엔드**
- Create: `backend/app/dependencies.py` — `require_admin` 의존성 (책임: 관리자 인증 1가지)
- Create: `backend/app/routers/admin.py` — `GET /api/admin/verify` (책임: 키 검증 엔드포인트)
- Create: `backend/tests/__init__.py`, `backend/tests/conftest.py`, `backend/tests/test_admin_auth.py`
- Modify: `backend/app/config.py` (admin_key 추가), `backend/app/main.py` (admin 라우터 등록)
- Modify: 관리 라우트에 의존성 부착 — `routers/companies.py`, `routers/reports.py`, `routers/analyses.py`, `routers/scheduler.py`, `routers/prompts.py`, `routers/tags.py`
- Modify: `backend/requirements.txt` (pytest 추가), 루트 `.env.example` (ADMIN_KEY 추가)

**프론트엔드**
- Create: `frontend/src/lib/adminKey.ts` — localStorage 접근 (책임: 키 저장소)
- Create: `frontend/src/context/AdminContext.tsx` — `AdminProvider` + `useAdmin` (책임: 인증 상태)
- Create: `frontend/src/components/AdminButton.tsx` — 미로그인 시 비활성화 버튼 (책임: 게이팅 UI)
- Modify: `frontend/src/api/client.ts` (헤더 주입 + `verifyAdminKey`), `frontend/src/main.tsx` (Provider 래핑), `frontend/src/components/Layout.tsx` (로그인/로그아웃 UI)
- Modify: 관리 버튼 보유 컴포넌트 — `pages/CompanyList.tsx`, `pages/CompanyDetail.tsx`, `components/ReportTable.tsx`, `components/AnalysisView.tsx`, `pages/PromptSettings.tsx`, `pages/TagSettings.tsx`

---

## Task 1: 백엔드 관리자 인증 의존성 + 검증 엔드포인트

**Files:**
- Create: `backend/app/dependencies.py`
- Create: `backend/app/routers/admin.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_admin_auth.py`
- Modify: `backend/app/config.py:6-14`
- Modify: `backend/app/main.py:14-16,55-60`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces: `app.dependencies.require_admin(x_admin_key: str | None = Header(default=None)) -> None` — `settings.admin_key`가 비면 무조건 통과, 아니면 헤더 불일치 시 `HTTPException(401)`.
- Produces: `GET /api/admin/verify` — `require_admin` 통과 시 `{"ok": true}`.
- Consumes: `app.config.settings.admin_key` (이 태스크에서 추가).

- [ ] **Step 1: pytest 의존성 추가**

`backend/requirements.txt` 끝에 한 줄 추가:

```
pytest==8.3.4
```

- [ ] **Step 2: config에 admin_key 추가**

`backend/app/config.py`의 `Settings` 클래스에서 `analysis_interval_secs` 아래(`data_dir` 위)에 필드를 추가한다. 수정 후 6-15행 형태:

```python
class Settings(BaseSettings):
    opendart_api_key: str
    gemini_api_key: str
    backend_port: int = 8016
    frontend_port: int = 8097
    scheduler_interval_hours: int = 24
    # Gemini 3 flash preview TPM 한도: 2M tokens/min
    # 요청당 ~850K 토큰 기준 → 분당 2건 → 30초 간격
    analysis_interval_secs: int = 30
    # 관리자 키 — 비어 있으면 인증 비활성화(모든 관리 요청 통과)
    admin_key: str = ""
    data_dir: Path = Path("/app/data")
```

- [ ] **Step 3: require_admin 의존성 생성**

`backend/app/dependencies.py` 생성:

```python
from fastapi import Header, HTTPException

from app.config import settings


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """관리자 인증. admin_key 미설정 시 통과(인증 비활성화), 설정 시 헤더 일치 필요."""
    if not settings.admin_key:
        return
    if x_admin_key != settings.admin_key:
        raise HTTPException(status_code=401, detail="관리자 인증이 필요합니다.")
```

- [ ] **Step 4: admin 검증 라우터 생성**

`backend/app/routers/admin.py` 생성:

```python
from fastapi import APIRouter, Depends

from app.dependencies import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/verify", dependencies=[Depends(require_admin)])
def verify_admin():
    """관리자 키 검증용. require_admin 통과 시 200."""
    return {"ok": True}
```

- [ ] **Step 5: main.py에 admin 라우터 등록**

`backend/app/main.py:14`의 import 라인을 수정:

```python
from app.routers import companies, reports, analyses, scheduler
```
→
```python
from app.routers import companies, reports, analyses, scheduler, admin
```

그리고 `app.include_router(tags_router.router)` (60행) 아래에 추가:

```python
app.include_router(admin.router)
```

- [ ] **Step 6: 테스트 부트스트랩 생성**

`backend/tests/__init__.py` 생성 (빈 파일):

```python
```

`backend/tests/conftest.py` 생성 (app import 전에 필수 키를 환경에 주입 — .env 없이도 import 성공):

```python
import os

os.environ.setdefault("OPENDART_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("DATA_DIR", "./data")
```

- [ ] **Step 7: require_admin 단위 테스트 작성 (실패 확인용)**

`backend/tests/test_admin_auth.py` 생성:

```python
import pytest
from fastapi import HTTPException

from app.config import settings
from app.dependencies import require_admin


def test_disabled_when_key_empty(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "")
    assert require_admin(None) is None
    assert require_admin("anything") is None


def test_rejects_missing_header(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "secret")
    with pytest.raises(HTTPException) as exc:
        require_admin(None)
    assert exc.value.status_code == 401


def test_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "secret")
    with pytest.raises(HTTPException) as exc:
        require_admin("wrong")
    assert exc.value.status_code == 401


def test_accepts_correct_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "secret")
    assert require_admin("secret") is None
```

- [ ] **Step 8: 테스트 실행 — 통과 확인**

Run: `cd backend && python -m pytest tests/test_admin_auth.py -v`
Expected: 4개 PASS (`test_disabled_when_key_empty`, `test_rejects_missing_header`, `test_rejects_wrong_key`, `test_accepts_correct_key`).

- [ ] **Step 9: 커밋**

```bash
cd /home/dev/code/dart
git add backend/app/config.py backend/app/dependencies.py backend/app/routers/admin.py backend/app/main.py backend/requirements.txt backend/tests
git commit -m "feat(backend): add admin key auth dependency and verify endpoint"
```

---

## Task 2: 관리 라우트에 require_admin 부착 + 통합 테스트

**Files:**
- Modify: `backend/app/routers/companies.py:104,111`(delete_company 데코레이터) — delete_company만
- Modify: `backend/app/routers/reports.py:115,122`
- Modify: `backend/app/routers/analyses.py:55,78,99`
- Modify: `backend/app/routers/scheduler.py:20`
- Modify: `backend/app/routers/prompts.py:28`
- Modify: `backend/app/routers/tags.py:41`
- Modify: `backend/tests/test_admin_auth.py`
- Modify: 루트 `.env.example`

**Interfaces:**
- Consumes: `app.dependencies.require_admin` (Task 1).
- 각 관리 라우트에 `dependencies=[Depends(require_admin)]`를 데코레이터에 추가. `Depends`는 이미 각 라우터에 import되어 있음(scheduler.py 제외 — 아래에서 import 추가).

- [ ] **Step 1: companies.py — delete_company 보호**

`backend/app/routers/companies.py`의 `require_admin` import를 상단 import 블록(15행 `from app.services.dart_client import search_companies` 아래)에 추가:

```python
from app.dependencies import require_admin
```

`Depends`는 3행에서 이미 import됨. `delete_company` 데코레이터(104행)를 수정:

```python
@router.delete("/{company_id}", status_code=204)
```
→
```python
@router.delete("/{company_id}", status_code=204, dependencies=[Depends(require_admin)])
```

`create_company`, `update_company`, `assign_tag`, `remove_tag`는 **공개이므로 변경하지 않는다.**

- [ ] **Step 2: reports.py — delete/redownload 보호**

`backend/app/routers/reports.py`의 import 블록(21행 `)` 아래, `router =` 위)에 추가:

```python
from app.dependencies import require_admin
```

`delete_report`(115행) 데코레이터:

```python
@router.delete("/api/reports/{report_id}", status_code=204, dependencies=[Depends(require_admin)])
```

`redownload_report`(122행) 데코레이터:

```python
@router.post("/api/reports/{report_id}/redownload", response_model=ReportResponse, dependencies=[Depends(require_admin)])
```

`download_reports`(보고서 수집, 52행)는 **공개이므로 변경하지 않는다.**

- [ ] **Step 3: analyses.py — analyze 3종 보호**

`backend/app/routers/analyses.py`의 import 블록(11행 아래)에 추가:

```python
from app.dependencies import require_admin
```

`analyze_report`(55행):

```python
@router.post("/api/reports/{report_id}/analyze", response_model=AnalysisResponse, dependencies=[Depends(require_admin)])
```

`analyze_report_all`(78행):

```python
@router.post("/api/reports/{report_id}/analyze-all", dependencies=[Depends(require_admin)])
```

`analyze_all`(99행):

```python
@router.post("/api/companies/{company_id}/analyze-all", dependencies=[Depends(require_admin)])
```

- [ ] **Step 4: scheduler.py — run-now 보호**

`backend/app/routers/scheduler.py` 1행 import를 수정:

```python
from fastapi import APIRouter
```
→
```python
from fastapi import APIRouter, Depends
```

import 블록(5행 아래)에 추가:

```python
from app.dependencies import require_admin
```

`run_now`(20행) 데코레이터:

```python
@router.post("/run-now", dependencies=[Depends(require_admin)])
```

- [ ] **Step 5: prompts.py — update_prompt 보호**

`backend/app/routers/prompts.py`의 import 블록(6행 아래)에 추가:

```python
from app.dependencies import require_admin
```

`update_prompt`(28행) 데코레이터:

```python
@router.put("/{analysis_type}", response_model=PromptTemplateResponse, dependencies=[Depends(require_admin)])
```

- [ ] **Step 6: tags.py — delete_tag 보호**

`backend/app/routers/tags.py`의 import 블록(7행 아래)에 추가:

```python
from app.dependencies import require_admin
```

`delete_tag`(41행) 데코레이터:

```python
@router.delete("/{tag_id}", status_code=204, dependencies=[Depends(require_admin)])
```

`create_tag`, `update_tag`는 **공개이므로 변경하지 않는다.**

- [ ] **Step 7: 통합 테스트 추가 (실패 확인용)**

`backend/tests/test_admin_auth.py` 끝에 추가한다. TestClient를 `with` 없이 생성하면 lifespan(스케줄러/DB 시딩)이 실행되지 않으며, `require_admin`이 401을 먼저 반환하므로 DB 테이블 없이도 검증된다.

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PROTECTED = [
    ("delete", "/api/tags/1"),
    ("delete", "/api/reports/1"),
    ("delete", "/api/companies/1"),
    ("post", "/api/reports/1/redownload"),
    ("post", "/api/reports/1/analyze-all"),
    ("post", "/api/companies/1/analyze-all"),
    ("post", "/api/scheduler/run-now"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_protected_routes_401_without_key(monkeypatch, method, path):
    monkeypatch.setattr(settings, "admin_key", "secret")
    resp = getattr(client, method)(path)
    assert resp.status_code == 401


def test_verify_ok_with_correct_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "secret")
    resp = client.get("/api/admin/verify", headers={"X-Admin-Key": "secret"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_verify_401_with_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "secret")
    resp = client.get("/api/admin/verify", headers={"X-Admin-Key": "nope"})
    assert resp.status_code == 401
```

- [ ] **Step 8: 전체 테스트 실행 — 통과 확인**

Run: `cd backend && python -m pytest tests/ -v`
Expected: Task 1의 4개 + 통합 테스트(7개 파라미터 + verify 2개) 모두 PASS.

- [ ] **Step 9: .env.example에 ADMIN_KEY 추가**

루트 `.env.example`의 `ANALYSIS_INTERVAL_SECS=30` 아래에 추가:

```
# 관리자 키 — 설정 시 삭제·분석 등 관리 기능에 X-Admin-Key 헤더 필요
# 비워두면 인증 비활성화(모든 요청 허용, 개발용)
ADMIN_KEY=
```

- [ ] **Step 10: 커밋**

```bash
cd /home/dev/code/dart
git add backend/app/routers backend/tests/test_admin_auth.py .env.example
git commit -m "feat(backend): gate destructive and LLM routes behind require_admin"
```

---

## Task 3: 프론트 관리자키 저장소 + fetch 헤더 주입

**Files:**
- Create: `frontend/src/lib/adminKey.ts`
- Modify: `frontend/src/api/client.ts:16-29` (request 래퍼), 파일 끝(verifyAdminKey 추가)

**Interfaces:**
- Produces: `getAdminKey(): string | null`, `setAdminKey(key: string): void`, `clearAdminKey(): void` (localStorage 키 `dart_admin_key`).
- Produces: `verifyAdminKey(key: string): Promise<boolean>` — `GET /api/admin/verify`에 `X-Admin-Key` 헤더로 검증, `resp.ok` 반환.
- `request()`는 저장된 키가 있으면 모든 요청에 `X-Admin-Key`를 자동 첨부.

- [ ] **Step 1: adminKey 저장소 생성**

`frontend/src/lib/adminKey.ts` 생성:

```ts
const STORAGE_KEY = "dart_admin_key";

export function getAdminKey(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setAdminKey(key: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, key);
  } catch {
    /* localStorage 불가 환경 무시 */
  }
}

export function clearAdminKey(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* noop */
  }
}
```

- [ ] **Step 2: request 래퍼에 헤더 주입**

`frontend/src/api/client.ts` 상단(16행 `const BASE = "/api";` 위)에 import 추가:

```ts
import { getAdminKey } from "../lib/adminKey";
```

`request` 함수(18-29행)를 다음으로 교체:

```ts
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const adminKey = getAdminKey();
  const resp = await fetch(`${BASE}${url}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(adminKey ? { "X-Admin-Key": adminKey } : {}),
      ...((init?.headers as Record<string, string> | undefined) ?? {}),
    },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}
```

- [ ] **Step 3: verifyAdminKey 추가**

`frontend/src/api/client.ts` 파일 맨 끝에 추가:

```ts
// --- Admin ---

export async function verifyAdminKey(key: string): Promise<boolean> {
  const resp = await fetch(`${BASE}/admin/verify`, {
    headers: { "X-Admin-Key": key },
  });
  return resp.ok;
}
```

- [ ] **Step 4: 타입 검사 — 통과 확인**

Run: `cd frontend && npm run typecheck`
Expected: 오류 없이 종료(exit 0).

- [ ] **Step 5: 커밋**

```bash
cd /home/dev/code/dart
git add frontend/src/lib/adminKey.ts frontend/src/api/client.ts
git commit -m "feat(frontend): store admin key and inject X-Admin-Key header"
```

---

## Task 4: AdminContext + 로그인/로그아웃 UI

**Files:**
- Create: `frontend/src/context/AdminContext.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/Layout.tsx`

**Interfaces:**
- Produces: `AdminProvider` (컴포넌트), `useAdmin(): { isAdmin: boolean; login: (key: string) => Promise<boolean>; logout: () => void }`.
- Consumes: `verifyAdminKey` (Task 3), `getAdminKey`/`setAdminKey`/`clearAdminKey` (Task 3).

- [ ] **Step 1: AdminContext 생성**

`frontend/src/context/AdminContext.tsx` 생성:

```tsx
import { createContext, useContext, useState, type ReactNode } from "react";
import { verifyAdminKey } from "../api/client";
import { getAdminKey, setAdminKey, clearAdminKey } from "../lib/adminKey";

interface AdminContextValue {
  isAdmin: boolean;
  login: (key: string) => Promise<boolean>;
  logout: () => void;
}

const AdminContext = createContext<AdminContextValue | null>(null);

export function AdminProvider({ children }: { children: ReactNode }) {
  // 저장된 키가 있으면 관리자 상태로 시작(요청 시 401이면 재로그인 유도)
  const [isAdmin, setIsAdmin] = useState<boolean>(() => getAdminKey() !== null);

  const login = async (key: string): Promise<boolean> => {
    const ok = await verifyAdminKey(key);
    if (ok) {
      setAdminKey(key);
      setIsAdmin(true);
    }
    return ok;
  };

  const logout = () => {
    clearAdminKey();
    setIsAdmin(false);
  };

  return (
    <AdminContext.Provider value={{ isAdmin, login, logout }}>
      {children}
    </AdminContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAdmin(): AdminContextValue {
  const ctx = useContext(AdminContext);
  if (!ctx) throw new Error("useAdmin must be used within AdminProvider");
  return ctx;
}
```

- [ ] **Step 2: main.tsx에서 Provider 래핑**

`frontend/src/main.tsx`를 다음으로 교체:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AdminProvider } from "./context/AdminContext";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AdminProvider>
        <App />
      </AdminProvider>
    </BrowserRouter>
  </StrictMode>,
);
```

- [ ] **Step 3: Layout에 로그인/로그아웃 UI 추가**

`frontend/src/components/Layout.tsx` 상단 import에 추가(3행 `import { fetchSchedulerStatus }` 아래):

```tsx
import { useAdmin } from "../context/AdminContext";
```

컴포넌트 본문 `const [scheduler, setScheduler] = ...` 아래에 추가:

```tsx
  const { isAdmin, login, logout } = useAdmin();

  const handleLogin = async () => {
    const key = window.prompt("관리자 키를 입력하세요");
    if (!key) return;
    const ok = await login(key);
    if (!ok) alert("관리자 키가 올바르지 않습니다.");
  };
```

nav 영역의 `설정` Link(45-50행) 아래, `</div>`(51행) 앞에 로그인/로그아웃 버튼을 추가:

```tsx
            {isAdmin ? (
              <button onClick={logout} className="nav-link">
                관리자 로그아웃
              </button>
            ) : (
              <button onClick={handleLogin} className="nav-link">
                관리자 로그인
              </button>
            )}
```

- [ ] **Step 4: 타입 검사 — 통과 확인**

Run: `cd frontend && npm run typecheck`
Expected: 오류 없이 종료(exit 0).

- [ ] **Step 5: 커밋**

```bash
cd /home/dev/code/dart
git add frontend/src/context/AdminContext.tsx frontend/src/main.tsx frontend/src/components/Layout.tsx
git commit -m "feat(frontend): add admin context and login/logout UI"
```

---

## Task 5: AdminButton으로 관리 버튼 게이팅 + 안내 배너

**Files:**
- Create: `frontend/src/components/AdminButton.tsx`
- Modify: `frontend/src/pages/CompanyList.tsx:245-250`
- Modify: `frontend/src/pages/CompanyDetail.tsx:212-229`
- Modify: `frontend/src/components/ReportTable.tsx:122-148`
- Modify: `frontend/src/components/AnalysisView.tsx:194-200,213-221,249-257`
- Modify: `frontend/src/pages/PromptSettings.tsx:107-113` (+ 배너)
- Modify: `frontend/src/pages/TagSettings.tsx:167-169` (+ 배너)

**Interfaces:**
- Produces: `AdminButton` — `<button>`과 동일한 props를 받되, `useAdmin().isAdmin`이 false면 `disabled` + `title="관리자 로그인이 필요합니다"`. 기존 `disabled`/`title`은 관리자일 때 유지.
- Consumes: `useAdmin` (Task 4).

- [ ] **Step 1: AdminButton 컴포넌트 생성**

`frontend/src/components/AdminButton.tsx` 생성:

```tsx
import type { ButtonHTMLAttributes } from "react";
import { useAdmin } from "../context/AdminContext";

const ADMIN_HINT = "관리자 로그인이 필요합니다";

export default function AdminButton({
  disabled,
  title,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  const { isAdmin } = useAdmin();
  const blocked = !isAdmin;
  return (
    <button
      {...rest}
      disabled={disabled || blocked}
      title={blocked ? ADMIN_HINT : title}
      className={`${className ?? ""} disabled:cursor-not-allowed disabled:opacity-50`}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 2: CompanyList 삭제 버튼 교체**

`frontend/src/pages/CompanyList.tsx` import에 추가(8행 `import type { Company, Tag }` 위):

```tsx
import AdminButton from "../components/AdminButton";
```

삭제 버튼(245-250행)을 교체:

```tsx
                      <button
                        onClick={() => handleDelete(c)}
                        className="btn btn-text-danger"
                      >
                        삭제
                      </button>
```
→
```tsx
                      <AdminButton
                        onClick={() => handleDelete(c)}
                        className="btn btn-text-danger"
                      >
                        삭제
                      </AdminButton>
```

`수정` 버튼은 공개이므로 그대로 둔다.

- [ ] **Step 3: CompanyDetail 전체 분석 + 삭제 버튼 교체**

`frontend/src/pages/CompanyDetail.tsx` import에 추가(19행 `import TagChip` 아래):

```tsx
import AdminButton from "../components/AdminButton";
```

전체 분석 버튼(212-223행)을 교체:

```tsx
            <button
              disabled={analyzing}
              onClick={() => {
                setAnalyzing(true);
                runWithToast(async () => (await analyzeAll(companyId)).message).finally(
                  () => setAnalyzing(false),
                );
              }}
              className="btn btn-ghost-accent"
            >
              {analyzing ? "요청 중..." : "전체 분석"}
            </button>
```
→
```tsx
            <AdminButton
              disabled={analyzing}
              onClick={() => {
                setAnalyzing(true);
                runWithToast(async () => (await analyzeAll(companyId)).message).finally(
                  () => setAnalyzing(false),
                );
              }}
              className="btn btn-ghost-accent"
            >
              {analyzing ? "요청 중..." : "전체 분석"}
            </AdminButton>
```

삭제 버튼(224-229행)을 교체:

```tsx
            <button
              onClick={handleDelete}
              className="btn btn-danger"
            >
              삭제
            </button>
```
→
```tsx
            <AdminButton
              onClick={handleDelete}
              className="btn btn-danger"
            >
              삭제
            </AdminButton>
```

`보고서 다운로드` 버튼(206-211행)과 태그 할당/해제는 공개이므로 그대로 둔다. `ReportTable`에 넘기는 `onAnalyze`/`onDelete`/`onRedownload` 콜백은 Task 5 Step 4에서 버튼 자체를 게이팅하므로 여기서는 변경 불필요.

- [ ] **Step 4: ReportTable 분석/재다운로드/삭제 버튼 교체**

`frontend/src/components/ReportTable.tsx` import에 추가(4행 `import { useSort, SortIcon }` 아래):

```tsx
import AdminButton from "./AdminButton";
```

분석 버튼(122-128행)을 교체:

```tsx
                        <button
                          disabled={analyzing || busyId === r.id}
                          onClick={() => onAnalyze(r.id)}
                          className="btn btn-link"
                        >
                          {analyzing ? "요청 중..." : "분석"}
                        </button>
```
→
```tsx
                        <AdminButton
                          disabled={analyzing || busyId === r.id}
                          onClick={() => onAnalyze(r.id)}
                          className="btn btn-link"
                        >
                          {analyzing ? "요청 중..." : "분석"}
                        </AdminButton>
```

재다운로드 버튼(130-141행)을 교체:

```tsx
                      <button
                        disabled={busyId === r.id}
                        onClick={async () => {
                          setBusyId(r.id);
                          try { await onRedownload(r.id); }
                          finally { setBusyId(null); }
                        }}
                        className="btn btn-text"
                        title="파일 재다운로드"
                      >
                        {busyId === r.id ? "..." : "재다운로드"}
                      </button>
```
→
```tsx
                      <AdminButton
                        disabled={busyId === r.id}
                        onClick={async () => {
                          setBusyId(r.id);
                          try { await onRedownload(r.id); }
                          finally { setBusyId(null); }
                        }}
                        className="btn btn-text"
                        title="파일 재다운로드"
                      >
                        {busyId === r.id ? "..." : "재다운로드"}
                      </AdminButton>
```

삭제 버튼(142-148행)을 교체:

```tsx
                      <button
                        disabled={busyId === r.id}
                        onClick={() => onDelete(r.id)}
                        className="btn btn-text-danger"
                      >
                        삭제
                      </button>
```
→
```tsx
                      <AdminButton
                        disabled={busyId === r.id}
                        onClick={() => onDelete(r.id)}
                        className="btn btn-text-danger"
                      >
                        삭제
                      </AdminButton>
```

- [ ] **Step 5: AnalysisView 분석 관련 버튼 교체**

`frontend/src/components/AnalysisView.tsx` import에 추가(4행 `import { analyzeReport }` 아래):

```tsx
import AdminButton from "./AdminButton";
```

재시도 버튼(194-200행)을 교체:

```tsx
          <button
            onClick={() => handleRun(selectedAnalysis.report_id)}
            className="btn btn-action mt-4"
          >
            재시도
          </button>
```
→
```tsx
          <AdminButton
            onClick={() => handleRun(selectedAnalysis.report_id)}
            className="btn btn-action mt-4"
          >
            재시도
          </AdminButton>
```

미분석 연도별 분석 버튼(213-221행)을 교체:

```tsx
                <button
                  key={r.id}
                  disabled={runningId === r.id}
                  onClick={() => handleRun(r.id)}
                  className="btn btn-action"
                >
                  {runningId === r.id ? "요청 중..." : `${r.fiscal_year} ${r.report_type} 분석`}
                </button>
```
→
```tsx
                <AdminButton
                  key={r.id}
                  disabled={runningId === r.id}
                  onClick={() => handleRun(r.id)}
                  className="btn btn-action"
                >
                  {runningId === r.id ? "요청 중..." : `${r.fiscal_year} ${r.report_type} 분석`}
                </AdminButton>
```

전체 재분석 버튼(249-256행)을 교체:

```tsx
              <button
                disabled={runningId === selectedReport.id}
                onClick={() => handleRun(selectedReport.id, true)}
                className="btn btn-outline btn-sm"
                title="3가지 분석 항목을 Gemini 1회 호출로 일괄 재분석"
              >
                {runningId === selectedReport.id ? "요청 중..." : "전체 재분석"}
              </button>
```
→
```tsx
              <AdminButton
                disabled={runningId === selectedReport.id}
                onClick={() => handleRun(selectedReport.id, true)}
                className="btn btn-outline btn-sm"
                title="3가지 분석 항목을 Gemini 1회 호출로 일괄 재분석"
              >
                {runningId === selectedReport.id ? "요청 중..." : "전체 재분석"}
              </AdminButton>
```

`PDF 출력` 버튼(258-266행)과 연도 칩(273-296행)은 공개이므로 그대로 둔다.

- [ ] **Step 6: PromptSettings 저장 버튼 교체 + 배너**

`frontend/src/pages/PromptSettings.tsx` import에 추가(4행 `import type { PromptTemplate }` 위):

```tsx
import AdminButton from "../components/AdminButton";
import { useAdmin } from "../context/AdminContext";
```

컴포넌트 본문 첫 줄(`const [prompts, setPrompts] = ...` 위)에 추가:

```tsx
  const { isAdmin } = useAdmin();
```

헤더 블록(`<div className="mb-8">...</div>`, 57-64행)의 닫는 `</div>`(64행) 바로 아래에 배너 추가:

```tsx
      {!isAdmin && (
        <div className="mb-6 rounded-lg border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">
          관리 기능을 사용하려면 우측 상단에서 관리자 로그인이 필요합니다.
        </div>
      )}
```

저장 버튼(107-113행)을 교체:

```tsx
                <button
                  onClick={() => handleSave(p.analysis_type)}
                  disabled={saving === p.analysis_type}
                  className="btn btn-primary"
                >
                  {saving === p.analysis_type ? "저장중..." : "저장"}
                </button>
```
→
```tsx
                <AdminButton
                  onClick={() => handleSave(p.analysis_type)}
                  disabled={saving === p.analysis_type}
                  className="btn btn-primary"
                >
                  {saving === p.analysis_type ? "저장중..." : "저장"}
                </AdminButton>
```

- [ ] **Step 7: TagSettings 삭제 버튼 교체 + 배너**

`frontend/src/pages/TagSettings.tsx` import에 추가(7행 `import { TAG_COLORS }` 아래):

```tsx
import AdminButton from "../components/AdminButton";
import { useAdmin } from "../context/AdminContext";
```

컴포넌트 본문 첫 줄(`const [tags, setTags] = ...` 위)에 추가:

```tsx
  const { isAdmin } = useAdmin();
```

헤더 블록(`<div className="mb-8">...</div>`, 66-71행)의 닫는 `</div>`(71행) 바로 아래에 배너 추가:

```tsx
      {!isAdmin && (
        <div className="mb-6 rounded-lg border border-warning/40 bg-warning-bg px-4 py-3 text-sm text-warning">
          관리 기능을 사용하려면 우측 상단에서 관리자 로그인이 필요합니다.
        </div>
      )}
```

삭제 버튼(167-169행)을 교체:

```tsx
                          <button onClick={() => handleDelete(tag)} className="btn btn-text-danger">
                            삭제
                          </button>
```
→
```tsx
                          <AdminButton onClick={() => handleDelete(tag)} className="btn btn-text-danger">
                            삭제
                          </AdminButton>
```

`추가`(create) 버튼과 `수정`/`저장`/`취소`(update) 버튼은 공개이므로 그대로 둔다.

- [ ] **Step 8: 타입 검사 — 통과 확인**

Run: `cd frontend && npm run typecheck`
Expected: 오류 없이 종료(exit 0).

- [ ] **Step 9: 수동 확인 (선택)**

백엔드 `.env`에 `ADMIN_KEY=test123` 설정 후 백엔드·프론트 기동. 미로그인 상태에서 삭제/분석 버튼이 비활성(회색) + hover 시 "관리자 로그인이 필요합니다" 표시 확인. 우측 상단 "관리자 로그인"에서 `test123` 입력 → 버튼 활성화 확인. 잘못된 키 입력 시 경고 확인.

- [ ] **Step 10: 커밋**

```bash
cd /home/dev/code/dart
git add frontend/src/components/AdminButton.tsx frontend/src/pages frontend/src/components
git commit -m "feat(frontend): disable admin-only buttons and show login guidance"
```

---

## 참고: 검증 요약

- 백엔드: `cd backend && python -m pytest tests/ -v` (Task 1·2)
- 프론트: `cd frontend && npm run typecheck` (Task 3·4·5)
- 통합 수동: `ADMIN_KEY` 설정 후 미로그인/로그인 상태의 버튼 동작 (Task 5 Step 9)
