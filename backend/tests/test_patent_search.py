"""출원인 집계 검증 — API 호출 없이 순수 함수만."""
from app.services.patent_search import BROAD_THRESHOLD, aggregate_applicants


def result(word: str, total: int, patents: list[tuple[str, list[str]]]) -> dict:
    return {"word": word, "total": total,
            "items": [{"app_no": no, "applicants": apps} for no, apps in patents]}


def test_same_patent_counted_once_across_keywords():
    """같은 특허가 여러 키워드에 걸려도 한 번만 센다."""
    r1 = result("좁은키워드", 1000, [("10-1", ["가전자"]), ("10-2", ["나소재"])])
    r2 = result("다른키워드", 2000, [("10-1", ["가전자"]), ("10-3", ["가전자"])])

    counts, kws, _ = aggregate_applicants([r1, r2])
    assert counts["가전자"] == 2      # 10-1 중복 제외, 10-1 + 10-3
    assert counts["나소재"] == 1


def test_keyword_set_tracks_where_applicant_appeared():
    """넓은 키워드 하나에서만 나온 대기업과 여러 키워드에 걸친 곳을 갈라야 한다."""
    narrow = result("황화물계 고체전해질", 4_635,
                    [("10-1", ["다모빌리티"]), ("10-2", ["라연구원"])])
    broad = result("리튬 이차전지", 65_760,
                   [("10-3", ["다모빌리티"]), ("10-4", ["마배터리"])])

    counts, kws, _ = aggregate_applicants([narrow, broad])
    assert kws["다모빌리티"] == {"황화물계 고체전해질", "리튬 이차전지"}   # 두 키워드
    assert kws["마배터리"] == {"리튬 이차전지"}                        # 넓은 것에만
    assert kws["라연구원"] == {"황화물계 고체전해질"}


def test_joint_application_credits_every_applicant():
    """공동출원(| 구분)은 모든 출원인에게 센다."""
    r = result("키워드", 100, [("10-1", ["바화학", "사대학교"])])
    counts, kws, _ = aggregate_applicants([r])
    assert counts["바화학"] == 1 and counts["사대학교"] == 1


def test_patent_without_number_is_not_deduped_away():
    """출원번호가 비어 있어도 집계에서 사라지면 안 된다."""
    r = result("키워드", 100, [("", ["아소재"]), ("", ["아소재"])])
    counts, _, _ = aggregate_applicants([r])
    assert counts["아소재"] == 2


def test_broad_threshold_separates_measured_cases():
    """실측값 기준: 4,635·2,440은 좁고 65,889·65,760은 넓다."""
    assert 4_635 < BROAD_THRESHOLD and 2_440 < BROAD_THRESHOLD
    assert 65_889 > BROAD_THRESHOLD and 65_760 > BROAD_THRESHOLD


def test_recent_counts_only_last_ten_years():
    """사업을 접은 기업이 옛 특허로 올라오지 않게 최근 10년 출원만 센다.
    실측(수소 연료전지): 현대하이스코 36건은 전부 2006~2013년이다."""
    from app.services.patent_search import count_recent
    items = [{"app_date": "20080101"}, {"app_date": "20160101"}, {"app_date": "20240101"},
             {"app_date": ""}]   # 출원일을 모르면 거를 근거가 없다
    assert count_recent(items, this_year=2026) == 3

def test_ipc_core_marks_off_domain_patents():
    """풀의 다수 메인그룹은 코어, 한두 건 끼어든 분야는 코어 밖. IPC가 없으면 판단 보류(True)."""
    from app.services.patent_search import mark_ipc_core
    batt = [{"app_no": f"10-{i}", "ipc": "H01M 10/0562|C01B 25/14", "applicants": []}
            for i in range(8)]
    stray = {"app_no": "10-x", "ipc": "B64C 39/02|G06Q 50/08", "applicants": []}
    blank = {"app_no": "10-y", "ipc": "", "applicants": []}
    r1 = {"word": "좁은", "total": 8, "items": batt}
    r2 = {"word": "엉뚱", "total": 3, "items": [stray, blank, batt[0]]}

    core = mark_ipc_core([r1, r2])
    assert core == {"H01M 10", "C01B 25"}
    assert all(it["ipc_core"] for it in batt)
    assert stray["ipc_core"] is False
    assert blank["ipc_core"] is True


def test_core_only_drops_off_domain_but_keeps_total():
    from app.services.patent_search import core_only
    batt = [{"app_no": f"10-{i}", "ipc": "H01M 10/0562", "applicants": []} for i in range(10)]
    stray = {"app_no": "10-x", "ipc": "G06Q 50/08", "applicants": []}
    out = core_only([{"word": "w", "total": 999, "items": batt + [stray]}])
    assert out[0]["total"] == 999 and stray not in out[0]["items"] and len(out[0]["items"]) == 10
