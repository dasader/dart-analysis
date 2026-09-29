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
    assert "사업의 내용" in extract_text_from_report(str(tmp_path), "0001")
    # 풀린 디렉터리를 만들지 않는다
    assert not (tmp_path / "extracted").exists()


def test_ignores_non_document_entries(tmp_path):
    make_zip(tmp_path / "0001.zip", {
        "doc.xml": "<p>본문</p>", "image.png": "\x89PNG", "note.txt": "메모"})
    text = extract_text_from_report(str(tmp_path), "0001")
    assert "본문" in text
    assert "메모" not in text


def test_reads_files_in_stable_order(tmp_path):
    make_zip(tmp_path / "0001.zip", {"b.xml": "<p>둘째</p>", "a.xml": "<p>첫째</p>"})
    text = extract_text_from_report(str(tmp_path), "0001")
    assert text.index("첫째") < text.index("둘째")


def test_max_chars_stops_early(tmp_path):
    """앞부분만 필요한 호출(보고서 미리보기)이 전체를 풀지 않게 한다."""
    make_zip(tmp_path / "0001.zip", {
        "a.xml": "<p>" + "가" * 5000 + "</p>", "b.xml": "<p>" + "나" * 5000 + "</p>"})
    text = extract_text_from_report(str(tmp_path), "0001", max_chars=100)
    assert "나" not in text          # 파일 하나를 읽고 멈춘다


def test_missing_or_broken_zip_returns_empty(tmp_path):
    """분석은 실패해야 하지만 예외로 죽어서는 안 된다 — 호출부가 빈 텍스트를 검사한다."""
    assert extract_text_from_report(str(tmp_path), "0001") == ""
    (tmp_path / "broken.zip").write_bytes(b"not a zip")
    assert extract_text_from_report(str(tmp_path), "0001") == ""


def test_reads_only_its_own_zip(tmp_path):
    """같은 기업·연도 폴더에 다른 보고서 ZIP이 있어도 섞지 않는다 — 지운 보고서의 ZIP이 남거나
    사업연도를 교정해도 파일이 옛 폴더에 남으면 한 폴더에 둘이 생긴다."""
    make_zip(tmp_path / "0001.zip", {"a.xml": "<p>내 보고서</p>"})
    make_zip(tmp_path / "0002.zip", {"a.xml": "<p>남의 보고서</p>"})
    text = extract_text_from_report(str(tmp_path), "0001")
    assert "내 보고서" in text and "남의 보고서" not in text


def test_legacy_single_zip_is_read_but_ambiguous_is_not(tmp_path):
    """자기 ZIP이 없는 옛 데이터: 하나뿐이면 그것을 읽고, 여럿이면 섞지 않고 빈 텍스트."""
    make_zip(tmp_path / "old.zip", {"a.xml": "<p>옛 보고서</p>"})
    assert "옛 보고서" in extract_text_from_report(str(tmp_path), "0001")
    make_zip(tmp_path / "other.zip", {"a.xml": "<p>다른 것</p>"})
    assert extract_text_from_report(str(tmp_path), "0001") == ""


def test_delete_report_files_removes_zip_and_empty_folder(tmp_path):
    from types import SimpleNamespace
    from app.services.report_service import delete_report_files
    year = tmp_path / "2025"
    year.mkdir()
    make_zip(year / "0001.zip", {"a.xml": "<p>x</p>"})
    make_zip(year / "0002.zip", {"a.xml": "<p>y</p>"})
    delete_report_files(SimpleNamespace(file_path=str(year), rcept_no="0001"))
    assert not (year / "0001.zip").exists() and (year / "0002.zip").exists()
    delete_report_files(SimpleNamespace(file_path=str(year), rcept_no="0002"))
    assert not year.exists()
