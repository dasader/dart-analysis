import asyncio
import io
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime

import httpx

from app.config import settings
from app.constants import REPORT_TYPE_ANNUAL

DART_BASE = "https://opendart.fss.or.kr/api"
CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"

# corpCode.xml은 전체 기업 목록(수 MB)이라 거의 변하지 않음 → 파싱 결과를 캐시
_CORP_CACHE_TTL = 24 * 3600
_corp_cache: list[dict] | None = None
_corp_cache_at: float = 0.0


def _parse_corp_zip(content: bytes) -> list[dict]:
    """corpCode.xml ZIP을 파싱해 전체 기업 목록을 반환 (블로킹 — executor에서 실행)."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        root = ET.fromstring(zf.read("CORPCODE.xml"))
    return [
        {
            "corp_code": item.findtext("corp_code", ""),
            "corp_name": item.findtext("corp_name", ""),
            "stock_code": item.findtext("stock_code", "") or None,
        }
        for item in root.iter("list")
    ]


async def _load_corp_list() -> list[dict]:
    """전체 기업 목록을 캐시에서 반환. 만료 시에만 다운로드·파싱."""
    global _corp_cache, _corp_cache_at
    now = time.monotonic()
    if _corp_cache is not None and now - _corp_cache_at < _CORP_CACHE_TTL:
        return _corp_cache

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            CORP_CODE_URL,
            params={"crtfc_key": settings.opendart_api_key},
        )
        resp.raise_for_status()

    loop = asyncio.get_running_loop()
    corps = await loop.run_in_executor(None, _parse_corp_zip, resp.content)
    _corp_cache = corps
    _corp_cache_at = now
    return corps


async def search_companies(name: str) -> list[dict]:
    """전체 기업 목록(캐시)에서 name이 포함된 기업을 최대 50건 반환."""
    needle = name.lower()
    corps = await _load_corp_list()
    matched = [c for c in corps if needle in c["corp_name"].lower()]
    return matched[:50]


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
    """보고서명에서 유형 분류.

    - 정정보고서: 일부 내용만 포함되어 분석 부적합 → 제외
    - 반기/분기보고서: 분석 대상 아님 → 제외
    - 사업보고서만 수집
    """
    if "정정" in name:
        return None
    if REPORT_TYPE_ANNUAL in name:
        return REPORT_TYPE_ANNUAL
    return None


def parse_filing_date(filing_str: str | None) -> date | None:
    """DART 접수일자(YYYYMMDD 문자열)를 date로 변환. 형식이 어긋나면 None."""
    if not filing_str:
        return None
    try:
        return datetime.strptime(filing_str, "%Y%m%d").date()
    except ValueError:
        return None


def extract_fiscal_year_from_name(report_name: str) -> int | None:
    """보고서명에서 사업연도 추출.

    '2025년도 사업보고서'       → 2025  (년 패턴)
    '사업보고서 (2025.12)'      → 2025  (YYYY.MM 패턴)
    '제60기 사업보고서'          → None  (연도 정보 없음)
    """
    # 우선순위 1: YYYY년 패턴
    m = re.search(r"(\d{4})년", report_name)
    if m:
        return int(m.group(1))
    # 우선순위 2: (YYYY.MM) 패턴 — "사업보고서 (2025.12)" 형식
    m = re.search(r"\((\d{4})\.\d{2}\)", report_name)
    if m:
        return int(m.group(1))
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
