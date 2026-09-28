from pydantic import BaseModel, Field
from datetime import datetime, date

from app.constants import AnalysisType


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
    tags: list[TagResponse] = []

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
    analysis_type: AnalysisType


class AnalysisState(BaseModel):
    """분석 진행 상태만 — 기업 상세의 10초 폴링용. 본문(result_summary)은 수십 KB라 싣지 않는다."""
    id: int
    report_id: int
    analysis_type: str
    status: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnalysisResponse(AnalysisState):
    company_id: int
    result_json: str | None
    result_summary: str | None
    error_message: str | None
    model_name: str | None
    created_at: datetime


class QueueStatus(BaseModel):
    pending_count: int          # 제출 대기 중인 보고서 수
    running_batches: int        # 진행 중인 batch 작업 수
    running_reports: int        # 그 batch들이 담당하는 보고서 수


# --- Batch ---

class BatchJobResponse(BaseModel):
    id: int
    job_name: str
    model_name: str
    thinking_level: str
    state: str
    report_ids: list[int]
    request_count: int
    success_count: int
    failed_count: int
    error_message: str | None
    submitted_at: datetime | None
    completed_at: datetime | None
    is_terminal: bool


class ExtractionFailure(BaseModel):
    """구역 추출 실패 — 보고서 서식 변경 신호. LLM에는 보내지 않았다."""

    report_id: int
    company_id: int
    corp_name: str
    report_name: str
    fiscal_year: int
    reason: str
    failed_at: datetime | None


# --- Technology ---

class TechnologyCreate(BaseModel):
    name: str
    description: str
    keywords: list[str] | None = None      # 없으면 LLM이 뽑는다
    # 온보딩 상한(비용 통제). 0이면 후보 전체를 분석한다
    max_companies: int = Field(default=5, ge=0)


class TechnologyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    max_companies: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class TechCompanyResponse(BaseModel):
    id: int
    company_id: int | None
    corp_code: str | None
    corp_name: str | None
    applicant_name: str
    patent_count: int
    keyword_hits: list[str]
    status: str
    exclude_reason: str | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    is_new: bool          # 마지막 스캔에서 처음 나타났다
    is_gone: bool         # 마지막 스캔에 나오지 않았다


class KeywordStat(BaseModel):
    """마지막 스캔에서 키워드 1건이 몇 건을 물어 왔는지. broad면 정밀도가 급락한다."""
    word: str
    total: int
    broad: bool


class TechnologyResponse(BaseModel):
    id: int
    name: str
    description: str
    keywords: list[str]
    keyword_stats: list[KeywordStat] = []
    ipc_core: list[str] = []
    max_companies: int
    is_active: bool
    last_scanned_at: datetime | None
    created_at: datetime
    tracked_count: int
    available_count: int
    excluded_count: int


class TechnologyDetail(TechnologyResponse):
    companies: list[TechCompanyResponse]
    report_md: str | None = None
    report_generated_at: datetime | None = None
    report_basis: str | None = None


# --- App Settings ---

class AppSettingResponse(BaseModel):
    key: str
    label: str
    description: str
    value: bool


class AppSettingUpdate(BaseModel):
    value: bool


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
