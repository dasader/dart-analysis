import io
import re
import zipfile
from pathlib import Path

from app.config import settings
from app.services.dart_client import download_document


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


def extract_text_from_report(file_path: str) -> str:
    """저장된 보고서 디렉터리에서 텍스트를 추출.

    extracted/ 디렉터리 내의 XML/HTML 파일들을 읽어 태그를 제거한 텍스트를 반환.
    """
    extracted_dir = Path(file_path) / "extracted"
    if not extracted_dir.exists():
        return ""

    texts = []
    for f in sorted(extracted_dir.iterdir()):
        if f.suffix.lower() in (".xml", ".html", ".htm"):
            raw = f.read_text(encoding="utf-8", errors="ignore")
            clean = _strip_tags(raw)
            if clean.strip():
                texts.append(clean)

    return "\n\n".join(texts)


def _strip_tags(text: str) -> str:
    """HTML/XML 태그 제거."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()
