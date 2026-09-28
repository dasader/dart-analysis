import io
import logging
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

logger = logging.getLogger(__name__)


async def download_report(corp_code: str, rcept_no: str, fiscal_year: int) -> str:
    """보고서 ZIP 다운로드 → 저장. 저장 디렉터리 경로 반환.

    **디스크에 풀어 두지 않는다.** 실측 11건에서 ZIP 7MB인데 풀어 놓은 것이 88MB로
    원본의 13배였다(디스크의 93%). 읽을 때 메모리에서 풀면 되고, 압축 해제는
    보고서 1건당 수십 밀리초라 저장해 둘 이유가 없다.
    """
    report_dir = settings.reports_dir / corp_code / str(fiscal_year)
    report_dir.mkdir(parents=True, exist_ok=True)

    content = await download_document(rcept_no)
    (report_dir / f"{rcept_no}.zip").write_bytes(content)

    # 받은 것이 ZIP이 아니면 여기서 드러내는 편이 낫다 — 나중에 빈 텍스트로 조용히 실패한다
    try:
        with zipfile.ZipFile(io.BytesIO(content)):
            pass
    except zipfile.BadZipFile:
        logger.warning("ZIP이 아닌 응답: corp_code=%s rcept_no=%s (%d바이트)",
                       corp_code, rcept_no, len(content))

    return str(report_dir)


async def create_report_from_dart(
    db: Session, company: Company, dart_report: dict, fallback_year: int
) -> Report:
    """DART 보고서 dict로 ZIP을 받아 추출하고 Report 레코드를 생성·커밋한다.

    fiscal_year는 보고서명에서 추출하되, 없으면 fallback_year를 사용.
    """
    fiscal_year = extract_fiscal_year_from_name(dart_report["report_name"]) or fallback_year
    file_path = await download_report(company.corp_code, dart_report["rcept_no"], fiscal_year)

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


_DOC_SUFFIXES = (".xml", ".html", ".htm")


def extract_text_from_report(file_path: str, max_chars: int | None = None) -> str:
    """저장된 보고서 ZIP에서 텍스트를 추출.

    ZIP 안의 XML/HTML을 **메모리에서** 읽어 태그를 제거한 텍스트를 반환한다.
    풀어서 저장하지 않는 이유는 download_report 주석 참조.

    max_chars가 주어지면 누적 길이가 그 값에 도달하는 즉시 읽기를 중단한다
    (앞부분만 필요한 호출용 — 전체 head/tail 트런케이션이 필요하면 None으로).
    """
    texts: list[str] = []
    total = 0

    for zip_path in sorted(Path(file_path).glob("*.zip")):
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in sorted(zf.namelist()):
                    if not name.lower().endswith(_DOC_SUFFIXES):
                        continue
                    clean = _strip_tags(zf.read(name).decode("utf-8", errors="ignore"))
                    if not clean.strip():
                        continue
                    texts.append(clean)
                    total += len(clean)
                    if max_chars is not None and total >= max_chars:
                        return "\n\n".join(texts)
        except zipfile.BadZipFile:
            logger.warning("깨진 ZIP, 건너뜀: %s", zip_path)

    return "\n\n".join(texts)


def _strip_tags(text: str) -> str:
    """HTML/XML 태그 제거."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()
