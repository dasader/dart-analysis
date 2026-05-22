import io
import re
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, Report
from app.services.dart_client import (
    download_document,
    extract_fiscal_year_from_name,
    parse_filing_date,
)


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


async def create_report_from_dart(
    db: Session, company: Company, dart_report: dict, fallback_year: int
) -> Report:
    """DART 보고서 dict로 ZIP을 받아 추출하고 Report 레코드를 생성·커밋한다.

    fiscal_year는 보고서명에서 추출하되, 없으면 fallback_year를 사용.
    """
    fiscal_year = extract_fiscal_year_from_name(dart_report["report_name"]) or fallback_year
    file_path = await download_and_extract(company.corp_code, dart_report["rcept_no"], fiscal_year)

    report = Report(
        company_id=company.id,
        rcept_no=dart_report["rcept_no"],
        report_name=dart_report["report_name"],
        report_type=dart_report["report_type"],
        fiscal_year=fiscal_year,
        filing_date=parse_filing_date(dart_report.get("filing_date")),
        file_path=file_path,
        downloaded_at=datetime.utcnow(),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def extract_text_from_report(file_path: str, max_chars: int | None = None) -> str:
    """저장된 보고서 디렉터리에서 텍스트를 추출.

    extracted/ 디렉터리 내의 XML/HTML 파일들을 읽어 태그를 제거한 텍스트를 반환.
    max_chars가 주어지면 누적 길이가 그 값에 도달하는 즉시 읽기를 중단한다
    (앞부분만 필요한 호출용 — 전체 head/tail 트런케이션이 필요하면 None으로).
    """
    extracted_dir = Path(file_path) / "extracted"
    if not extracted_dir.exists():
        return ""

    texts = []
    total = 0
    for f in sorted(extracted_dir.iterdir()):
        if f.suffix.lower() not in (".xml", ".html", ".htm"):
            continue
        clean = _strip_tags(f.read_text(encoding="utf-8", errors="ignore"))
        if not clean.strip():
            continue
        texts.append(clean)
        total += len(clean)
        if max_chars is not None and total >= max_chars:
            break

    return "\n\n".join(texts)


def _strip_tags(text: str) -> str:
    """HTML/XML 태그 제거."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()
