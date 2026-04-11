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
