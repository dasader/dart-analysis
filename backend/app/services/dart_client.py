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
    """보고서명에서 유형 분류.

    - 정정보고서: 일부 내용만 포함되어 분석 부적합 → 제외
    - 반기/분기보고서: 분석 대상 아님 → 제외
    - 사업보고서만 수집
    """
    if "정정" in name:
        return None
    if "사업보고서" in name:
        return "사업보고서"
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
