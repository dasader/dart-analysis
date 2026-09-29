import io
import logging
import re
import shutil
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


def delete_report_files(report: Report) -> None:
    """보고서 ZIP을 지운다. 남겨 두면 같은 폴더에 다른 보고서를 받을 때 섞일 근거가 된다
    (`_report_zip` 참조). 연도 폴더가 비면 폴더도 지운다."""
    if not report.file_path:
        return
    folder = Path(report.file_path)
    (folder / f"{report.rcept_no}.zip").unlink(missing_ok=True)
    try:
        folder.rmdir()          # 비어 있을 때만 지워진다
    except OSError:
        pass


def delete_company_files(corp_code: str) -> None:
    """기업의 보고서 폴더(`reports/{corp_code}`)를 통째로 지운다."""
    shutil.rmtree(settings.reports_dir / corp_code, ignore_errors=True)


def _report_zip(file_path: str, rcept_no: str) -> Path | None:
    """보고서 자신의 ZIP(`{rcept_no}.zip`).

    폴더(`reports/{corp}/{year}`)의 ZIP을 **전부** 읽으면 다른 보고서가 섞인다 — 보고서를 지워도
    ZIP이 남던 때가 있었고, 사업연도를 교정해도 파일은 옛 연도 폴더에 남는다. 그 폴더에 다른
    보고서를 받으면 두 텍스트가 합쳐져 입력이 2배가 되고 분석이 섞인다.
    자기 ZIP이 없으면(옛 데이터) 폴더에 하나뿐일 때만 그것을 쓴다. 여럿이면 어느 것인지 모르므로
    읽지 않는다 — 조용히 섞는 대신 빈 텍스트(구역 추출 실패)로 드러낸다.
    """
    folder = Path(file_path)
    own = folder / f"{rcept_no}.zip"
    if own.exists():
        return own
    zips = sorted(folder.glob("*.zip"))
    if len(zips) == 1:
        return zips[0]
    if zips:
        logger.warning("자기 ZIP(%s.zip)이 없고 폴더에 ZIP이 %d개라 읽지 않음: %s",
                       rcept_no, len(zips), folder)
    return None


def extract_text_from_report(file_path: str, rcept_no: str, max_chars: int | None = None) -> str:
    """저장된 보고서 ZIP(`{rcept_no}.zip`)에서 텍스트를 추출.

    ZIP 안의 XML/HTML을 **메모리에서** 읽어 태그를 제거한 텍스트를 반환한다.
    풀어서 저장하지 않는 이유는 download_report 주석 참조.

    max_chars가 주어지면 누적 길이가 그 값에 도달하는 즉시 읽기를 중단한다
    (앞부분만 필요한 호출용 — 전체 head/tail 트런케이션이 필요하면 None으로).
    """
    zip_path = _report_zip(file_path, rcept_no)
    if zip_path is None:
        return ""

    texts: list[str] = []
    total = 0
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
                    break
    except zipfile.BadZipFile:
        logger.warning("깨진 ZIP, 건너뜀: %s", zip_path)
    return "\n\n".join(texts)


def _strip_tags(text: str) -> str:
    """HTML/XML 태그 제거."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()
