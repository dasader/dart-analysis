# 분석 상태 버그 수정 + 기업 태그 기능 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 분석 큐 투입 시 상태가 즉시 "완료"로 표시되는 버그를 수정하고, 기업에 색상 태그를 붙이고 목록에서 필터링하는 기능을 추가한다.

**Architecture:** SQLAlchemy M2M (`Tag` ↔ `Company` via `company_tags` 조인 테이블), FastAPI 라우터 신규 추가, React 상태 기반 필터·드롭다운 UI.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2.x, Pydantic v2, React 18, TypeScript, Tailwind v4

---

## 파일 맵

| 파일 | 작업 |
|------|------|
| `backend/app/models.py` | `company_tags` Table + `Tag` 모델 + `Company.tags` relationship 추가 |
| `backend/app/schemas.py` | `TagResponse/Create/Update` 추가, `CompanyResponse.tags` 필드 추가 |
| `backend/app/routers/companies.py` | 버그 수정 + `_build_company_response` 헬퍼 + 태그 할당/제거/필터 엔드포인트 |
| `backend/app/routers/reports.py` | 버그 수정 (`analysis_count` 필터) |
| `backend/app/routers/tags.py` | 신규 — 태그 CRUD |
| `backend/app/main.py` | `tags` 라우터 등록 |
| `frontend/src/types/index.ts` | `Tag` 인터페이스 추가, `Company.tags` 필드 추가, `TAG_COLORS` 상수 추가 |
| `frontend/src/api/client.ts` | 태그 API 함수 추가, `fetchCompanies` 시그니처 변경 |
| `frontend/src/pages/TagSettings.tsx` | 신규 — 태그 관리 페이지 |
| `frontend/src/App.tsx` | `/tags` 라우트 추가 |
| `frontend/src/components/Layout.tsx` | "태그 관리" 네비 링크 추가 |
| `frontend/src/pages/CompanyList.tsx` | 태그 필터 바 + 기업 행 태그 칩 |
| `frontend/src/pages/CompanyDetail.tsx` | 인라인 태그 할당/제거 UI |

---

## Task 1: 버그 수정 — 분석 상태 필터

**Files:**
- Modify: `backend/app/routers/companies.py:22`
- Modify: `backend/app/routers/reports.py:34`

- [ ] **Step 1: companies.py — `latest_analysis_date` 쿼리에 completed 필터 추가**

`backend/app/routers/companies.py` 의 `list_companies` 함수에서 L22 블록을:

```python
        latest = (
            db.query(func.max(Analysis.updated_at))
            .filter(Analysis.company_id == c.id)
            .scalar()
        )
```

다음으로 교체:

```python
        latest = (
            db.query(func.max(Analysis.updated_at))
            .filter(Analysis.company_id == c.id, Analysis.status == "completed")
            .scalar()
        )
```

- [ ] **Step 2: reports.py — `analysis_count` 쿼리에 completed 필터 추가**

`backend/app/routers/reports.py` 의 `get_reports` 함수에서 L34를:

```python
        count = db.query(func.count(Analysis.id)).filter(Analysis.report_id == r.id).scalar()
```

다음으로 교체:

```python
        count = db.query(func.count(Analysis.id)).filter(
            Analysis.report_id == r.id, Analysis.status == "completed"
        ).scalar()
```

- [ ] **Step 3: 백엔드 재시작 후 확인**

```bash
cd backend
DATA_DIR=./data python -m uvicorn app.main:app --reload --port 8016
```

분석 요청 후 기업 목록에서 상태가 "대기" 또는 "보고서만"으로 유지되는지 확인. 큐가 완료된 뒤에만 "분석완료"로 바뀌어야 함.

- [ ] **Step 4: 커밋**

```bash
git add backend/app/routers/companies.py backend/app/routers/reports.py
git commit -m "fix: 분석 pending 상태에서 완료로 잘못 표시되는 버그 수정"
```

---

## Task 2: 백엔드 데이터 모델 — Tag + company_tags

**Files:**
- Modify: `backend/app/models.py`

- [ ] **Step 1: `Table` import 추가**

`backend/app/models.py` 상단 import를:

```python
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Text,
    ForeignKey, UniqueConstraint,
)
```

다음으로 교체 (`Table` 추가):

```python
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Text,
    ForeignKey, UniqueConstraint, Table,
)
```

- [ ] **Step 2: `company_tags` 조인 테이블을 `Company` 클래스 정의 바로 위에 삽입**

> **중요**: `company_tags`는 `Company.tags` 클래스 바디에서 직접 참조되므로, 반드시 `Company` 클래스 선언 **이전**에 정의해야 합니다. `from app.database import Base` 바로 아래, `class Company(Base):` 위에 삽입하세요.

`models.py` 의 다음 부분:

```python
from app.database import Base


class Company(Base):
```

을:

```python
from app.database import Base

# 기업-태그 M2M 조인 테이블 (Company 클래스보다 먼저 정의)
company_tags = Table(
    "company_tags",
    Base.metadata,
    Column("company_id", Integer, ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Company(Base):
```

로 교체.

- [ ] **Step 3: `Company` 클래스 바디에 `tags` relationship 추가**

`models.py` 의 `Company` 클래스 내 relationship 블록:

```python
    reports = relationship("Report", back_populates="company", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="company", cascade="all, delete-orphan")
```

를:

```python
    reports = relationship("Report", back_populates="company", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="company", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=company_tags, back_populates="companies")
```

로 교체.

- [ ] **Step 4: `Tag` 모델을 파일 끝에 추가 (PromptTemplate 클래스 뒤)**

```python
class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    companies = relationship("Company", secondary=company_tags, back_populates="tags")
```

- [ ] **Step 5: 백엔드 재시작으로 DB 마이그레이션 확인**

```bash
cd backend
DATA_DIR=./data python -m uvicorn app.main:app --reload --port 8016
```

시작 로그에 에러 없이 `Application startup complete.` 메시지가 나오면 성공.
(`Base.metadata.create_all`이 `tags`, `company_tags` 테이블을 자동 생성)

- [ ] **Step 6: 커밋**

```bash
git add backend/app/models.py
git commit -m "feat: Tag 모델 및 company_tags 조인 테이블 추가"
```

---

## Task 3: 백엔드 스키마 — Tag 스키마 + CompanyResponse 업데이트

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: `TagResponse`, `TagCreate`, `TagUpdate` 스키마 추가**

`backend/app/schemas.py` 의 `# --- Company ---` 섹션 바로 위(파일 상단 import 블록 바로 아래)에 추가:

```python
# --- Tag ---

class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TagCreate(BaseModel):
    name: str
    color: str


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
```

- [ ] **Step 2: `CompanyResponse`에 `tags` 필드 추가**

`schemas.py` 의 `CompanyResponse` 클래스를:

```python
class CompanyResponse(BaseModel):
    id: int
    corp_code: str
    corp_name: str
    stock_code: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    report_count: int = 0
    latest_analysis_date: datetime | None = None

    model_config = {"from_attributes": True}
```

다음으로 교체:

```python
class CompanyResponse(BaseModel):
    id: int
    corp_code: str
    corp_name: str
    stock_code: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    report_count: int = 0
    latest_analysis_date: datetime | None = None
    tags: list[TagResponse] = []

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: 커밋**

```bash
git add backend/app/schemas.py
git commit -m "feat: Tag 스키마 추가 및 CompanyResponse에 tags 필드 추가"
```

---

## Task 4: 백엔드 라우터 — tags.py 신규 작성

**Files:**
- Create: `backend/app/routers/tags.py`

- [ ] **Step 1: `backend/app/routers/tags.py` 파일 생성**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tag
from app.schemas import TagResponse, TagCreate, TagUpdate

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagResponse])
def list_tags(db: Session = Depends(get_db)):
    return db.query(Tag).order_by(Tag.name).all()


@router.post("", response_model=TagResponse, status_code=201)
def create_tag(body: TagCreate, db: Session = Depends(get_db)):
    if db.query(Tag).filter(Tag.name == body.name).first():
        raise HTTPException(409, f"이미 존재하는 태그입니다: {body.name}")
    tag = Tag(**body.model_dump())
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.put("/{tag_id}", response_model=TagResponse)
def update_tag(tag_id: int, body: TagUpdate, db: Session = Depends(get_db)):
    tag = db.query(Tag).get(tag_id)
    if not tag:
        raise HTTPException(404, "태그를 찾을 수 없습니다.")
    if body.name and body.name != tag.name:
        if db.query(Tag).filter(Tag.name == body.name).first():
            raise HTTPException(409, f"이미 존재하는 태그입니다: {body.name}")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(tag, key, val)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(Tag).get(tag_id)
    if not tag:
        raise HTTPException(404, "태그를 찾을 수 없습니다.")
    db.delete(tag)
    db.commit()
```

- [ ] **Step 2: 커밋**

```bash
git add backend/app/routers/tags.py
git commit -m "feat: 태그 CRUD 라우터 추가"
```

---

## Task 5: 백엔드 라우터 — companies.py 업데이트

**Files:**
- Modify: `backend/app/routers/companies.py`

- [ ] **Step 1: import에 `Tag` 추가**

`companies.py` 상단의:

```python
from app.models import Company, Report, Analysis
```

를:

```python
from app.models import Company, Report, Analysis, Tag
```

로 교체.

- [ ] **Step 2: `_build_company_response` 헬퍼 함수 추가**

`router = APIRouter(...)` 선언 바로 뒤에 추가:

```python
def _build_company_response(db: Session, company: Company) -> CompanyResponse:
    report_count = (
        db.query(func.count(Report.id)).filter(Report.company_id == company.id).scalar()
    )
    latest = (
        db.query(func.max(Analysis.updated_at))
        .filter(Analysis.company_id == company.id, Analysis.status == "completed")
        .scalar()
    )
    resp = CompanyResponse.model_validate(company)
    resp.report_count = report_count
    resp.latest_analysis_date = latest
    return resp
```

- [ ] **Step 3: `list_companies`에 `tag_ids` 필터 + 헬퍼 적용**

기존 `list_companies` 함수 전체를 교체:

```python
@router.get("", response_model=list[CompanyResponse])
def list_companies(tag_ids: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Company).order_by(Company.created_at.desc())
    if tag_ids:
        ids = [int(i) for i in tag_ids.split(",") if i.strip().isdigit()]
        if ids:
            query = query.filter(Company.tags.any(Tag.id.in_(ids)))
    companies = query.all()
    return [_build_company_response(db, c) for c in companies]
```

- [ ] **Step 4: 태그 할당 / 제거 엔드포인트 추가**

파일 끝에 추가:

```python
@router.post("/{company_id}/tags/{tag_id}", response_model=CompanyResponse)
def assign_tag(company_id: int, tag_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")
    tag = db.query(Tag).get(tag_id)
    if not tag:
        raise HTTPException(404, "태그를 찾을 수 없습니다.")
    if tag not in company.tags:
        company.tags.append(tag)
        db.commit()
        db.refresh(company)
    return _build_company_response(db, company)


@router.delete("/{company_id}/tags/{tag_id}", response_model=CompanyResponse)
def remove_tag(company_id: int, tag_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")
    tag = db.query(Tag).get(tag_id)
    if tag and tag in company.tags:
        company.tags.remove(tag)
        db.commit()
        db.refresh(company)
    return _build_company_response(db, company)
```

- [ ] **Step 5: 백엔드 재시작 후 API 확인**

```bash
# 태그 생성 테스트
curl -s -X POST http://localhost:8016/api/tags \
  -H "Content-Type: application/json" \
  -d '{"name":"포트폴리오","color":"#3B82F6"}' | python -m json.tool

# 기업 목록 태그 포함 확인 (tags 배열이 응답에 있어야 함)
curl -s http://localhost:8016/api/companies | python -m json.tool | head -40

# tag_ids 필터 테스트 (생성된 태그 id로 교체)
curl -s "http://localhost:8016/api/companies?tag_ids=1" | python -m json.tool
```

- [ ] **Step 6: 커밋**

```bash
git add backend/app/routers/companies.py
git commit -m "feat: 기업 라우터에 태그 할당/제거/필터링 엔드포인트 추가"
```

---

## Task 6: 백엔드 main.py — tags 라우터 등록

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: tags 라우터 import 및 등록**

`main.py` 의:

```python
from app.routers import companies, reports, analyses, scheduler
from app.routers import prompts as prompts_router
```

를:

```python
from app.routers import companies, reports, analyses, scheduler
from app.routers import prompts as prompts_router
from app.routers import tags as tags_router
```

로 교체.

`app.include_router(prompts_router.router)` 다음 줄에 추가:

```python
app.include_router(tags_router.router)
```

- [ ] **Step 2: 백엔드 재시작 + Swagger 확인**

```bash
DATA_DIR=./data python -m uvicorn app.main:app --reload --port 8016
```

브라우저에서 `http://localhost:8016/docs` 접속 → `/api/tags` 엔드포인트 그룹이 보이면 성공.

- [ ] **Step 3: 커밋**

```bash
git add backend/app/main.py
git commit -m "feat: tags 라우터 FastAPI 앱에 등록"
```

---

## Task 7: 프론트엔드 — 타입 + API 클라이언트

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: `types/index.ts` — `Tag` 인터페이스 + `TAG_COLORS` + `Company.tags` 추가**

`frontend/src/types/index.ts` 전체를 교체:

```typescript
export interface Tag {
  id: number;
  name: string;
  color: string;
  created_at: string;
}

export const TAG_COLORS = [
  "#3B82F6", "#22C55E", "#EF4444", "#F97316",
  "#A855F7", "#EC4899", "#06B6D4", "#EAB308",
  "#6366F1", "#14B8A6", "#78716C", "#6B7280",
] as const;

export interface Company {
  id: number;
  corp_code: string;
  corp_name: string;
  stock_code: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  report_count: number;
  latest_analysis_date: string | null;
  tags: Tag[];
}

export interface CompanySearchResult {
  corp_code: string;
  corp_name: string;
  stock_code: string | null;
}

export interface Report {
  id: number;
  company_id: number;
  rcept_no: string;
  report_name: string;
  report_type: string;
  fiscal_year: number;
  filing_date: string | null;
  file_path: string | null;
  downloaded_at: string | null;
  created_at: string;
  analysis_count: number;
}

export interface Analysis {
  id: number;
  company_id: number;
  report_id: number;
  analysis_type: "subsidiary" | "rnd" | "national_tech";
  status: "pending" | "running" | "completed" | "failed";
  result_json: string | null;
  result_summary: string | null;
  error_message: string | null;
  model_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface SchedulerStatus {
  is_running: boolean;
  next_run_time: string | null;
  interval_hours: number;
}

export interface PromptTemplate {
  id: number;
  analysis_type: string;
  label: string;
  system_prompt: string;
  user_prompt_template: string;
  updated_at: string;
}
```

- [ ] **Step 2: `api/client.ts` — `fetchCompanies` 업데이트 + 태그 API 함수 추가**

`client.ts` 의 import 줄 `import type { Company, ... }` 에 `Tag` 추가:

```typescript
import type {
  Company,
  CompanySearchResult,
  Report,
  Analysis,
  SchedulerStatus,
  PromptTemplate,
  Tag,
} from "../types";
```

기존 `fetchCompanies` 함수를:

```typescript
export function fetchCompanies(): Promise<Company[]> {
  return request("/companies");
}
```

다음으로 교체:

```typescript
export function fetchCompanies(tagIds?: number[]): Promise<Company[]> {
  const qs = tagIds && tagIds.length > 0 ? `?tag_ids=${tagIds.join(",")}` : "";
  return request(`/companies${qs}`);
}
```

파일 끝 `// --- Prompts ---` 섹션 다음에 추가:

```typescript
// --- Tags ---

export function fetchTags(): Promise<Tag[]> {
  return request("/tags");
}

export function createTag(body: { name: string; color: string }): Promise<Tag> {
  return request("/tags", { method: "POST", body: JSON.stringify(body) });
}

export function updateTag(
  id: number,
  body: { name?: string; color?: string },
): Promise<Tag> {
  return request(`/tags/${id}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteTag(id: number): Promise<void> {
  return request(`/tags/${id}`, { method: "DELETE" });
}

export function assignTag(companyId: number, tagId: number): Promise<Company> {
  return request(`/companies/${companyId}/tags/${tagId}`, { method: "POST" });
}

export function removeCompanyTag(companyId: number, tagId: number): Promise<Company> {
  return request(`/companies/${companyId}/tags/${tagId}`, { method: "DELETE" });
}
```

- [ ] **Step 3: TypeScript 컴파일 확인**

```bash
cd frontend
npx tsc --noEmit
```

에러 없으면 성공.

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat: Tag 타입 및 태그 API 클라이언트 함수 추가"
```

---

## Task 8: 프론트엔드 — TagSettings 페이지

**Files:**
- Create: `frontend/src/pages/TagSettings.tsx`

- [ ] **Step 1: `TagSettings.tsx` 파일 생성**

```tsx
import { useEffect, useState } from "react";
import { fetchTags, createTag, updateTag, deleteTag } from "../api/client";
import type { Tag } from "../types";
import { TAG_COLORS } from "../types";

export default function TagSettings() {
  const [tags, setTags] = useState<Tag[]>([]);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState(TAG_COLORS[0]);
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editColor, setEditColor] = useState("");
  const [error, setError] = useState("");

  const load = () => fetchTags().then(setTags).catch(() => {});
  useEffect(load, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!newName.trim()) return;
    try {
      await createTag({ name: newName.trim(), color: newColor });
      setNewName("");
      setNewColor(TAG_COLORS[0]);
      load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const startEdit = (tag: Tag) => {
    setEditId(tag.id);
    setEditName(tag.name);
    setEditColor(tag.color);
    setError("");
  };

  const handleUpdate = async (id: number) => {
    setError("");
    if (!editName.trim()) return;
    try {
      await updateTag(id, { name: editName.trim(), color: editColor });
      setEditId(null);
      load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleDelete = async (tag: Tag) => {
    if (!confirm(`"${tag.name}" 태그를 삭제하시겠습니까?\n기업에서 할당된 태그도 해제됩니다.`)) return;
    await deleteTag(tag.id);
    load();
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-navy">태그 관리</h1>
        <p className="mt-1 text-sm text-text-secondary">
          기업에 할당할 태그를 미리 정의합니다.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-lg bg-danger-bg px-4 py-3 text-sm text-danger">
          {error}
        </div>
      )}

      {/* 태그 생성 폼 */}
      <div className="mb-8 rounded-xl border border-border bg-surface p-6 shadow-sm">
        <h2 className="mb-4 text-sm font-semibold text-text-primary">새 태그 추가</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-48">
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">
              태그 이름
            </label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="예: 포트폴리오"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent focus:ring-1 focus:ring-accent/20"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">
              색상
            </label>
            <div className="flex flex-wrap gap-1.5">
              {TAG_COLORS.map((hex) => (
                <button
                  key={hex}
                  type="button"
                  onClick={() => setNewColor(hex)}
                  style={{ backgroundColor: hex }}
                  className={`h-7 w-7 rounded-full transition-transform hover:scale-110 ${
                    newColor === hex ? "ring-2 ring-offset-2 ring-gray-400 scale-110" : ""
                  }`}
                  title={hex}
                />
              ))}
            </div>
          </div>
          <button
            type="submit"
            disabled={!newName.trim()}
            className="btn btn-primary"
          >
            추가
          </button>
        </form>
      </div>

      {/* 태그 목록 */}
      <div className="rounded-xl border border-border bg-surface shadow-sm">
        {tags.length === 0 ? (
          <div className="py-12 text-center text-sm text-text-tertiary">
            태그가 없습니다. 위에서 태그를 추가해주세요.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-background/50">
                <th className="px-6 py-3.5 text-left font-semibold text-text-secondary">태그</th>
                <th className="px-6 py-3.5 text-left font-semibold text-text-secondary">색상</th>
                <th className="px-6 py-3.5 text-right font-semibold text-text-secondary">작업</th>
              </tr>
            </thead>
            <tbody>
              {tags.map((tag) => (
                <tr key={tag.id} className="border-b border-border transition-colors last:border-b-0 hover:bg-background/30">
                  <td className="px-6 py-4">
                    {editId === tag.id ? (
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className="w-full max-w-xs rounded border border-border px-2 py-1 text-sm outline-none focus:border-accent"
                        autoFocus
                      />
                    ) : (
                      <span
                        style={{ backgroundColor: tag.color + "20", color: tag.color, border: `1px solid ${tag.color}40` }}
                        className="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium"
                      >
                        {tag.name}
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    {editId === tag.id ? (
                      <div className="flex flex-wrap gap-1.5">
                        {TAG_COLORS.map((hex) => (
                          <button
                            key={hex}
                            type="button"
                            onClick={() => setEditColor(hex)}
                            style={{ backgroundColor: hex }}
                            className={`h-6 w-6 rounded-full transition-transform hover:scale-110 ${
                              editColor === hex ? "ring-2 ring-offset-1 ring-gray-400 scale-110" : ""
                            }`}
                          />
                        ))}
                      </div>
                    ) : (
                      <span
                        style={{ backgroundColor: tag.color }}
                        className="inline-block h-5 w-5 rounded-full"
                        title={tag.color}
                      />
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-3">
                      {editId === tag.id ? (
                        <>
                          <button onClick={() => handleUpdate(tag.id)} className="btn btn-link">
                            저장
                          </button>
                          <button onClick={() => setEditId(null)} className="btn btn-text">
                            취소
                          </button>
                        </>
                      ) : (
                        <>
                          <button onClick={() => startEdit(tag)} className="btn btn-text">
                            수정
                          </button>
                          <button onClick={() => handleDelete(tag)} className="btn btn-text-danger">
                            삭제
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/pages/TagSettings.tsx
git commit -m "feat: 태그 관리 페이지 추가"
```

---

## Task 9: 프론트엔드 — 라우트 + 네비게이션

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: `App.tsx` — `/tags` 라우트 추가**

`App.tsx` 전체를 교체:

```tsx
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import CompanyList from "./pages/CompanyList";
import CompanyDetail from "./pages/CompanyDetail";
import PromptSettings from "./pages/PromptSettings";
import TagSettings from "./pages/TagSettings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<CompanyList />} />
        <Route path="/companies/:id" element={<CompanyDetail />} />
        <Route path="/settings/prompts" element={<PromptSettings />} />
        <Route path="/tags" element={<TagSettings />} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 2: `Layout.tsx` — "태그 관리" 네비 링크 추가**

`Layout.tsx` 의 `<Link to="/settings/prompts" className="nav-link">설정</Link>` 바로 앞에 추가:

```tsx
            <Link
              to="/tags"
              className="nav-link"
            >
              태그 관리
            </Link>
```

최종 nav 영역:

```tsx
          <div className="flex items-center gap-4 text-sm">
            {scheduler && (
              <div className="flex items-center gap-1.5">
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${
                    scheduler.is_running ? "bg-green-400" : "bg-red-400"
                  }`}
                />
                <span className="text-white/60">
                  {scheduler.is_running ? "스케줄러 동작중" : "스케줄러 정지"}
                </span>
              </div>
            )}
            <Link to="/tags" className="nav-link">
              태그 관리
            </Link>
            <Link to="/settings/prompts" className="nav-link">
              설정
            </Link>
          </div>
```

- [ ] **Step 3: 브라우저 확인**

```bash
cd frontend && npm run dev
```

`http://localhost:5185/tags` 접속 → 태그 관리 페이지가 렌더링되면 성공. 태그 추가/수정/삭제 동작 확인.

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout.tsx
git commit -m "feat: 태그 관리 라우트 및 네비게이션 링크 추가"
```

---

## Task 10: 프론트엔드 — CompanyList 태그 필터 바 + 태그 칩

**Files:**
- Modify: `frontend/src/pages/CompanyList.tsx`

- [ ] **Step 1: import 추가**

`CompanyList.tsx` 상단 import를:

```typescript
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchCompanies, deleteCompany } from "../api/client";
import CompanyForm from "../components/CompanyForm";
import CompanyEditModal from "../components/CompanyEditModal";
import type { Company } from "../types";
```

다음으로 교체:

```typescript
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchCompanies, deleteCompany, fetchTags } from "../api/client";
import CompanyForm from "../components/CompanyForm";
import CompanyEditModal from "../components/CompanyEditModal";
import type { Company, Tag } from "../types";
```

- [ ] **Step 2: 태그 상태 추가**

`CompanyList` 컴포넌트 내부 state 선언 블록에 추가:

```typescript
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [selectedTagIds, setSelectedTagIds] = useState<number[]>([]);
```

- [ ] **Step 3: `load` 함수 교체**

기존:

```typescript
  const load = () => {
    setLoading(true);
    fetchCompanies()
      .then(setCompanies)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, []);
```

교체:

```typescript
  const load = (tagIds = selectedTagIds) => {
    setLoading(true);
    Promise.all([
      fetchCompanies(tagIds.length > 0 ? tagIds : undefined),
      fetchTags(),
    ])
      .then(([cos, tags]) => {
        setCompanies(cos);
        setAllTags(tags);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load([]); }, []);

  const toggleTagFilter = (tagId: number) => {
    const newIds = selectedTagIds.includes(tagId)
      ? selectedTagIds.filter((id) => id !== tagId)
      : [...selectedTagIds, tagId];
    setSelectedTagIds(newIds);
    load(newIds);
  };
```

- [ ] **Step 4: 검색 바를 태그 필터 바와 함께 배치**

기존:

```tsx
      {/* Search */}
      <div className="mb-6">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="기업명 또는 기업코드 검색..."
          className="w-full max-w-sm rounded-lg border border-border bg-surface px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent/20"
        />
      </div>
```

교체:

```tsx
      {/* Search + Tag Filter */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="기업명 또는 기업코드 검색..."
          className="min-w-48 flex-1 rounded-lg border border-border bg-surface px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent/20"
        />
        {allTags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {allTags.map((tag) => {
              const active = selectedTagIds.includes(tag.id);
              return (
                <button
                  key={tag.id}
                  onClick={() => toggleTagFilter(tag.id)}
                  style={
                    active
                      ? { backgroundColor: tag.color, color: "#fff", borderColor: tag.color }
                      : { color: tag.color, borderColor: tag.color + "60" }
                  }
                  className="rounded-full border px-3 py-1 text-xs font-medium transition-all hover:opacity-80"
                >
                  {tag.name}
                </button>
              );
            })}
            {selectedTagIds.length > 0 && (
              <button
                onClick={() => { setSelectedTagIds([]); load([]); }}
                className="rounded-full border border-border px-3 py-1 text-xs text-text-tertiary hover:text-text-primary"
              >
                초기화
              </button>
            )}
          </div>
        )}
      </div>
```

- [ ] **Step 5: 기업 행 — 기업명 셀에 태그 칩 추가**

기존 기업명 `<td>` 내부:

```tsx
                  <td className="px-6 py-4">
                    <Link
                      to={`/companies/${c.id}`}
                      className="font-medium text-navy hover:text-accent"
                    >
                      {c.corp_name}
                    </Link>
                    {!c.is_active && (
                      <span className="ml-2 text-xs text-text-tertiary">(비활성)</span>
                    )}
                  </td>
```

교체:

```tsx
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <Link
                        to={`/companies/${c.id}`}
                        className="font-medium text-navy hover:text-accent"
                      >
                        {c.corp_name}
                      </Link>
                      {!c.is_active && (
                        <span className="text-xs text-text-tertiary">(비활성)</span>
                      )}
                    </div>
                    {c.tags.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {c.tags.slice(0, 3).map((tag) => (
                          <span
                            key={tag.id}
                            style={{
                              backgroundColor: tag.color + "20",
                              color: tag.color,
                              border: `1px solid ${tag.color}40`,
                            }}
                            className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium"
                          >
                            {tag.name}
                          </span>
                        ))}
                        {c.tags.length > 3 && (
                          <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-text-tertiary">
                            +{c.tags.length - 3}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
```

- [ ] **Step 6: 브라우저 확인**

`http://localhost:5185` 에서:
- 태그 칩이 검색바 우측에 배치되는지 확인
- 모바일 뷰(`375px`)에서 태그 필터가 아래 줄로 내려가는지 확인
- 태그 클릭 시 해당 기업만 필터링되는지 확인
- "초기화" 버튼으로 필터 해제 확인

- [ ] **Step 7: 커밋**

```bash
git add frontend/src/pages/CompanyList.tsx
git commit -m "feat: 기업 목록에 태그 필터 바 및 태그 칩 표시 추가"
```

---

## Task 11: 프론트엔드 — CompanyDetail 인라인 태그 UI

**Files:**
- Modify: `frontend/src/pages/CompanyDetail.tsx`

- [ ] **Step 1: import 추가**

기존:

```typescript
import {
  fetchCompanies,
  fetchReports,
  fetchCompanyAnalyses,
  deleteCompany,
  deleteReport,
  redownloadReport,
  analyzeReport,
  analyzeAll,
} from "../api/client";
import ReportTable from "../components/ReportTable";
import DownloadModal from "../components/DownloadModal";
import AnalysisView from "../components/AnalysisView";
import type { Company, Report, Analysis } from "../types";
```

교체:

```typescript
import { useEffect, useRef, useState } from "react";
import {
  fetchCompanies,
  fetchReports,
  fetchCompanyAnalyses,
  fetchTags,
  assignTag,
  removeCompanyTag,
  deleteCompany,
  deleteReport,
  redownloadReport,
  analyzeReport,
  analyzeAll,
} from "../api/client";
import ReportTable from "../components/ReportTable";
import DownloadModal from "../components/DownloadModal";
import AnalysisView from "../components/AnalysisView";
import type { Company, Report, Analysis, Tag } from "../types";
```

(주의: 기존 `import { useEffect, useState }` 는 위 import로 대체됨)

- [ ] **Step 2: 태그 상태 + 드롭다운 상태 추가**

컴포넌트 내부 state 선언 블록에 추가:

```typescript
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [showTagDropdown, setShowTagDropdown] = useState(false);
  const tagDropdownRef = useRef<HTMLDivElement>(null);
```

- [ ] **Step 3: `load` 함수에 `fetchTags` 추가**

기존:

```typescript
  const load = async () => {
    const [companies, reps, anals] = await Promise.all([
      fetchCompanies(),
      fetchReports(companyId),
      fetchCompanyAnalyses(companyId),
    ]);
    setCompany(companies.find((c) => c.id === companyId) || null);
    setReports(reps);
    setAnalyses(anals);
  };
```

교체:

```typescript
  const load = async () => {
    const [companies, reps, anals, tags] = await Promise.all([
      fetchCompanies(),
      fetchReports(companyId),
      fetchCompanyAnalyses(companyId),
      fetchTags(),
    ]);
    setCompany(companies.find((c) => c.id === companyId) || null);
    setReports(reps);
    setAnalyses(anals);
    setAllTags(tags);
  };
```

- [ ] **Step 4: 드롭다운 외부 클릭 닫기 effect 추가**

`useEffect(() => { load(); }, [companyId]);` 바로 아래에 추가:

```typescript
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (tagDropdownRef.current && !tagDropdownRef.current.contains(e.target as Node)) {
        setShowTagDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);
```

- [ ] **Step 5: 태그 할당/제거 핸들러 추가**

`handleDelete` 함수 바로 뒤에 추가:

```typescript
  const handleAssignTag = async (tagId: number) => {
    try {
      const updated = await assignTag(companyId, tagId);
      setCompany(updated);
      setShowTagDropdown(false);
    } catch (e: any) {
      showToast(e.message, "err");
    }
  };

  const handleRemoveTag = async (tagId: number) => {
    try {
      const updated = await removeCompanyTag(companyId, tagId);
      setCompany(updated);
    } catch (e: any) {
      showToast(e.message, "err");
    }
  };
```

- [ ] **Step 6: 헤더 영역에 태그 UI 추가**

`CompanyDetail.tsx` 의 기업명/코드 표시 블록:

```tsx
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-navy">
              {company.corp_name}
            </h1>
            <div className="mt-1 flex gap-3 text-sm text-text-secondary">
              {company.stock_code && (
                <span className="font-mono">{company.stock_code}</span>
              )}
              <span className="font-mono text-text-tertiary">
                DART: {company.corp_code}
              </span>
            </div>
          </div>
```

교체:

```tsx
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-navy">
              {company.corp_name}
            </h1>
            <div className="mt-1 flex gap-3 text-sm text-text-secondary">
              {company.stock_code && (
                <span className="font-mono">{company.stock_code}</span>
              )}
              <span className="font-mono text-text-tertiary">
                DART: {company.corp_code}
              </span>
            </div>
            {/* 태그 인라인 UI */}
            <div className="no-print mt-2 flex flex-wrap items-center gap-1.5">
              {company.tags.map((tag) => (
                <span
                  key={tag.id}
                  style={{
                    backgroundColor: tag.color + "20",
                    color: tag.color,
                    border: `1px solid ${tag.color}40`,
                  }}
                  className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
                >
                  {tag.name}
                  <button
                    onClick={() => handleRemoveTag(tag.id)}
                    className="ml-0.5 opacity-60 hover:opacity-100"
                    title="태그 제거"
                  >
                    ×
                  </button>
                </span>
              ))}
              <div ref={tagDropdownRef} className="relative">
                <button
                  onClick={() => setShowTagDropdown((v) => !v)}
                  className="rounded-full border border-dashed border-border px-2.5 py-0.5 text-xs text-text-tertiary hover:border-accent hover:text-accent"
                >
                  + 태그
                </button>
                {showTagDropdown && (
                  <div className="absolute left-0 top-full z-20 mt-1 min-w-36 rounded-lg border border-border bg-surface shadow-lg">
                    {allTags.filter((t) => !company.tags.some((ct) => ct.id === t.id)).length === 0 ? (
                      <p className="px-3 py-2.5 text-xs text-text-tertiary">
                        할당 가능한 태그가 없습니다.
                      </p>
                    ) : (
                      allTags
                        .filter((t) => !company.tags.some((ct) => ct.id === t.id))
                        .map((tag) => (
                          <button
                            key={tag.id}
                            onClick={() => handleAssignTag(tag.id)}
                            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-background/60"
                          >
                            <span
                              style={{ backgroundColor: tag.color }}
                              className="inline-block h-2.5 w-2.5 rounded-full flex-shrink-0"
                            />
                            {tag.name}
                          </button>
                        ))
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
```

- [ ] **Step 7: 브라우저 확인**

기업 상세 페이지에서:
- "+ 태그" 버튼 클릭 → 드롭다운에 할당 가능한 태그 목록 표시
- 태그 선택 → 즉시 헤더에 칩으로 표시
- 칩의 × 버튼 클릭 → 즉시 제거
- 드롭다운 외부 클릭 → 드롭다운 닫힘
- 이미 할당된 태그는 드롭다운에 표시 안 됨

- [ ] **Step 8: 최종 커밋**

```bash
git add frontend/src/pages/CompanyDetail.tsx
git commit -m "feat: 기업 상세 화면에 인라인 태그 할당/제거 UI 추가"
```

---

## 완료 기준 체크리스트

- [ ] 분석 큐 투입 직후 기업 목록 상태가 "대기" 또는 "보고서만"으로 유지됨
- [ ] 분석 완료 후에만 "분석완료" 뱃지 표시
- [ ] 보고서 목록 분석 컬럼이 pending 포함 카운트하지 않음
- [ ] 태그 관리 페이지에서 태그 생성/수정/삭제 동작
- [ ] 중복 태그명 생성 시 에러 메시지 표시
- [ ] 기업 목록에서 태그 필터 클릭 시 해당 기업만 표시 (OR 조건)
- [ ] 모바일 뷰에서 태그 필터 바가 줄바꿈으로 자연스럽게 배치됨
- [ ] 기업 상세에서 인라인 태그 할당/제거
- [ ] 태그 삭제 시 기업에서 자동 해제
