"""보고서 텍스트 추출 — ZIP에서 바로 읽는다.

디스크에 풀어 두면 원본의 13배가 쌓인다(실측 11건: ZIP 7MB vs 풀린 것 88MB).
압축 해제는 보고서 1건당 수십 밀리초라 매번 푸는 편이 싸다 —
실측에서 디렉터리 읽기 8~83ms, ZIP 읽기 10~82ms로 차이가 없었다.
"""
import zipfile

from app.services.report_service import extract_text_from_report


def make_zip(path, files: dict[str, str]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, body in files.items():
            zf.writestr(name, body)


def test_reads_xml_from_zip_without_unpacking(tmp_path):
    make_zip(tmp_path / "0001.zip", {"doc.xml": "<p>사업의 내용</p>"})
    assert "사업의 내용" in extract_text_from_report(str(tmp_path))
    # 풀린 디렉터리를 만들지 않는다
    assert not (tmp_path / "extracted").exists()


def test_ignores_non_document_entries(tmp_path):
    make_zip(tmp_path / "0001.zip", {
        "doc.xml": "<p>본문</p>", "image.png": "\x89PNG", "note.txt": "메모"})
    text = extract_text_from_report(str(tmp_path))
    assert "본문" in text
    assert "메모" not in text


def test_reads_files_in_stable_order(tmp_path):
    make_zip(tmp_path / "0001.zip", {"b.xml": "<p>둘째</p>", "a.xml": "<p>첫째</p>"})
    text = extract_text_from_report(str(tmp_path))
    assert text.index("첫째") < text.index("둘째")


def test_max_chars_stops_early(tmp_path):
    """앞부분만 필요한 호출(보고서 미리보기)이 전체를 풀지 않게 한다."""
    make_zip(tmp_path / "0001.zip", {
        "a.xml": "<p>" + "가" * 5000 + "</p>", "b.xml": "<p>" + "나" * 5000 + "</p>"})
    text = extract_text_from_report(str(tmp_path), max_chars=100)
    assert "나" not in text          # 파일 하나를 읽고 멈춘다


def test_missing_or_broken_zip_returns_empty(tmp_path):
    """분석은 실패해야 하지만 예외로 죽어서는 안 된다 — 호출부가 빈 텍스트를 검사한다."""
    assert extract_text_from_report(str(tmp_path)) == ""
    (tmp_path / "broken.zip").write_bytes(b"not a zip")
    assert extract_text_from_report(str(tmp_path)) == ""


def test_multiple_zips_are_all_read(tmp_path):
    """재다운로드로 ZIP이 여러 개 남아도 전부 읽는다."""
    make_zip(tmp_path / "0001.zip", {"a.xml": "<p>먼저</p>"})
    make_zip(tmp_path / "0002.zip", {"a.xml": "<p>나중</p>"})
    text = extract_text_from_report(str(tmp_path))
    assert "먼저" in text and "나중" in text
