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


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_type = Column(String, unique=True, nullable=False)
    label = Column(String, nullable=False)
    system_prompt = Column(Text, nullable=False)
    user_prompt_template = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    companies = relationship("Company", secondary=company_tags, back_populates="tags")
