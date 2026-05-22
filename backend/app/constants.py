from enum import Enum


class AnalysisType(str, Enum):
    """분석 유형. seed_prompts.py의 analysis_type 및 PromptTemplate과 1:1 대응."""

    SUBSIDIARY = "subsidiary"
    RND = "rnd"
    NATIONAL_TECH = "national_tech"


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# 분석 유형 전체 목록 (일괄 분석·큐 투입 시 순회용)
ANALYSIS_TYPES: tuple[AnalysisType, ...] = tuple(AnalysisType)

# 수집 대상 보고서 유형 (사업보고서만 수집)
REPORT_TYPE_ANNUAL = "사업보고서"
