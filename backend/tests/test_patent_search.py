"""출원인 집계 검증 — API 호출 없이 순수 함수만."""
from app.services.patent_search import BROAD_THRESHOLD, aggregate_applicants


def result(word: str, total: int, patents: list[tuple[str, list[str]]]) -> dict:
    return {"word": word, "total": total,
            "items": [{"app_no": no, "applicants": apps} for no, apps in patents]}


def test_same_patent_counted_once_across_keywords():
    """같은 특허가 여러 키워드에 걸려도 한 번만 센다."""
    r1 = result("좁은키워드", 1000, [("10-1", ["가전자"]), ("10-2", ["나소재"])])
    r2 = result("다른키워드", 2000, [("10-1", ["가전자"]), ("10-3", ["가전자"])])

    counts, kws = aggregate_applicants([r1, r2])
    assert counts["가전자"] == 2      # 10-1 중복 제외, 10-1 + 10-3
    assert counts["나소재"] == 1


def test_keyword_set_tracks_where_applicant_appeared():
    """넓은 키워드 하나에서만 나온 대기업과 여러 키워드에 걸친 곳을 갈라야 한다."""
    narrow = result("황화물계 고체전해질", 4_635,
                    [("10-1", ["다모빌리티"]), ("10-2", ["라연구원"])])
    broad = result("리튬 이차전지", 65_760,
                   [("10-3", ["다모빌리티"]), ("10-4", ["마배터리"])])

    counts, kws = aggregate_applicants([narrow, broad])
    assert kws["다모빌리티"] == {"황화물계 고체전해질", "리튬 이차전지"}   # 두 키워드
    assert kws["마배터리"] == {"리튬 이차전지"}                        # 넓은 것에만
    assert kws["라연구원"] == {"황화물계 고체전해질"}


def test_joint_application_credits_every_applicant():
    """공동출원(| 구분)은 모든 출원인에게 센다."""
    r = result("키워드", 100, [("10-1", ["바화학", "사대학교"])])
    counts, kws = aggregate_applicants([r])
    assert counts["바화학"] == 1 and counts["사대학교"] == 1


def test_patent_without_number_is_not_deduped_away():
    """출원번호가 비어 있어도 집계에서 사라지면 안 된다."""
    r = result("키워드", 100, [("", ["아소재"]), ("", ["아소재"])])
    counts, _ = aggregate_applicants([r])
    assert counts["아소재"] == 2


def test_broad_threshold_separates_measured_cases():
    """실측값 기준: 4,635·2,440은 좁고 65,889·65,760은 넓다."""
    assert 4_635 < BROAD_THRESHOLD and 2_440 < BROAD_THRESHOLD
    assert 65_889 > BROAD_THRESHOLD and 65_760 > BROAD_THRESHOLD
