from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Text,
    ForeignKey, UniqueConstraint, Table,
)
from sqlalchemy.orm import relationship

from app.database import Base

# 기업-태그 M2M 조인 테이블 (Company 클래스보다 먼저 정의)
company_tags = Table(
    "company_tags",
    Base.metadata,
    Column("company_id", Integer, ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    corp_code = Column(String, unique=True, nullable=False)
    corp_name = Column(String, nullable=False)
    stock_code = Column(String, nullable=True)
    # 특허 출원인과 조인하기 위한 법인등록번호(13자리, 숫자만). company.json에서 채운다.
    jurir_no = Column(String, nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reports = relationship("Report", back_populates="company", cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="company", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=company_tags, back_populates="companies")


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


class BatchJob(Base):
    """Gemini Batch API 작업 1건. 담당 보고서들을 report_ids로 들고 있는다.

    Analysis 테이블은 건드리지 않는다 — JSONL의 key가 report_id라 결과 분배에 충분하다.
    """

    __tablename__ = "batch_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String, unique=True, nullable=False)   # batches/xxx
    file_name = Column(String, nullable=True)                # 업로드한 JSONL (files/xxx)
    model_name = Column(String, nullable=False)
    thinking_level = Column(String, nullable=False)
    state = Column(String, nullable=False)                   # JOB_STATE_*
    report_ids = Column(Text, nullable=False)                # JSON 배열
    request_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_type = Column(String, unique=True, nullable=False)
    label = Column(String, nullable=False)
    system_prompt = Column(Text, nullable=False)
    user_prompt_template = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ApplicantCorp(Base):
    """특허 출원인의 법인·사업자 번호 (KIPRIS 벌크 `CORP_APPLICANT.txt`).

    특허 출원인명은 한글 표기("주식회사 엘지화학"), DART는 영문 표기("(주)LG화학")를
    쓰므로 이름으로는 매칭되지 않는다. 법인번호로 정확 조인한다.
    실측: 385,256건 중 법인번호 보유 99.4%.

    분기별 갱신이므로 적재는 전량 교체다 (scripts/load_applicant_corps.py).
    """

    __tablename__ = "applicant_corps"

    applicant_code = Column(String, primary_key=True)   # 특허고객번호
    applicant_name = Column(String, nullable=False, index=True)
    applicant_name_eng = Column(String, nullable=True)
    jurir_no = Column(String, nullable=True, index=True)  # 법인번호 13자리(숫자만)
    bizr_no = Column(String, nullable=True, index=True)   # 사업자번호 10자리(숫자만)


class DartCorp(Base):
    """DART 전체 기업 색인 (corpCode.xml + 법인번호).

    `Company`는 **우리가 추적하기로 한** 기업이고, 이쪽은 DART에 존재하는 전체 목록이다.
    특허 출원인의 법인번호로 corp_code를 역인출하려면 이 색인이 필요하다 —
    corpCode.xml에는 법인번호가 없어(corp_code·corp_name·stock_code·modify_date뿐)
    기업마다 company.json을 한 번씩 불러 채워야 한다.

    전체 11만여 개를 다 채우면 호출이 과하므로 **상장사부터** 채운다.
    """

    __tablename__ = "dart_corps"

    corp_code = Column(String, primary_key=True)
    corp_name = Column(String, nullable=False, index=True)
    stock_code = Column(String, nullable=True, index=True)   # 있으면 상장사
    jurir_no = Column(String, nullable=True, index=True)      # company.json으로 채운다
    # 조회했으나 법인번호가 없던 경우를 구분해야 재시도를 반복하지 않는다
    jurir_checked_at = Column(DateTime, nullable=True)


class ApiCall(Base):
    """외부 API 호출 1건. KIPRIS 무료 한도(월 1,000회)를 지키기 위한 계측.

    실패 호출도 기록한다 — 한도 집계가 성공 여부와 무관할 수 있어 보수적으로 센다.
    """

    __tablename__ = "api_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False, index=True)   # kipris, dart, ...
    operation = Column(String, nullable=False)
    query = Column(String, nullable=True)
    ok = Column(Boolean, nullable=False, default=True)
    note = Column(String, nullable=True)
    period = Column(String, nullable=False, index=True)     # YYYY-MM (한도 주기)
    called_at = Column(DateTime, default=datetime.utcnow)


class AppSetting(Base):
    """런타임에 바꿀 수 있는 설정. 값이 없으면 .env 기본값을 쓴다.

    .env는 앱 시작 시 한 번만 읽히므로, 재시작 없이 바꿔야 하는 값만 여기 둔다.
    """

    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    companies = relationship("Company", secondary=company_tags, back_populates="tags")
