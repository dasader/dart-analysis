# 기업 DART 사업보고서 분석 웹서비스 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OpenDART API로 기업 사업보고서를 수집하고 Gemini LLM으로 종속회사/R&D/국가전략기술 분석을 수행하는 웹서비스 구축

**Architecture:** FastAPI 백엔드(APScheduler 내장) + React/Vite 프론트엔드 + SQLite. 보고서 원문은 파일 시스템, 메타데이터와 분석 결과는 SQLite에 저장. Docker Compose로 시놀로지 배포.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / APScheduler / React 18 / Vite / TypeScript / Tailwind CSS / Docker

---

## Frontend 디자인 방향

**Aesthetic:** Editorial / Corporate Intelligence — 금융/컨설팅 리포트를 연상시키는 절제된 전문가 톤

**Typography:**
- 한글 본문: **Pretendard** (Apple SD Gothic Neo 대안, 현대적이고 깔끔한 한글 서체)
- 영문 본문/숫자: **DM Sans** (기하학적이면서 가독성 높은 sans-serif)
- 코드/데이터: **JetBrains Mono** (기술 데이터 표시용)

**Color Palette:**
- Background: `#FAFBFC` (밝은 회색-흰색)
- Surface: `#FFFFFF` (카드/패널)
- Primary: `#1B2A4A` (네이비, 신뢰감)
- Accent: `#2563EB` (블루, CTA/링크)
- Success: `#059669` / Warning: `#D97706` / Danger: `#DC2626`
- Text Primary: `#111827` / Text Secondary: `#6B7280`
- Border: `#E5E7EB`

**Layout:** 좌측 고정 사이드바 없이, 상단 네비게이션 + 넓은 콘텐츠 영역. 카드 기반 레이아웃에 미묘한 그림자(`shadow-sm`)와 1px 보더로 깊이감.

**Print:** `@media print` 전용 스타일로 불필요한 UI 요소 숨기고 흰색 배경 + 검정 텍스트 전환.

---

## File Structure

```
16_firm-dart-analysis/
├── .env                          # API 키, 포트 등 환경변수
├── .gitignore                    # data/, node_modules/, __pycache__ 등
├── docker-compose.yml            # backend + frontend 서비스 정의
├── backend/
│   ├── Dockerfile                # python:3.12-slim 기반
│   ├── requirements.txt          # FastAPI, SQLAlchemy, APScheduler, httpx, google-genai
│   └── app/
│       ├── main.py               # FastAPI 앱 생성, 라우터 등록, APScheduler lifespan
│       ├── config.py             # pydantic-settings 기반 환경변수 로드
│       ├── database.py           # SQLAlchemy engine/session, create_all
│       ├── models.py             # Company, Report, Analysis ORM 모델
│       ├── schemas.py            # Pydantic request/response 스키마
│       ├── routers/
│       │   ├── companies.py      # 기업 CRUD + OpenDART 검색
│       │   ├── reports.py        # 보고서 목록/다운로드/체크/원문
│       │   ├── analyses.py       # 분석 실행/조회
│       │   ├── scheduler.py      # 스케줄러 상태/즉시실행
│       │   └── prompts.py        # 프롬프트 조회/수정 API
│       ├── services/
│       │   ├── dart_client.py    # OpenDART API (기업검색, 공시목록, 문서다운로드)
│       │   ├── gemini_client.py  # Gemini API 호출 래퍼
│       │   ├── report_service.py # ZIP 다운로드/해제/텍스트 추출
│       │   └── analysis_service.py # DB에서 프롬프트 로드 + Gemini 호출 + 결과 파싱
│       ├── seed_prompts.py       # 기본 프롬프트 시딩 (3종)
│       └── scheduler.py          # APScheduler 작업 정의
├── frontend/
│   ├── Dockerfile                # node:20-alpine → nginx:alpine multi-stage
│   ├── nginx.conf                # SPA fallback + /api 프록시
│   ├── package.json
│   ├── tsconfig.json
│   ├── tsconfig.app.json
│   ├── vite.config.ts            # 포트 5185, /api 프록시 → localhost:8016
│   ├── tailwind.config.js        # Pretendard + DM Sans 폰트 설정
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx              # React 엔트리
│       ├── App.tsx               # React Router 설정
│       ├── index.css             # Tailwind 지시문 + @font-face + 글로벌 스타일 + print CSS
│       ├── api/
│       │   └── client.ts         # fetch 래퍼, 타입별 API 함수
│       ├── types/
│       │   └── index.ts          # Company, Report, Analysis 등 TypeScript 인터페이스
│       ├── pages/
│       │   ├── CompanyList.tsx    # 메인 — 기업 목록 대시보드
│       │   ├── CompanyDetail.tsx  # 기업 상세 + 탭
│       │   └── PromptSettings.tsx # 프롬프트 편집 설정 페이지
│       └── components/
│           ├── Layout.tsx         # 상단 네비게이션 + 콘텐츠 래퍼
│           ├── CompanyForm.tsx    # 기업 등록/수정 모달
│           ├── CompanySearch.tsx  # OpenDART 기업 검색 UI
│           ├── ReportTable.tsx    # 보고서 목록 테이블
│           ├── DownloadModal.tsx  # 보고서 다운로드 모달
│           ├── AnalysisView.tsx   # 분석 결과 표시 (마크다운 렌더링)
│           └── PrintableReport.tsx # PDF 출력용 래퍼
└── data/                         # 볼륨 마운트 (gitignore)
    ├── db.sqlite3
    └── reports/
```

---

## Task 1: 프로젝트 초기화 및 환경 설정

**Files:**
- Create: `.gitignore`
- Create: `.env`
- Create: `docker-compose.yml`
- Create: `backend/Dockerfile`
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`

- [ ] **Step 1: .gitignore 생성**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/

# Node
node_modules/
dist/

# Data
data/

# Environment
.env

# IDE
.vscode/
.idea/

# Superpowers
.superpowers/

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 2: .env 파일 업데이트**

기존 `.env` 파일에 환경변수를 추가. 기존 API 키는 유지하되 변수명을 표준화:

```env
# OpenDART
OPENDART_API_KEY=ccda2b87cdf11055b37dda35c0b5dcb5a91babc9

# Gemini
GEMINI_API_KEY=AIzaSyAujeINgg3_joF-2-e11LpffQzCqLHvVPo

# Ports
BACKEND_PORT=8016
FRONTEND_PORT=8097
FRONTEND_DEV_PORT=5185

# Scheduler
SCHEDULER_INTERVAL_HOURS=24

# Backend
DATA_DIR=/app/data
```

- [ ] **Step 3: backend/requirements.txt 생성**

```txt
fastapi==0.115.12
uvicorn[standard]==0.34.2
sqlalchemy==2.0.40
pydantic-settings==2.9.1
httpx==0.28.1
apscheduler==3.11.0
google-genai==1.14.0
python-multipart==0.0.20
```

- [ ] **Step 4: backend/app/config.py 생성**

```python
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    opendart_api_key: str
    gemini_api_key: str
    backend_port: int = 8016
    frontend_port: int = 8097
    scheduler_interval_hours: int = 24
    data_dir: Path = Path("/app/data")

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'db.sqlite3'}"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 5: backend/app/__init__.py 생성**

```python
```

(빈 파일)

- [ ] **Step 6: backend/Dockerfile 생성**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

RUN mkdir -p /app/data/reports

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 7: docker-compose.yml 생성**

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "${BACKEND_PORT:-8016}:8000"
    volumes:
      - ./data:/app/data
    env_file:
      - .env
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "${FRONTEND_PORT:-8097}:80"
    depends_on:
      - backend
    restart: unless-stopped
```

- [ ] **Step 8: 커밋**

```bash
git init
git add .gitignore .env docker-compose.yml backend/Dockerfile backend/requirements.txt backend/app/__init__.py backend/app/config.py
git commit -m "chore: 프로젝트 초기화 — 환경설정, Dockerfile, docker-compose"
```

---

## Task 2: 데이터베이스 모델 및 연결

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models.py`
- Create: `backend/app/schemas.py`

- [ ] **Step 1: backend/app/database.py 생성**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import Generator

from app.config import settings


engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2: backend/app/models.py 생성**

```python
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Text,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_code = Column(String, unique=True, nullable=False)
    corp_name = Column(String, nullable=False)
    stock_code = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reports = relationship("Report", back_populates="company", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="company", cascade="all, delete-orphan")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("company_id", "rcept_no", name="uq_company_rcept"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    rcept_no = Column(String, nullable=False)
    report_name = Column(String, nullable=False)
    report_type = Column(String, nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    filing_date = Column(Date, nullable=True)
    file_path = Column(String, nullable=True)
    downloaded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="reports")
    analyses = relationship("Analysis", back_populates="report", cascade="all, delete-orphan")


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        UniqueConstraint("company_id", "report_id", "analysis_type", name="uq_company_report_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    report_id = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    analysis_type = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending/running/completed/failed
    result_json = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    model_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="analyses")
    report = relationship("Report", back_populates="analyses")


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_type = Column(String, unique=True, nullable=False)
    label = Column(String, nullable=False)
    system_prompt = Column(Text, nullable=False)
    user_prompt_template = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 3: backend/app/schemas.py 생성**

```python
from pydantic import BaseModel
from datetime import datetime, date


# --- Company ---

class CompanySearchResult(BaseModel):
    corp_code: str
    corp_name: str
    stock_code: str | None = None

class CompanyCreate(BaseModel):
    corp_code: str
    corp_name: str
    stock_code: str | None = None

class CompanyUpdate(BaseModel):
    corp_name: str | None = None
    stock_code: str | None = None
    is_active: bool | None = None

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


# --- Report ---

class ReportDownloadRequest(BaseModel):
    fiscal_year: int | None = None
    report_type: str | None = None

class ReportResponse(BaseModel):
    id: int
    company_id: int
    rcept_no: str
    report_name: str
    report_type: str
    fiscal_year: int
    filing_date: date | None
    file_path: str | None
    downloaded_at: datetime | None
    created_at: datetime
    analysis_count: int = 0

    model_config = {"from_attributes": True}


# --- Analysis ---

class AnalysisRequest(BaseModel):
    analysis_type: str  # subsidiary | rnd | national_tech

class AnalysisResponse(BaseModel):
    id: int
    company_id: int
    report_id: int
    analysis_type: str
    status: str
    result_json: str | None
    result_summary: str | None
    error_message: str | None
    model_name: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QueueStatus(BaseModel):
    pending_count: int
    running: dict | None  # 현재 처리 중인 분석 정보


# --- Scheduler ---

class SchedulerStatus(BaseModel):
    is_running: bool
    next_run_time: datetime | None
    interval_hours: int


# --- Prompt Template ---

class PromptTemplateResponse(BaseModel):
    id: int
    analysis_type: str
    label: str
    system_prompt: str
    user_prompt_template: str
    updated_at: datetime

    model_config = {"from_attributes": True}

class PromptTemplateUpdate(BaseModel):
    system_prompt: str
    user_prompt_template: str
```

- [ ] **Step 4: 커밋**

```bash
git add backend/app/database.py backend/app/models.py backend/app/schemas.py
git commit -m "feat: SQLAlchemy 데이터 모델(PromptTemplate 포함) 및 Pydantic 스키마 정의"
```

---

## Task 3: OpenDART API 클라이언트

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/dart_client.py`

- [ ] **Step 1: backend/app/services/__init__.py 생성**

```python
```

(빈 파일)

- [ ] **Step 2: backend/app/services/dart_client.py 생성**

OpenDART API 3가지 기능: 기업 검색, 공시 목록 조회, 문서 다운로드.

```python
import io
import zipfile
import xml.etree.ElementTree as ET

import httpx

from app.config import settings

DART_BASE = "https://opendart.fss.or.kr/api"
CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"


async def search_companies(name: str) -> list[dict]:
    """OpenDART corpCode.xml을 다운로드하여 기업명으로 검색.

    corpCode.xml은 전체 기업 목록이 담긴 ZIP 파일.
    ZIP 안의 CORPCODE.xml을 파싱하여 name이 포함된 기업을 반환.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            CORP_CODE_URL,
            params={"crtfc_key": settings.opendart_api_key},
        )
        resp.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    xml_content = zf.read("CORPCODE.xml")
    root = ET.fromstring(xml_content)

    results = []
    for item in root.iter("list"):
        corp_name = item.findtext("corp_name", "")
        if name.lower() in corp_name.lower():
            results.append({
                "corp_code": item.findtext("corp_code", ""),
                "corp_name": corp_name,
                "stock_code": item.findtext("stock_code", "") or None,
            })
    return results[:50]


async def list_reports(
    corp_code: str,
    bgn_de: str | None = None,
    end_de: str | None = None,
    pblntf_ty: str = "A",
) -> list[dict]:
    """OpenDART 공시검색 API로 보고서 목록 조회.

    pblntf_ty: A=정기공시(사업/분기/반기보고서)
    """
    params = {
        "crtfc_key": settings.opendart_api_key,
        "corp_code": corp_code,
        "pblntf_ty": pblntf_ty,
        "page_count": 100,
    }
    if bgn_de:
        params["bgn_de"] = bgn_de
    if end_de:
        params["end_de"] = end_de

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{DART_BASE}/list.json", params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") != "000":
        return []

    results = []
    for item in data.get("list", []):
        report_nm = item.get("report_nm", "")
        report_type = _classify_report(report_nm)
        if report_type is None:
            continue
        results.append({
            "rcept_no": item["rcept_no"],
            "report_name": report_nm,
            "report_type": report_type,
            "filing_date": item.get("rcept_dt"),
            "corp_name": item.get("corp_name"),
        })
    return results


def _classify_report(name: str) -> str | None:
    """보고서명에서 유형 분류."""
    if "사업보고서" in name:
        return "사업보고서"
    if "반기보고서" in name:
        return "반기보고서"
    if "분기보고서" in name:
        return "분기보고서"
    return None


async def download_document(rcept_no: str) -> bytes:
    """OpenDART 문서 다운로드 API로 ZIP 파일 다운로드."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{DART_BASE}/document.xml",
            params={
                "crtfc_key": settings.opendart_api_key,
                "rcept_no": rcept_no,
            },
        )
        resp.raise_for_status()
    return resp.content
```

- [ ] **Step 3: 커밋**

```bash
git add backend/app/services/
git commit -m "feat: OpenDART API 클라이언트 — 기업검색, 공시목록, 문서다운로드"
```

---

## Task 4: 보고서 다운로드/추출 서비스

**Files:**
- Create: `backend/app/services/report_service.py`

- [ ] **Step 1: backend/app/services/report_service.py 생성**

```python
import io
import re
import zipfile
from pathlib import Path

from app.config import settings
from app.services.dart_client import download_document


async def download_and_extract(corp_code: str, rcept_no: str, fiscal_year: int) -> str:
    """보고서 ZIP 다운로드 → 해제 → 저장. 저장 디렉터리 경로 반환."""
    report_dir = settings.reports_dir / corp_code / str(fiscal_year)
    report_dir.mkdir(parents=True, exist_ok=True)

    zip_path = report_dir / f"{rcept_no}.zip"
    extracted_dir = report_dir / "extracted"
    extracted_dir.mkdir(exist_ok=True)

    content = await download_document(rcept_no)
    zip_path.write_bytes(content)

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            zf.extractall(extracted_dir)
    except zipfile.BadZipFile:
        pass

    return str(report_dir)


def extract_text_from_report(file_path: str) -> str:
    """저장된 보고서 디렉터리에서 텍스트를 추출.

    extracted/ 디렉터리 내의 XML/HTML 파일들을 읽어 태그를 제거한 텍스트를 반환.
    """
    extracted_dir = Path(file_path) / "extracted"
    if not extracted_dir.exists():
        return ""

    texts = []
    for f in sorted(extracted_dir.iterdir()):
        if f.suffix.lower() in (".xml", ".html", ".htm"):
            raw = f.read_text(encoding="utf-8", errors="ignore")
            clean = _strip_tags(raw)
            if clean.strip():
                texts.append(clean)

    return "\n\n".join(texts)


def _strip_tags(text: str) -> str:
    """HTML/XML 태그 제거."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()
```

- [ ] **Step 2: 커밋**

```bash
git add backend/app/services/report_service.py
git commit -m "feat: 보고서 ZIP 다운로드, 해제, 텍스트 추출 서비스"
```

---

## Task 5: Gemini 클라이언트, 프롬프트 시딩, 분석 서비스 + 백그라운드 큐

**Files:**
- Create: `backend/app/services/gemini_client.py`
- Create: `backend/app/seed_prompts.py`
- Create: `backend/app/services/analysis_service.py`
- Create: `backend/app/services/analysis_queue.py`
- Create: `backend/app/routers/prompts.py`

- [ ] **Step 1: backend/app/services/gemini_client.py 생성**

```python
from google import genai

from app.config import settings

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


MODEL_NAME = "gemini-2.0-flash"


async def generate(system_prompt: str, user_prompt: str) -> str:
    """Gemini API 호출. system + user 프롬프트를 받아 응답 텍스트를 반환."""
    client = _get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
            max_output_tokens=8192,
        ),
    )
    return response.text or ""
```

- [ ] **Step 2: backend/app/seed_prompts.py 생성**

기본 프롬프트 3종을 DB에 시딩하는 함수. 앱 시작 시 호출되며, 이미 존재하면 건너뜀.

```python
from sqlalchemy.orm import Session

from app.models import PromptTemplate

DEFAULT_PROMPTS = [
    {
        "analysis_type": "subsidiary",
        "label": "종속회사 변동 분석",
        "system_prompt": """당신은 기업 사업보고서를 분석하는 전문 애널리스트입니다.
주어진 사업보고서에서 연결대상 종속회사 현황을 추출하고 분석해주세요.

반드시 아래 형식의 마크다운으로 응답하세요:

## 요약
(종속회사 현황 전체 요약 — 총 개수, 주요 변화 등 2~3문장)

## 종속회사 목록
| 회사명 | 소재지 | 주요 사업 | 지분율(%) |
(보고서에서 확인 가능한 모든 종속회사 테이블)

## 주요 변동 사항
(보고서 내에서 확인 가능한 신규 편입, 제외, 변동 내용을 구체적으로 기술)

## 사업영역 변화 분석
(종속회사 구성을 통해 파악되는 기업의 사업 방향성, 확장/축소 영역)

## 시사점
(투자자/이해관계자 관점의 시사점 3~5개, 각각 구체적으로)""",
        "user_prompt_template": """아래는 {corp_name}의 {fiscal_year}년 사업보고서 전문입니다.
이 보고서에서 연결대상 종속회사 현황을 추출하고 분석해주세요.

---
{report_text}""",
    },
    {
        "analysis_type": "rnd",
        "label": "R&D/투자 분석",
        "system_prompt": """당신은 기업 R&D 및 투자 전략을 분석하는 전문 애널리스트입니다.
주어진 사업보고서에서 연구개발 활동과 투자 현황을 분석해주세요.

반드시 아래 형식의 마크다운으로 응답하세요:

## 요약
(R&D 및 투자 현황 전체 요약 2~3문장)

## 연구개발 영역
| 연구 분야 | 주요 내용 | 투자금액(원) | 비고 |
(보고서에서 확인 가능한 R&D 영역별 정리)

## 핵심 기술 투자
(핵심 기술에 대한 투자 내역, 방향성 분석)

## 시설 투자
(생산설비, 공장, 연구소 등 유형자산 투자 현황)

## 유무형 투자
(특허, 라이선스, 소프트웨어, 영업권 등 무형자산 및 기타 투자)

## 투자 전략 분석
(전체적인 투자 방향성, 경쟁사 대비 특징적인 투자 패턴)

## 시사점
(R&D/투자 관점의 시사점 3~5개)""",
        "user_prompt_template": """아래는 {corp_name}의 {fiscal_year}년 사업보고서 전문입니다.
이 보고서에서 연구개발 활동과 투자 현황을 분석해주세요.

---
{report_text}""",
    },
    {
        "analysis_type": "national_tech",
        "label": "국가전략기술 분석",
        "system_prompt": """당신은 국가전략기술 분야의 전문 분석가입니다.
주어진 사업보고서에서 국가전략기술 관련 사업 및 연구 활동을 분석해주세요.

국가전략기술 분야:
- 반도체·디스플레이
- 이차전지
- 첨단 모빌리티 (자율주행, 전기차, UAM 등)
- 차세대 원자력
- 첨단바이오
- 우주항공·해양
- 수소
- 사이버보안
- 인공지능
- 차세대 통신
- 첨단로봇·제조
- 양자기술

반드시 아래 형식의 마크다운으로 응답하세요:

## 요약
(해당 기업의 국가전략기술 관련 활동 전체 요약 2~3문장)

## 관련 국가전략기술 분야
| 기술 분야 | 관련도 | 주요 활동 |
(해당하는 국가전략기술 분야별 관련도를 상/중/하로 평가)

## 분야별 상세 분석
(각 관련 분야에 대해 구체적인 사업/연구/투자 내용 서술)

## 정부 정책 연계
(국가 R&D 과제 참여, 정부 지원사업, 규제 대응 등)

## 시사점
(국가전략기술 관점의 시사점 3~5개)""",
        "user_prompt_template": """아래는 {corp_name}의 {fiscal_year}년 사업보고서 전문입니다.
이 보고서에서 국가전략기술 분야와 관련된 사업 및 연구 활동을 분석해주세요.

---
{report_text}""",
    },
]


def seed_default_prompts(db: Session) -> None:
    """DB에 기본 프롬프트가 없으면 시딩."""
    for prompt_data in DEFAULT_PROMPTS:
        existing = db.query(PromptTemplate).filter_by(
            analysis_type=prompt_data["analysis_type"]
        ).first()
        if not existing:
            db.add(PromptTemplate(**prompt_data))
    db.commit()
```

- [ ] **Step 3: backend/app/services/analysis_service.py 생성**

DB에서 프롬프트 로드 → Gemini 호출 → DB 업데이트. 큐 워커에서 호출됨:

```python
import json

from sqlalchemy.orm import Session

from app.models import Analysis, PromptTemplate
from app.services.gemini_client import generate, MODEL_NAME
from app.services.report_service import extract_text_from_report

VALID_TYPES = {"subsidiary", "rnd", "national_tech"}


async def run_analysis(db: Session, analysis_id: int) -> None:
    """analysis_id에 해당하는 분석을 실행. 큐 워커에서 호출."""
    analysis = db.query(Analysis).get(analysis_id)
    if not analysis:
        return

    analysis.status = "running"
    db.commit()

    try:
        template = db.query(PromptTemplate).filter_by(
            analysis_type=analysis.analysis_type
        ).first()
        if not template:
            raise ValueError(f"프롬프트 템플릿이 없습니다: {analysis.analysis_type}")

        report = analysis.report
        report_text = extract_text_from_report(report.file_path)
        if not report_text:
            raise ValueError("보고서 텍스트를 추출할 수 없습니다.")

        max_chars = 2_000_000
        if len(report_text) > max_chars:
            report_text = report_text[:max_chars]

        user_prompt = template.user_prompt_template.format(
            corp_name=report.company.corp_name,
            fiscal_year=report.fiscal_year,
            report_text=report_text,
        )

        result_text = await generate(template.system_prompt, user_prompt)

        analysis.result_summary = result_text
        analysis.result_json = json.dumps({"raw_response": result_text}, ensure_ascii=False)
        analysis.model_name = MODEL_NAME
        analysis.status = "completed"
        db.commit()

    except Exception as e:
        analysis.status = "failed"
        analysis.error_message = str(e)
        db.commit()
```

- [ ] **Step 4: backend/app/services/analysis_queue.py 생성**

asyncio.Queue 기반 백그라운드 워커:

```python
import asyncio
import logging

from app.database import SessionLocal
from app.services.analysis_service import run_analysis

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[int] = asyncio.Queue()
_current_analysis_id: int | None = None


def enqueue(analysis_id: int) -> None:
    """분석 작업을 큐에 추가."""
    _queue.put_nowait(analysis_id)


def get_queue_info() -> dict:
    """큐 상태 정보 반환."""
    return {
        "pending_count": _queue.qsize(),
        "running": {"analysis_id": _current_analysis_id} if _current_analysis_id else None,
    }


async def worker() -> None:
    """큐에서 분석 작업을 하나씩 꺼내 실행하는 무한 루프 워커."""
    global _current_analysis_id
    while True:
        analysis_id = await _queue.get()
        _current_analysis_id = analysis_id
        try:
            db = SessionLocal()
            try:
                await run_analysis(db, analysis_id)
            finally:
                db.close()
        except Exception:
            logger.exception(f"분석 실행 실패: analysis_id={analysis_id}")
        finally:
            _current_analysis_id = None
            _queue.task_done()
```

- [ ] **Step 5: backend/app/routers/prompts.py 생성**


프롬프트 조회/수정 API:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PromptTemplate
from app.schemas import PromptTemplateResponse, PromptTemplateUpdate

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptTemplateResponse])
def list_prompts(db: Session = Depends(get_db)):
    return db.query(PromptTemplate).order_by(PromptTemplate.analysis_type).all()


@router.get("/{analysis_type}", response_model=PromptTemplateResponse)
def get_prompt(analysis_type: str, db: Session = Depends(get_db)):
    template = db.query(PromptTemplate).filter_by(analysis_type=analysis_type).first()
    if not template:
        raise HTTPException(404, f"프롬프트를 찾을 수 없습니다: {analysis_type}")
    return template


@router.put("/{analysis_type}", response_model=PromptTemplateResponse)
def update_prompt(
    analysis_type: str,
    body: PromptTemplateUpdate,
    db: Session = Depends(get_db),
):
    template = db.query(PromptTemplate).filter_by(analysis_type=analysis_type).first()
    if not template:
        raise HTTPException(404, f"프롬프트를 찾을 수 없습니다: {analysis_type}")
    template.system_prompt = body.system_prompt
    template.user_prompt_template = body.user_prompt_template
    db.commit()
    db.refresh(template)
    return template
```

- [ ] **Step 6: 커밋**

```bash
git add backend/app/services/gemini_client.py backend/app/seed_prompts.py backend/app/services/analysis_service.py backend/app/services/analysis_queue.py backend/app/routers/prompts.py
git commit -m "feat: Gemini 클라이언트, 프롬프트 시딩/관리, asyncio 큐 기반 분석 서비스"
```

---

## Task 6: API 라우터 — 기업 관리

**Files:**
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/companies.py`

- [ ] **Step 1: backend/app/routers/__init__.py 생성**

```python
```

(빈 파일)

- [ ] **Step 2: backend/app/routers/companies.py 생성**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Report, Analysis
from app.schemas import (
    CompanyCreate, CompanyUpdate, CompanyResponse, CompanySearchResult,
)
from app.services.dart_client import search_companies

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=list[CompanyResponse])
def list_companies(db: Session = Depends(get_db)):
    companies = db.query(Company).order_by(Company.created_at.desc()).all()
    results = []
    for c in companies:
        report_count = db.query(func.count(Report.id)).filter(Report.company_id == c.id).scalar()
        latest = (
            db.query(func.max(Analysis.updated_at))
            .filter(Analysis.company_id == c.id)
            .scalar()
        )
        resp = CompanyResponse.model_validate(c)
        resp.report_count = report_count
        resp.latest_analysis_date = latest
        results.append(resp)
    return results


@router.get("/search", response_model=list[CompanySearchResult])
async def search(name: str):
    if len(name) < 2:
        raise HTTPException(400, "검색어는 2자 이상 입력하세요.")
    results = await search_companies(name)
    return [CompanySearchResult(**r) for r in results]


@router.post("", response_model=CompanyResponse, status_code=201)
def create_company(body: CompanyCreate, db: Session = Depends(get_db)):
    existing = db.query(Company).filter(Company.corp_code == body.corp_code).first()
    if existing:
        raise HTTPException(409, f"이미 등록된 기업입니다: {existing.corp_name}")
    company = Company(**body.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return CompanyResponse.model_validate(company)


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(company_id: int, body: CompanyUpdate, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(company, key, val)
    db.commit()
    db.refresh(company)
    return CompanyResponse.model_validate(company)


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")
    db.delete(company)
    db.commit()
```

- [ ] **Step 3: 커밋**

```bash
git add backend/app/routers/
git commit -m "feat: 기업 관리 API — CRUD + OpenDART 검색"
```

---

## Task 7: API 라우터 — 보고서 관리

**Files:**
- Create: `backend/app/routers/reports.py`

- [ ] **Step 1: backend/app/routers/reports.py 생성**

```python
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Report, Analysis
from app.schemas import ReportResponse, ReportDownloadRequest
from app.services.dart_client import list_reports
from app.services.report_service import download_and_extract, extract_text_from_report

router = APIRouter(tags=["reports"])


@router.get("/api/companies/{company_id}/reports", response_model=list[ReportResponse])
def get_reports(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")

    reports = (
        db.query(Report)
        .filter(Report.company_id == company_id)
        .order_by(Report.fiscal_year.desc())
        .all()
    )
    results = []
    for r in reports:
        count = db.query(func.count(Analysis.id)).filter(Analysis.report_id == r.id).scalar()
        resp = ReportResponse.model_validate(r)
        resp.analysis_count = count
        results.append(resp)
    return results


@router.post("/api/companies/{company_id}/reports/download", response_model=list[ReportResponse])
async def download_reports(
    company_id: int,
    body: ReportDownloadRequest,
    db: Session = Depends(get_db),
):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")

    bgn_de = f"{body.fiscal_year}0101" if body.fiscal_year else None
    end_de = f"{body.fiscal_year + 1}1231" if body.fiscal_year else None

    dart_reports = await list_reports(company.corp_code, bgn_de=bgn_de, end_de=end_de)

    if body.report_type:
        dart_reports = [r for r in dart_reports if r["report_type"] == body.report_type]

    downloaded = []
    for dr in dart_reports:
        existing = db.query(Report).filter_by(
            company_id=company_id, rcept_no=dr["rcept_no"]
        ).first()
        if existing:
            downloaded.append(existing)
            continue

        filing = dr.get("filing_date")
        fiscal_year = int(filing[:4]) if filing else (body.fiscal_year or 2024)

        file_path = await download_and_extract(company.corp_code, dr["rcept_no"], fiscal_year)

        report = Report(
            company_id=company_id,
            rcept_no=dr["rcept_no"],
            report_name=dr["report_name"],
            report_type=dr["report_type"],
            fiscal_year=fiscal_year,
            filing_date=filing,
            file_path=file_path,
            downloaded_at=datetime.utcnow(),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        downloaded.append(report)

    return [ReportResponse.model_validate(r) for r in downloaded]


@router.get("/api/companies/{company_id}/reports/check")
async def check_new_reports(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")

    dart_reports = await list_reports(company.corp_code)
    existing_rcepts = {
        r.rcept_no
        for r in db.query(Report.rcept_no).filter(Report.company_id == company_id).all()
    }

    new_reports = [r for r in dart_reports if r["rcept_no"] not in existing_rcepts]
    return {"new_count": len(new_reports), "reports": new_reports}


@router.get("/api/reports/{report_id}/content")
def get_report_content(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    if not report.file_path:
        raise HTTPException(404, "보고서 파일이 아직 다운로드되지 않았습니다.")

    text = extract_text_from_report(report.file_path)
    return {"report_id": report_id, "content": text[:50000]}
```

- [ ] **Step 2: 커밋**

```bash
git add backend/app/routers/reports.py
git commit -m "feat: 보고서 관리 API — 목록, 다운로드, 새 보고서 체크, 원문 조회"
```

---

## Task 8: API 라우터 — 분석 및 스케줄러

**Files:**
- Create: `backend/app/routers/analyses.py`
- Create: `backend/app/routers/scheduler.py`
- Create: `backend/app/scheduler.py`

- [ ] **Step 1: backend/app/routers/analyses.py 생성**

큐에 넣고 즉시 반환하는 비동기 방식:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Report, Analysis
from app.schemas import AnalysisRequest, AnalysisResponse, QueueStatus
from app.services.analysis_queue import enqueue, get_queue_info

VALID_TYPES = ("subsidiary", "rnd", "national_tech")

router = APIRouter(tags=["analyses"])


@router.post("/api/reports/{report_id}/analyze", response_model=AnalysisResponse)
def analyze_report(
    report_id: int,
    body: AnalysisRequest,
    db: Session = Depends(get_db),
):
    """분석 요청을 큐에 추가하고 즉시 반환. 백그라운드에서 처리됨."""
    report = db.query(Report).get(report_id)
    if not report:
        raise HTTPException(404, "보고서를 찾을 수 없습니다.")
    if not report.file_path:
        raise HTTPException(400, "보고서 파일이 아직 다운로드되지 않았습니다.")
    if body.analysis_type not in VALID_TYPES:
        raise HTTPException(400, f"지원하지 않는 분석 유형: {body.analysis_type}")

    # 기존 분석이 있으면 재사용 (status를 pending으로 리셋)
    existing = db.query(Analysis).filter_by(
        company_id=report.company_id,
        report_id=report.id,
        analysis_type=body.analysis_type,
    ).first()

    if existing:
        existing.status = "pending"
        existing.error_message = None
        db.commit()
        db.refresh(existing)
        enqueue(existing.id)
        return AnalysisResponse.model_validate(existing)

    analysis = Analysis(
        company_id=report.company_id,
        report_id=report.id,
        analysis_type=body.analysis_type,
        status="pending",
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    enqueue(analysis.id)
    return AnalysisResponse.model_validate(analysis)


@router.post("/api/companies/{company_id}/analyze-all")
def analyze_all(company_id: int, db: Session = Depends(get_db)):
    """해당 기업의 모든 보고서 × 모든 분석 유형을 일괄 큐에 추가."""
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, "기업을 찾을 수 없습니다.")

    reports = db.query(Report).filter(
        Report.company_id == company_id,
        Report.file_path.isnot(None),
    ).all()

    queued = 0
    for report in reports:
        for atype in VALID_TYPES:
            existing = db.query(Analysis).filter_by(
                company_id=company_id,
                report_id=report.id,
                analysis_type=atype,
            ).first()

            if existing and existing.status == "completed":
                continue  # 이미 완료된 건 건너뜀

            if existing:
                existing.status = "pending"
                existing.error_message = None
                db.commit()
                enqueue(existing.id)
            else:
                analysis = Analysis(
                    company_id=company_id,
                    report_id=report.id,
                    analysis_type=atype,
                    status="pending",
                )
                db.add(analysis)
                db.commit()
                db.refresh(analysis)
                enqueue(analysis.id)
            queued += 1

    return {"message": f"{queued}건의 분석이 큐에 추가되었습니다.", "queued": queued}


@router.get("/api/reports/{report_id}/analyses", response_model=list[AnalysisResponse])
def get_report_analyses(report_id: int, db: Session = Depends(get_db)):
    analyses = db.query(Analysis).filter(Analysis.report_id == report_id).all()
    return [AnalysisResponse.model_validate(a) for a in analyses]


@router.get("/api/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).get(analysis_id)
    if not analysis:
        raise HTTPException(404, "분석 결과를 찾을 수 없습니다.")
    return AnalysisResponse.model_validate(analysis)


@router.get("/api/companies/{company_id}/analyses", response_model=list[AnalysisResponse])
def get_company_analyses(company_id: int, db: Session = Depends(get_db)):
    analyses = (
        db.query(Analysis)
        .filter(Analysis.company_id == company_id)
        .order_by(Analysis.report_id.desc(), Analysis.analysis_type)
        .all()
    )
    return [AnalysisResponse.model_validate(a) for a in analyses]


@router.get("/api/queue/status", response_model=QueueStatus)
def queue_status():
    return get_queue_info()
```

- [ ] **Step 2: backend/app/scheduler.py 생성**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.models import Company
from app.services.dart_client import list_reports
from app.services.report_service import download_and_extract
from app.models import Report

scheduler = AsyncIOScheduler()


async def check_and_download_reports():
    """등록된 모든 활성 기업의 새 보고서를 체크하고 다운로드."""
    db = SessionLocal()
    try:
        companies = db.query(Company).filter(Company.is_active == True).all()
        for company in companies:
            try:
                dart_reports = await list_reports(company.corp_code)
                existing_rcepts = {
                    r.rcept_no
                    for r in db.query(Report.rcept_no).filter(
                        Report.company_id == company.id
                    ).all()
                }

                for dr in dart_reports:
                    if dr["rcept_no"] in existing_rcepts:
                        continue

                    filing = dr.get("filing_date")
                    fiscal_year = int(filing[:4]) if filing else 2024

                    file_path = await download_and_extract(
                        company.corp_code, dr["rcept_no"], fiscal_year
                    )

                    from datetime import datetime
                    report = Report(
                        company_id=company.id,
                        rcept_no=dr["rcept_no"],
                        report_name=dr["report_name"],
                        report_type=dr["report_type"],
                        fiscal_year=fiscal_year,
                        filing_date=filing,
                        file_path=file_path,
                        downloaded_at=datetime.utcnow(),
                    )
                    db.add(report)
                    db.commit()
            except Exception:
                continue
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        check_and_download_reports,
        trigger=IntervalTrigger(hours=settings.scheduler_interval_hours),
        id="check_reports",
        replace_existing=True,
    )
    scheduler.start()


def shutdown_scheduler():
    scheduler.shutdown(wait=False)
```

- [ ] **Step 3: backend/app/routers/scheduler.py 생성**

```python
from fastapi import APIRouter

from app.config import settings
from app.scheduler import scheduler, check_and_download_reports
from app.schemas import SchedulerStatus

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/status", response_model=SchedulerStatus)
def get_status():
    job = scheduler.get_job("check_reports")
    return SchedulerStatus(
        is_running=scheduler.running,
        next_run_time=job.next_run_time if job else None,
        interval_hours=settings.scheduler_interval_hours,
    )


@router.post("/run-now")
async def run_now():
    await check_and_download_reports()
    return {"message": "실행 완료"}
```

- [ ] **Step 4: 커밋**

```bash
git add backend/app/routers/analyses.py backend/app/routers/scheduler.py backend/app/scheduler.py
git commit -m "feat: 분석 API, 스케줄러 API, APScheduler 작업 정의"
```

---

## Task 9: FastAPI 메인 앱 조립

**Files:**
- Create: `backend/app/main.py`

- [ ] **Step 1: backend/app/main.py 생성**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import asyncio

from app.config import settings
from app.database import Base, engine, SessionLocal
from app.scheduler import start_scheduler, shutdown_scheduler
from app.seed_prompts import seed_default_prompts
from app.services.analysis_queue import worker as queue_worker
from app.routers import companies, reports, analyses, scheduler
from app.routers import prompts as prompts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작: DB 테이블 생성 + 기본 프롬프트 시딩 + 데이터 디렉터리 확보 + 스케줄러 + 큐 워커
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_default_prompts(db)
    finally:
        db.close()
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    start_scheduler()
    worker_task = asyncio.create_task(queue_worker())
    yield
    # 종료: 스케줄러 정지 + 큐 워커 취소
    worker_task.cancel()
    shutdown_scheduler()


app = FastAPI(
    title="기업 DART 사업보고서 분석",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(reports.router)
app.include_router(analyses.router)
app.include_router(scheduler.router)
app.include_router(prompts_router.router)
```

- [ ] **Step 2: 로컬에서 백엔드 실행 확인**

```bash
cd backend
pip install -r requirements.txt
DATA_DIR=./data uvicorn app.main:app --reload --port 8016
```

브라우저에서 `http://localhost:8016/docs` 접속하여 Swagger UI 확인.

- [ ] **Step 3: 커밋**

```bash
git add backend/app/main.py
git commit -m "feat: FastAPI 메인 앱 — 라우터 등록, lifespan, CORS"
```

---

## Task 10: 프론트엔드 프로젝트 초기화

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`

- [ ] **Step 1: Vite + React + TypeScript 프로젝트 생성**

```bash
cd frontend
npm create vite@latest . -- --template react-ts
```

이미 디렉터리에 파일이 있으면 빈 디렉터리에서 생성 후 복사하거나, 수동으로 파일을 생성.

- [ ] **Step 2: 의존성 설치**

```bash
cd frontend
npm install react-router-dom react-markdown
npm install -D tailwindcss @tailwindcss/vite
```

- [ ] **Step 3: vite.config.ts 작성**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5185,
    proxy: {
      "/api": {
        target: "http://localhost:8016",
        changeOrigin: true,
      },
    },
  },
});
```

- [ ] **Step 4: frontend/index.html 작성**

```html
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>기업 DART 분석</title>
    <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin />
    <link
      href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"
      rel="stylesheet"
    />
    <link
      href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300..800;1,9..40,300..800&family=JetBrains+Mono:wght@400;500&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: 커밋**

```bash
git add frontend/package.json frontend/tsconfig.json frontend/tsconfig.app.json frontend/vite.config.ts frontend/tailwind.config.js frontend/postcss.config.js frontend/index.html
git commit -m "chore: 프론트엔드 프로젝트 초기화 — Vite, React, Tailwind, 폰트"
```

---

## Task 11: 프론트엔드 글로벌 스타일 및 타입 정의

**Files:**
- Create: `frontend/src/index.css`
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/main.tsx`

- [ ] **Step 1: frontend/src/index.css 작성**

```css
@import "tailwindcss";

@theme {
  --font-sans: "Pretendard", "DM Sans", -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;

  --color-navy: #1B2A4A;
  --color-navy-light: #2D4A7A;
  --color-accent: #2563EB;
  --color-accent-light: #3B82F6;
  --color-surface: #FFFFFF;
  --color-background: #FAFBFC;
  --color-border: #E5E7EB;
  --color-border-dark: #D1D5DB;
  --color-text-primary: #111827;
  --color-text-secondary: #6B7280;
  --color-text-tertiary: #9CA3AF;
  --color-success: #059669;
  --color-success-bg: #ECFDF5;
  --color-warning: #D97706;
  --color-warning-bg: #FFFBEB;
  --color-danger: #DC2626;
  --color-danger-bg: #FEF2F2;
}

body {
  font-family: var(--font-sans);
  background-color: var(--color-background);
  color: var(--color-text-primary);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Print styles */
@media print {
  body {
    background: white;
    color: black;
    font-size: 11pt;
  }

  .no-print {
    display: none !important;
  }

  .print-only {
    display: block !important;
  }

  table {
    border-collapse: collapse;
  }

  table th,
  table td {
    border: 1px solid #ccc;
    padding: 4px 8px;
  }
}

.print-only {
  display: none;
}
```

- [ ] **Step 2: frontend/src/types/index.ts 작성**

```typescript
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

- [ ] **Step 3: frontend/src/main.tsx 작성**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
```

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/index.css frontend/src/types/ frontend/src/main.tsx
git commit -m "feat: 글로벌 스타일(Pretendard/DM Sans, 커스텀 테마) + TypeScript 타입 정의"
```

---

## Task 12: API 클라이언트

**Files:**
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: frontend/src/api/client.ts 작성**

```typescript
import type {
  Company,
  CompanySearchResult,
  Report,
  Analysis,
  SchedulerStatus,
  PromptTemplate,
} from "../types";

const BASE = "/api";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

// --- Companies ---

export function fetchCompanies(): Promise<Company[]> {
  return request("/companies");
}

export function searchCompanies(name: string): Promise<CompanySearchResult[]> {
  return request(`/companies/search?name=${encodeURIComponent(name)}`);
}

export function createCompany(body: {
  corp_code: string;
  corp_name: string;
  stock_code?: string | null;
}): Promise<Company> {
  return request("/companies", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateCompany(
  id: number,
  body: { corp_name?: string; stock_code?: string; is_active?: boolean },
): Promise<Company> {
  return request(`/companies/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function deleteCompany(id: number): Promise<void> {
  return request(`/companies/${id}`, { method: "DELETE" });
}

// --- Reports ---

export function fetchReports(companyId: number): Promise<Report[]> {
  return request(`/companies/${companyId}/reports`);
}

export function downloadReports(
  companyId: number,
  body: { fiscal_year?: number; report_type?: string },
): Promise<Report[]> {
  return request(`/companies/${companyId}/reports/download`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function checkNewReports(
  companyId: number,
): Promise<{ new_count: number; reports: Record<string, string>[] }> {
  return request(`/companies/${companyId}/reports/check`);
}

export function fetchReportContent(
  reportId: number,
): Promise<{ report_id: number; content: string }> {
  return request(`/reports/${reportId}/content`);
}

// --- Analyses ---

export function runAnalysis(
  reportId: number,
  analysisType: string,
): Promise<Analysis> {
  return request(`/reports/${reportId}/analyze`, {
    method: "POST",
    body: JSON.stringify({ analysis_type: analysisType }),
  });
}

export function fetchReportAnalyses(reportId: number): Promise<Analysis[]> {
  return request(`/reports/${reportId}/analyses`);
}

export function fetchAnalysis(analysisId: number): Promise<Analysis> {
  return request(`/analyses/${analysisId}`);
}

export function fetchCompanyAnalyses(companyId: number): Promise<Analysis[]> {
  return request(`/companies/${companyId}/analyses`);
}

export function analyzeAll(
  companyId: number,
): Promise<{ message: string; queued: number }> {
  return request(`/companies/${companyId}/analyze-all`, { method: "POST" });
}

export function fetchQueueStatus(): Promise<{
  pending_count: number;
  running: { analysis_id: number } | null;
}> {
  return request("/queue/status");
}

// --- Scheduler ---

export function fetchSchedulerStatus(): Promise<SchedulerStatus> {
  return request("/scheduler/status");
}

export function runSchedulerNow(): Promise<{ message: string }> {
  return request("/scheduler/run-now", { method: "POST" });
}

// --- Prompts ---

export function fetchPrompts(): Promise<PromptTemplate[]> {
  return request("/prompts");
}

export function fetchPrompt(analysisType: string): Promise<PromptTemplate> {
  return request(`/prompts/${analysisType}`);
}

export function updatePrompt(
  analysisType: string,
  body: { system_prompt: string; user_prompt_template: string },
): Promise<PromptTemplate> {
  return request(`/prompts/${analysisType}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/api/
git commit -m "feat: API 클라이언트 — 기업/보고서/분석/스케줄러/프롬프트 전체 엔드포인트"
```

---

## Task 13: Layout 컴포넌트

**Files:**
- Create: `frontend/src/components/Layout.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: frontend/src/components/Layout.tsx 작성**

Editorial/Corporate 톤의 상단 네비게이션. 네이비 배경에 흰색 텍스트. 절제된 그림자.

```tsx
import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { fetchSchedulerStatus } from "../api/client";
import type { SchedulerStatus } from "../types";

export default function Layout() {
  const location = useLocation();
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);

  useEffect(() => {
    fetchSchedulerStatus().then(setScheduler).catch(() => {});
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-background">
      {/* Top Navigation */}
      <header className="no-print sticky top-0 z-50 border-b border-border bg-navy text-white shadow-sm">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          <Link
            to="/"
            className="flex items-center gap-2.5 font-semibold tracking-tight transition-opacity hover:opacity-80"
          >
            <span className="text-lg">DART</span>
            <span className="text-sm font-normal text-white/60">
              기업 사업보고서 분석
            </span>
          </Link>

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
            <Link
              to="/settings/prompts"
              className="text-sm text-white/60 transition-colors hover:text-white"
            >
              설정
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: frontend/src/App.tsx 작성**

```tsx
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import CompanyList from "./pages/CompanyList";
import CompanyDetail from "./pages/CompanyDetail";
import PromptSettings from "./pages/PromptSettings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<CompanyList />} />
        <Route path="/companies/:id" element={<CompanyDetail />} />
        <Route path="/settings/prompts" element={<PromptSettings />} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/Layout.tsx frontend/src/App.tsx
git commit -m "feat: Layout 컴포넌트 — 네이비 상단 네비게이션 + 라우팅 설정"
```

---

## Task 14: 기업 목록 페이지 (CompanyList)

**Files:**
- Create: `frontend/src/pages/CompanyList.tsx`
- Create: `frontend/src/components/CompanyForm.tsx`
- Create: `frontend/src/components/CompanySearch.tsx`

- [ ] **Step 1: frontend/src/components/CompanySearch.tsx 작성**

OpenDART 기업 검색 모달 내부 검색 UI:

```tsx
import { useState } from "react";
import { searchCompanies } from "../api/client";
import type { CompanySearchResult } from "../types";

interface Props {
  onSelect: (result: CompanySearchResult) => void;
}

export default function CompanySearch({ onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CompanySearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSearch = async () => {
    if (query.length < 2) return;
    setLoading(true);
    setError("");
    try {
      const data = await searchCompanies(query);
      setResults(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder="기업명을 입력하세요 (2자 이상)"
          className="flex-1 rounded-md border border-border bg-white px-3 py-2 text-sm outline-none transition-colors focus:border-accent"
        />
        <button
          onClick={handleSearch}
          disabled={loading || query.length < 2}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-light disabled:opacity-50"
        >
          {loading ? "검색중..." : "검색"}
        </button>
      </div>

      {error && (
        <p className="mt-2 text-sm text-danger">{error}</p>
      )}

      {results.length > 0 && (
        <div className="mt-3 max-h-64 overflow-y-auto rounded-md border border-border">
          {results.map((r) => (
            <button
              key={r.corp_code}
              onClick={() => onSelect(r)}
              className="flex w-full items-center justify-between border-b border-border px-4 py-3 text-left text-sm transition-colors last:border-b-0 hover:bg-background"
            >
              <div>
                <span className="font-medium text-text-primary">
                  {r.corp_name}
                </span>
                {r.stock_code && (
                  <span className="ml-2 font-mono text-xs text-text-tertiary">
                    {r.stock_code}
                  </span>
                )}
              </div>
              <span className="font-mono text-xs text-text-tertiary">
                {r.corp_code}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: frontend/src/components/CompanyForm.tsx 작성**

기업 등록 모달:

```tsx
import { useState } from "react";
import CompanySearch from "./CompanySearch";
import { createCompany } from "../api/client";
import type { CompanySearchResult } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export default function CompanyForm({ open, onClose, onCreated }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  const handleSelect = async (result: CompanySearchResult) => {
    setLoading(true);
    setError("");
    try {
      await createCompany({
        corp_code: result.corp_code,
        corp_name: result.corp_name,
        stock_code: result.stock_code,
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-border bg-surface p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text-primary">
            기업 등록
          </h2>
          <button
            onClick={onClose}
            className="text-text-tertiary transition-colors hover:text-text-primary"
          >
            ✕
          </button>
        </div>

        <p className="mb-4 text-sm text-text-secondary">
          OpenDART에서 기업을 검색하고 선택하면 자동으로 등록됩니다.
        </p>

        <CompanySearch onSelect={handleSelect} />

        {loading && (
          <p className="mt-3 text-sm text-text-secondary">등록 중...</p>
        )}
        {error && (
          <p className="mt-3 text-sm text-danger">{error}</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: frontend/src/pages/CompanyList.tsx 작성**

메인 대시보드:

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchCompanies } from "../api/client";
import CompanyForm from "../components/CompanyForm";
import type { Company } from "../types";

export default function CompanyList() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    fetchCompanies()
      .then(setCompanies)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const filtered = companies.filter((c) =>
    c.corp_name.toLowerCase().includes(search.toLowerCase()),
  );

  const getStatusBadge = (c: Company) => {
    if (c.latest_analysis_date) {
      return (
        <span className="inline-flex items-center rounded-full bg-success-bg px-2.5 py-0.5 text-xs font-medium text-success">
          분석완료
        </span>
      );
    }
    if (c.report_count > 0) {
      return (
        <span className="inline-flex items-center rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning">
          보고서만
        </span>
      );
    }
    return (
      <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-text-tertiary">
        대기
      </span>
    );
  };

  return (
    <div>
      {/* Page Header */}
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-navy">
            분석 대상 기업
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            OpenDART 사업보고서 기반 기업 분석 대시보드
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-accent-light hover:shadow-md"
        >
          + 기업 등록
        </button>
      </div>

      {/* Search */}
      <div className="mb-6">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="등록된 기업 검색..."
          className="w-full max-w-sm rounded-lg border border-border bg-surface px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-text-tertiary focus:border-accent focus:ring-1 focus:ring-accent/20"
        />
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-background/50">
              <th className="px-6 py-3.5 text-left font-semibold text-text-secondary">
                기업명
              </th>
              <th className="px-6 py-3.5 text-left font-semibold text-text-secondary">
                종목코드
              </th>
              <th className="px-6 py-3.5 text-center font-semibold text-text-secondary">
                보고서
              </th>
              <th className="px-6 py-3.5 text-left font-semibold text-text-secondary">
                최근 분석
              </th>
              <th className="px-6 py-3.5 text-center font-semibold text-text-secondary">
                상태
              </th>
              <th className="px-6 py-3.5 text-right font-semibold text-text-secondary" />
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-text-tertiary">
                  로딩 중...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-12 text-center text-text-tertiary">
                  {companies.length === 0
                    ? "등록된 기업이 없습니다. 기업을 등록해주세요."
                    : "검색 결과가 없습니다."}
                </td>
              </tr>
            ) : (
              filtered.map((c) => (
                <tr
                  key={c.id}
                  className="border-b border-border transition-colors last:border-b-0 hover:bg-background/30"
                >
                  <td className="px-6 py-4">
                    <Link
                      to={`/companies/${c.id}`}
                      className="font-medium text-navy hover:text-accent"
                    >
                      {c.corp_name}
                    </Link>
                  </td>
                  <td className="px-6 py-4 font-mono text-xs text-text-secondary">
                    {c.stock_code || "—"}
                  </td>
                  <td className="px-6 py-4 text-center font-mono text-text-secondary">
                    {c.report_count}건
                  </td>
                  <td className="px-6 py-4 text-text-secondary">
                    {c.latest_analysis_date
                      ? new Date(c.latest_analysis_date).toLocaleDateString("ko-KR")
                      : "—"}
                  </td>
                  <td className="px-6 py-4 text-center">{getStatusBadge(c)}</td>
                  <td className="px-6 py-4 text-right">
                    <Link
                      to={`/companies/${c.id}`}
                      className="text-sm text-accent hover:underline"
                    >
                      상세 →
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <CompanyForm
        open={showForm}
        onClose={() => setShowForm(false)}
        onCreated={load}
      />
    </div>
  );
}
```

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/pages/CompanyList.tsx frontend/src/components/CompanyForm.tsx frontend/src/components/CompanySearch.tsx
git commit -m "feat: 기업 목록 페이지 — 대시보드 테이블, 기업 등록 모달, OpenDART 검색"
```

---

## Task 15: 기업 상세 페이지 (CompanyDetail)

**Files:**
- Create: `frontend/src/pages/CompanyDetail.tsx`
- Create: `frontend/src/components/ReportTable.tsx`
- Create: `frontend/src/components/DownloadModal.tsx`
- Create: `frontend/src/components/AnalysisView.tsx`

- [ ] **Step 1: frontend/src/components/DownloadModal.tsx 작성**

```tsx
import { useState } from "react";
import { downloadReports } from "../api/client";

interface Props {
  open: boolean;
  companyId: number;
  onClose: () => void;
  onDownloaded: () => void;
}

export default function DownloadModal({
  open,
  companyId,
  onClose,
  onDownloaded,
}: Props) {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [reportType, setReportType] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  const handleDownload = async () => {
    setLoading(true);
    setError("");
    try {
      await downloadReports(companyId, {
        fiscal_year: year,
        report_type: reportType || undefined,
      });
      onDownloaded();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-text-primary">
            보고서 다운로드
          </h2>
          <button
            onClick={onClose}
            className="text-text-tertiary transition-colors hover:text-text-primary"
          >
            ✕
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-text-secondary">
              사업연도
            </label>
            <select
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus:border-accent"
            >
              {Array.from({ length: 10 }, (_, i) => currentYear - i).map(
                (y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ),
              )}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-text-secondary">
              보고서 유형
            </label>
            <select
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
              className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm outline-none focus:border-accent"
            >
              <option value="">전체</option>
              <option value="사업보고서">사업보고서</option>
              <option value="반기보고서">반기보고서</option>
              <option value="분기보고서">분기보고서</option>
            </select>
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          <button
            onClick={handleDownload}
            disabled={loading}
            className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent-light disabled:opacity-50"
          >
            {loading ? "다운로드 중..." : "다운로드 시작"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: frontend/src/components/ReportTable.tsx 작성**

```tsx
import type { Report } from "../types";

interface Props {
  reports: Report[];
  onAnalyze: (reportId: number) => void;
}

const ANALYSIS_TYPES = ["subsidiary", "rnd", "national_tech"];

export default function ReportTable({ reports, onAnalyze }: Props) {
  if (reports.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-surface py-16 text-center text-sm text-text-tertiary">
        아직 다운로드된 보고서가 없습니다.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-background/50">
            <th className="px-5 py-3 text-left font-semibold text-text-secondary">
              보고서명
            </th>
            <th className="px-5 py-3 text-left font-semibold text-text-secondary">
              유형
            </th>
            <th className="px-5 py-3 text-center font-semibold text-text-secondary">
              사업연도
            </th>
            <th className="px-5 py-3 text-left font-semibold text-text-secondary">
              공시일
            </th>
            <th className="px-5 py-3 text-center font-semibold text-text-secondary">
              분석
            </th>
            <th className="px-5 py-3 text-right font-semibold text-text-secondary" />
          </tr>
        </thead>
        <tbody>
          {reports.map((r) => (
            <tr
              key={r.id}
              className="border-b border-border transition-colors last:border-b-0 hover:bg-background/30"
            >
              <td className="px-5 py-3.5 font-medium text-text-primary">
                {r.report_name}
              </td>
              <td className="px-5 py-3.5">
                <span className="inline-flex rounded-full border border-border px-2 py-0.5 text-xs text-text-secondary">
                  {r.report_type}
                </span>
              </td>
              <td className="px-5 py-3.5 text-center font-mono text-text-secondary">
                {r.fiscal_year}
              </td>
              <td className="px-5 py-3.5 text-text-secondary">
                {r.filing_date || "—"}
              </td>
              <td className="px-5 py-3.5 text-center">
                <span
                  className={`font-mono text-xs ${
                    r.analysis_count >= ANALYSIS_TYPES.length
                      ? "text-success"
                      : r.analysis_count > 0
                        ? "text-warning"
                        : "text-text-tertiary"
                  }`}
                >
                  {r.analysis_count}/{ANALYSIS_TYPES.length}
                </span>
              </td>
              <td className="px-5 py-3.5 text-right">
                <button
                  onClick={() => onAnalyze(r.id)}
                  className="text-sm text-accent hover:underline"
                >
                  분석 →
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: frontend/src/components/AnalysisView.tsx 작성**

마크다운 렌더링 + 재분석/PDF 출력 + **자동 폴링으로 분석 진행 상태 실시간 표시**:

```tsx
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { runAnalysis } from "../api/client";
import type { Analysis, Report } from "../types";

interface Props {
  companyId: number;
  reports: Report[];
  analyses: Analysis[];
  analysisType: "subsidiary" | "rnd" | "national_tech";
  onRefresh: () => void;
}

const TYPE_LABELS: Record<string, string> = {
  subsidiary: "종속회사 변동 분석",
  rnd: "R&D/투자 분석",
  national_tech: "국가전략기술 분석",
};

const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  pending: { text: "대기중", color: "text-text-tertiary bg-gray-100" },
  running: { text: "분석중", color: "text-warning bg-warning-bg" },
  completed: { text: "완료", color: "text-success bg-success-bg" },
  failed: { text: "실패", color: "text-danger bg-danger-bg" },
};

export default function AnalysisView({
  companyId,
  reports,
  analyses,
  analysisType,
  onRefresh,
}: Props) {
  const relevantAnalyses = analyses.filter(
    (a) => a.analysis_type === analysisType,
  );

  // pending 또는 running 상태가 있으면 5초마다 자동 폴링
  const hasActiveJob = relevantAnalyses.some(
    (a) => a.status === "pending" || a.status === "running",
  );
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    if (hasActiveJob) {
      intervalRef.current = setInterval(onRefresh, 5000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [hasActiveJob, onRefresh]);

  const years = [
    ...new Set(
      reports
        .filter((r) =>
          relevantAnalyses.some((a) => a.report_id === r.id),
        )
        .map((r) => r.fiscal_year),
    ),
  ].sort((a, b) => b - a);

  const [selectedYear, setSelectedYear] = useState<number | null>(
    years[0] || null,
  );

  const selectedReport = reports.find((r) => r.fiscal_year === selectedYear);
  const selectedAnalysis = relevantAnalyses.find(
    (a) => selectedReport && a.report_id === selectedReport.id,
  );

  const handleRun = async (reportId: number) => {
    try {
      await runAnalysis(reportId, analysisType);
      onRefresh();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const unanalyzedReports = reports.filter(
    (r) =>
      r.file_path &&
      !relevantAnalyses.some((a) => a.report_id === r.id),
  );

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-navy">
          {TYPE_LABELS[analysisType]}
        </h3>
        <div className="no-print flex items-center gap-3">
          {hasActiveJob && (
            <span className="flex items-center gap-1.5 text-sm text-warning">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-warning" />
              처리중...
            </span>
          )}
          {selectedReport && (
            <button
              onClick={() => handleRun(selectedReport.id)}
              className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-background"
            >
              재분석
            </button>
          )}
          <button
            onClick={() => window.print()}
            className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-background"
          >
            PDF 출력
          </button>
        </div>
      </div>

      {/* Year chips */}
      {years.length > 0 && (
        <div className="no-print mb-6 flex flex-wrap gap-2">
          {years.map((y) => {
            const yearAnalysis = relevantAnalyses.find(
              (a) => reports.find((r) => r.id === a.report_id)?.fiscal_year === y,
            );
            const statusInfo = yearAnalysis
              ? STATUS_LABELS[yearAnalysis.status]
              : null;
            return (
              <button
                key={y}
                onClick={() => setSelectedYear(y)}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  selectedYear === y
                    ? "bg-navy text-white"
                    : "border border-border bg-surface text-text-secondary hover:bg-background"
                }`}
              >
                {y}
                {statusInfo && yearAnalysis?.status !== "completed" && (
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[10px] ${statusInfo.color}`}
                  >
                    {statusInfo.text}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Analysis Content */}
      {selectedAnalysis && selectedAnalysis.status === "completed" ? (
        <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-3 border-b border-border pb-4">
            <span className="text-xs text-text-tertiary">
              모델: {selectedAnalysis.model_name}
            </span>
            <span className="text-xs text-text-tertiary">
              분석일:{" "}
              {new Date(selectedAnalysis.updated_at).toLocaleDateString("ko-KR")}
            </span>
          </div>
          <article className="prose prose-sm max-w-none prose-headings:text-navy prose-h2:text-base prose-h2:font-semibold prose-h3:text-sm prose-h3:font-semibold prose-p:text-text-primary prose-p:leading-relaxed prose-table:text-sm prose-th:bg-background/50 prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2 prose-li:text-text-primary">
            <ReactMarkdown>{selectedAnalysis.result_summary || ""}</ReactMarkdown>
          </article>
        </div>
      ) : selectedAnalysis &&
        (selectedAnalysis.status === "pending" ||
          selectedAnalysis.status === "running") ? (
        <div className="flex flex-col items-center rounded-xl border border-border bg-surface py-16">
          <div className="mb-4 h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent" />
          <p className="text-sm text-text-secondary">
            {selectedAnalysis.status === "pending"
              ? "큐에서 대기 중입니다..."
              : "Gemini가 보고서를 분석하고 있습니다..."}
          </p>
          <p className="mt-1 text-xs text-text-tertiary">
            이 페이지를 벗어나도 분석은 계속 진행됩니다.
          </p>
        </div>
      ) : selectedAnalysis && selectedAnalysis.status === "failed" ? (
        <div className="rounded-xl border border-danger/30 bg-danger-bg p-6">
          <p className="mb-2 font-medium text-danger">분석 실패</p>
          <p className="text-sm text-text-secondary">
            {selectedAnalysis.error_message}
          </p>
          <button
            onClick={() => handleRun(selectedAnalysis.report_id)}
            className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white"
          >
            재시도
          </button>
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-surface py-16 text-center">
          {unanalyzedReports.length > 0 ? (
            <div>
              <p className="mb-4 text-sm text-text-tertiary">
                아직 이 유형의 분석이 수행되지 않았습니다.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {unanalyzedReports.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => handleRun(r.id)}
                    className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-light"
                  >
                    {r.fiscal_year} {r.report_type} 분석
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-text-tertiary">
              보고서를 먼저 다운로드해주세요.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: frontend/src/pages/CompanyDetail.tsx 작성**

```tsx
import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  fetchCompanies,
  fetchReports,
  fetchCompanyAnalyses,
  deleteCompany,
  analyzeAll,
} from "../api/client";
import ReportTable from "../components/ReportTable";
import DownloadModal from "../components/DownloadModal";
import AnalysisView from "../components/AnalysisView";
import type { Company, Report, Analysis } from "../types";

const TABS = [
  { key: "reports", label: "보고서" },
  { key: "subsidiary", label: "종속회사 분석" },
  { key: "rnd", label: "R&D/투자 분석" },
  { key: "national_tech", label: "국가전략기술" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function CompanyDetail() {
  const { id } = useParams<{ id: string }>();
  const companyId = Number(id);

  const [company, setCompany] = useState<Company | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [tab, setTab] = useState<TabKey>("reports");
  const [showDownload, setShowDownload] = useState(false);

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

  useEffect(() => {
    load();
  }, [companyId]);

  const handleDelete = async () => {
    if (!confirm("이 기업과 관련 데이터를 모두 삭제하시겠습니까?")) return;
    await deleteCompany(companyId);
    window.location.href = "/";
  };

  if (!company) {
    return (
      <div className="py-16 text-center text-text-tertiary">로딩 중...</div>
    );
  }

  return (
    <div>
      {/* Breadcrumb + Header */}
      <div className="mb-6">
        <Link
          to="/"
          className="no-print text-sm text-text-tertiary hover:text-accent"
        >
          ← 기업 목록
        </Link>
        <div className="mt-3 flex items-end justify-between">
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
          <div className="no-print flex gap-2">
            <button
              onClick={() => setShowDownload(true)}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-light"
            >
              보고서 다운로드
            </button>
            <button
              onClick={async () => {
                const result = await analyzeAll(companyId);
                alert(result.message);
                load();
              }}
              className="rounded-lg border border-accent px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent/5"
            >
              전체 분석
            </button>
            <button
              onClick={handleDelete}
              className="rounded-lg border border-danger/30 px-3 py-2 text-sm text-danger transition-colors hover:bg-danger-bg"
            >
              삭제
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="no-print mb-6 border-b border-border">
        <div className="flex gap-0">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`border-b-2 px-5 py-3 text-sm font-medium transition-colors ${
                tab === t.key
                  ? "border-accent text-accent"
                  : "border-transparent text-text-secondary hover:text-text-primary"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {tab === "reports" && (
        <ReportTable
          reports={reports}
          onAnalyze={(reportId) => {
            setTab("subsidiary");
          }}
        />
      )}

      {tab !== "reports" && (
        <AnalysisView
          companyId={companyId}
          reports={reports}
          analyses={analyses}
          analysisType={tab}
          onRefresh={load}
        />
      )}

      <DownloadModal
        open={showDownload}
        companyId={companyId}
        onClose={() => setShowDownload(false)}
        onDownloaded={load}
      />
    </div>
  );
}
```

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/pages/CompanyDetail.tsx frontend/src/components/ReportTable.tsx frontend/src/components/DownloadModal.tsx frontend/src/components/AnalysisView.tsx
git commit -m "feat: 기업 상세 페이지 — 보고서 테이블, 분석 탭, 다운로드 모달, 마크다운 렌더링"
```

---

## Task 16: PDF 출력용 컴포넌트 및 인쇄 스타일

**Files:**
- Create: `frontend/src/components/PrintableReport.tsx`
- Modify: `frontend/src/components/AnalysisView.tsx` (PrintableReport 통합)

- [ ] **Step 1: frontend/src/components/PrintableReport.tsx 작성**

```tsx
import ReactMarkdown from "react-markdown";
import type { Analysis } from "../types";

interface Props {
  companyName: string;
  fiscalYear: number;
  analysis: Analysis;
}

const TYPE_LABELS: Record<string, string> = {
  subsidiary: "연결대상 종속회사 변동 분석",
  rnd: "연구개발 및 투자 분석",
  national_tech: "국가전략기술 관련 분석",
};

export default function PrintableReport({
  companyName,
  fiscalYear,
  analysis,
}: Props) {
  return (
    <div className="print-only">
      <div className="mb-8 border-b-2 border-black pb-4">
        <h1 className="text-xl font-bold">{companyName}</h1>
        <h2 className="mt-1 text-base text-gray-700">
          {fiscalYear}년 {TYPE_LABELS[analysis.analysis_type]}
        </h2>
        <p className="mt-2 text-xs text-gray-500">
          분석일: {new Date(analysis.updated_at).toLocaleDateString("ko-KR")} |
          모델: {analysis.model_name}
        </p>
      </div>
      <article className="prose prose-sm max-w-none">
        <ReactMarkdown>{analysis.result_summary || ""}</ReactMarkdown>
      </article>
      <footer className="mt-12 border-t border-gray-300 pt-4 text-xs text-gray-400">
        DART 사업보고서 AI 분석 보고서 — 자동 생성됨
      </footer>
    </div>
  );
}
```

- [ ] **Step 2: AnalysisView.tsx에 PrintableReport 통합**

`AnalysisView.tsx`의 분석 결과 표시 부분 끝에 PrintableReport를 추가. `selectedAnalysis`가 있을 때 아래 코드를 분석 결과 `</div>` 바로 뒤에 삽입:

```tsx
// AnalysisView.tsx 상단 import 추가:
import PrintableReport from "./PrintableReport";

// selectedAnalysis 렌더링 블록 안, article 닫는 태그 뒤에 추가:
{selectedAnalysis && selectedReport && (
  <PrintableReport
    companyName={/* company name - pass via props */}
    fiscalYear={selectedReport.fiscal_year}
    analysis={selectedAnalysis}
  />
)}
```

`AnalysisView`의 Props에 `companyName: string`을 추가하고, `CompanyDetail.tsx`에서 `companyName={company.corp_name}`을 전달.

**수정할 AnalysisView Props:**

```typescript
interface Props {
  companyId: number;
  companyName: string;   // 추가
  reports: Report[];
  analyses: Analysis[];
  analysisType: "subsidiary" | "rnd" | "national_tech";
  onRefresh: () => void;
}
```

**CompanyDetail.tsx에서 호출 부분 수정:**

```tsx
<AnalysisView
  companyId={companyId}
  companyName={company.corp_name}
  reports={reports}
  analyses={analyses}
  analysisType={tab}
  onRefresh={load}
/>
```

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/PrintableReport.tsx frontend/src/components/AnalysisView.tsx frontend/src/pages/CompanyDetail.tsx
git commit -m "feat: PDF 출력용 PrintableReport 컴포넌트 + 인쇄 레이아웃 통합"
```

---

## Task 17: 프롬프트 설정 페이지

**Files:**
- Create: `frontend/src/pages/PromptSettings.tsx`

- [ ] **Step 1: frontend/src/pages/PromptSettings.tsx 작성**

프롬프트 3종을 카드 형태로 표시하고, 각각 시스템 프롬프트와 유저 프롬프트를 텍스트에어리어로 편집:

```tsx
import { useEffect, useState } from "react";
import { fetchPrompts, updatePrompt } from "../api/client";
import type { PromptTemplate } from "../types";

export default function PromptSettings() {
  const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  // 편집 상태를 별도로 관리
  const [edits, setEdits] = useState<
    Record<string, { system_prompt: string; user_prompt_template: string }>
  >({});

  useEffect(() => {
    fetchPrompts()
      .then((data) => {
        setPrompts(data);
        const initial: typeof edits = {};
        for (const p of data) {
          initial[p.analysis_type] = {
            system_prompt: p.system_prompt,
            user_prompt_template: p.user_prompt_template,
          };
        }
        setEdits(initial);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (analysisType: string) => {
    const edit = edits[analysisType];
    if (!edit) return;
    setSaving(analysisType);
    setSaved(null);
    try {
      await updatePrompt(analysisType, edit);
      setSaved(analysisType);
      setTimeout(() => setSaved(null), 2000);
    } catch (e: any) {
      alert(e.message);
    } finally {
      setSaving(null);
    }
  };

  if (loading) {
    return (
      <div className="py-16 text-center text-text-tertiary">로딩 중...</div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight text-navy">
          프롬프트 설정
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Gemini LLM 분석에 사용되는 프롬프트를 편집합니다. 변경 즉시 반영됩니다.
        </p>
      </div>

      {/* 플레이스홀더 안내 */}
      <div className="mb-6 rounded-lg border border-border bg-surface px-5 py-4">
        <h3 className="mb-2 text-sm font-semibold text-text-primary">
          사용 가능한 플레이스홀더
        </h3>
        <div className="flex flex-wrap gap-3 text-sm">
          <code className="rounded bg-background px-2 py-1 font-mono text-xs text-accent">
            {"{corp_name}"}
          </code>
          <span className="text-text-secondary">기업명</span>
          <code className="rounded bg-background px-2 py-1 font-mono text-xs text-accent">
            {"{fiscal_year}"}
          </code>
          <span className="text-text-secondary">사업연도</span>
          <code className="rounded bg-background px-2 py-1 font-mono text-xs text-accent">
            {"{report_text}"}
          </code>
          <span className="text-text-secondary">
            보고서 전문 (유저 프롬프트에서 사용)
          </span>
        </div>
      </div>

      {/* 프롬프트 카드들 */}
      <div className="space-y-6">
        {prompts.map((p) => (
          <div
            key={p.analysis_type}
            className="rounded-xl border border-border bg-surface shadow-sm"
          >
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <div>
                <h2 className="font-semibold text-navy">{p.label}</h2>
                <span className="font-mono text-xs text-text-tertiary">
                  {p.analysis_type}
                </span>
              </div>
              <div className="flex items-center gap-3">
                {saved === p.analysis_type && (
                  <span className="text-sm text-success">저장됨</span>
                )}
                <button
                  onClick={() => handleSave(p.analysis_type)}
                  disabled={saving === p.analysis_type}
                  className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-light disabled:opacity-50"
                >
                  {saving === p.analysis_type ? "저장중..." : "저장"}
                </button>
              </div>
            </div>

            <div className="space-y-4 p-6">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  시스템 프롬프트
                </label>
                <textarea
                  value={edits[p.analysis_type]?.system_prompt ?? ""}
                  onChange={(e) =>
                    setEdits((prev) => ({
                      ...prev,
                      [p.analysis_type]: {
                        ...prev[p.analysis_type],
                        system_prompt: e.target.value,
                      },
                    }))
                  }
                  rows={12}
                  className="w-full rounded-lg border border-border bg-background px-4 py-3 font-mono text-sm leading-relaxed text-text-primary outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/20"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-text-secondary">
                  유저 프롬프트 템플릿
                </label>
                <textarea
                  value={
                    edits[p.analysis_type]?.user_prompt_template ?? ""
                  }
                  onChange={(e) =>
                    setEdits((prev) => ({
                      ...prev,
                      [p.analysis_type]: {
                        ...prev[p.analysis_type],
                        user_prompt_template: e.target.value,
                      },
                    }))
                  }
                  rows={6}
                  className="w-full rounded-lg border border-border bg-background px-4 py-3 font-mono text-sm leading-relaxed text-text-primary outline-none transition-colors focus:border-accent focus:ring-1 focus:ring-accent/20"
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/pages/PromptSettings.tsx
git commit -m "feat: 프롬프트 설정 페이지 — 분석 프롬프트 웹 UI 편집"
```

---

## Task 18: Nginx 설정 및 프론트엔드 Dockerfile

**Files:**
- Create: `frontend/nginx.conf`
- Create: `frontend/Dockerfile`

- [ ] **Step 1: frontend/nginx.conf 작성**

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy
    location /api/ {
        proxy_pass http://backend:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

- [ ] **Step 2: frontend/Dockerfile 작성**

```dockerfile
# Build stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 3: 커밋**

```bash
git add frontend/nginx.conf frontend/Dockerfile
git commit -m "feat: Nginx 설정(SPA fallback, API 프록시) + 프론트엔드 multi-stage Dockerfile"
```

---

## Task 19: PORT_REGISTRY 업데이트

**Files:**
- Modify: `../PORT_REGISTRY.md`

- [ ] **Step 1: PORT_REGISTRY.md에 16번 프로젝트 섹션 추가**

`15_EWS` 섹션 뒤에 추가:

```markdown
### 16_firm-dart-analysis (기업 DART 사업보고서 분석)

| 서비스 | 호스트 포트 | 컨테이너 포트 | 기술 |
|--------|------------|--------------|------|
| backend | **8016** | 8000 | FastAPI + APScheduler |
| frontend (prod) | **8097** | 80 | Nginx (정적 빌드) |
| frontend (dev) | **5185** | 5173 | Vite dev 서버 |
```

"전체 사용 포트 요약" 섹션에 추가:

```
8016        16_firm-dart-analysis backend
8097        16_firm-dart-analysis frontend (Nginx)
5185        16_firm-dart-analysis frontend-dev (Vite dev)
```

- [ ] **Step 2: 커밋**

```bash
git add ../PORT_REGISTRY.md
git commit -m "docs: PORT_REGISTRY에 16_firm-dart-analysis 포트 등록"
```

---

## Task 20: 통합 테스트 및 Docker 빌드 확인

- [ ] **Step 1: 백엔드 로컬 실행 확인**

```bash
cd backend
pip install -r requirements.txt
DATA_DIR=./data uvicorn app.main:app --reload --port 8016
```

브라우저에서 `http://localhost:8016/docs` 접속 확인.

- [ ] **Step 2: 프론트엔드 로컬 실행 확인**

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5185` 접속. 기업 목록 페이지가 표시되는지 확인. 기업 등록 모달이 열리는지 확인.

- [ ] **Step 3: 기업 등록 기능 테스트**

1. "기업 등록" 클릭
2. "삼성전자" 검색
3. 결과에서 삼성전자 선택 → 등록 확인

- [ ] **Step 4: 보고서 다운로드 테스트**

1. 삼성전자 상세 페이지 이동
2. "보고서 다운로드" 클릭 → 2024년 사업보고서 다운로드
3. 보고서 탭에 보고서 목록 표시 확인

- [ ] **Step 5: 분석 실행 테스트**

1. 종속회사 분석 탭 이동
2. "분석" 버튼 클릭 → Gemini API 호출 → 결과 마크다운 표시 확인

- [ ] **Step 6: 프롬프트 설정 페이지 테스트**

1. 상단 네비게이션 "설정" 클릭 → `/settings/prompts` 이동
2. 프롬프트 3종이 카드 형태로 표시되는지 확인
3. 시스템 프롬프트 텍스트 수정 → "저장" 클릭 → "저장됨" 표시 확인
4. 페이지 새로고침 후 수정 내용이 유지되는지 확인

- [ ] **Step 7: Docker Compose 빌드 확인**

```bash
cd 16_firm-dart-analysis
docker compose build
docker compose up -d
```

`http://localhost:8097` 접속하여 프론트엔드 정상 동작 확인.
`http://localhost:8016/docs` 접속하여 API docs 확인.

- [ ] **Step 8: 커밋**

```bash
git add -A
git commit -m "chore: 통합 테스트 후 최종 조정"
```
