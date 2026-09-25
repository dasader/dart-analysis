"""기술 종합 보고서의 프롬프트 조립 검증 — 외부 호출 없이 순수 로직만.

핵심은 "무엇이 프롬프트에 들어가는가"다. 특허 초록이 주근거이고 사업보고서는
보조인데, 관심 기업 특허가 대학·외국기업 초록에 밀려 잘리면 보고서가 정작
"어느 기업이 하는가"에 답하지 못한다.
"""
import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import AnalysisStatus
from app.migrate import run as run_migrations
from app.models import Analysis, Company, Report, TechCompany, Technology
from app.services import tech_report


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
    run_migrations(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def tech(db):
    t = Technology(name="전고체 배터리", description="설명",
                   keywords=json.dumps(["황화물계 고체전해질"], ensure_ascii=False))
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def patent(applicant, *, app_no, abstract="초록 본문", title="제목", status="등록"):
    return {"applicants": [applicant], "title": title, "app_no": app_no,
            "app_date": "20250101", "ipc": "H01M", "status": status,
            "abstract": abstract}


def test_report_columns_exist(db, tech):
    """migrate가 report_md·report_generated_at을 만들어야 한다."""
    tech.report_md = "## 보고서"
    tech.report_generated_at = datetime(2026, 8, 15)
    db.commit()
    db.refresh(tech)
    assert tech.report_md == "## 보고서"


def test_interesting_companies_come_first(db, tech):
    """관심 기업 특허가 상한에 밀려 잘리면 안 된다 — 우선순위로 앞세운다."""
    others = [patent(f"OO대학교 산학협력단 {i}", app_no=f"X{i}")
              for i in range(tech_report.MAX_PATENTS)]
    mine = [patent("삼성전자주식회사", app_no="M1", title="전고체 전해질")]
    used = tech_report.select_patents(
        [{"word": "k", "total": 100, "items": others + mine}],
        names={"삼성전자주식회사"})

    assert used[0]["applicants"] == ["삼성전자주식회사"]
    assert len(used) == tech_report.MAX_PATENTS


def test_duplicate_patents_are_folded(db, tech):
    """같은 특허가 여러 키워드에 걸려도 초록을 두 번 넣지 않는다."""
    p = patent("가전자", app_no="A1")
    used = tech_report.select_patents(
        [{"word": "k1", "total": 1, "items": [p]},
         {"word": "k2", "total": 1, "items": [p]}], names=set())
    assert len(used) == 1


def test_patents_without_abstract_are_skipped(db, tech):
    used = tech_report.select_patents(
        [{"word": "k", "total": 1, "items": [patent("가전자", app_no="A1", abstract="")]}],
        names=set())
    assert used == []
    assert "초록이 있는 특허가 없습니다" in tech_report._patent_section(used)


def test_company_section_uses_latest_year_only(db, tech):
    """연도가 섞이면 프롬프트가 부풀고 옛 수치가 섞인다 — 최신 1개 연도만 쓴다."""
    co = Company(corp_code="00000001", corp_name="가전자")
    db.add(co)
    db.commit()
    db.add(TechCompany(technology_id=tech.id, company_id=co.id, corp_name="가전자",
                       applicant_name="가전자", patent_count=5, status="tracked",
                       keyword_hits="[]"))
    for year, text in ((2024, "옛날 R&D"), (2025, "최신 R&D")):
        r = Report(company_id=co.id, rcept_no=f"R{year}", report_name="사업보고서",
                   report_type="annual", fiscal_year=year)
        db.add(r)
        db.commit()
        db.add(Analysis(company_id=co.id, report_id=r.id, analysis_type="rnd",
                        status=AnalysisStatus.COMPLETED, result_summary=text))
    db.commit()
    db.refresh(tech)

    section, years = tech_report._company_section(db, tech)
    assert "최신 R&D" in section and "옛날 R&D" not in section
    assert "2025년 사업보고서 기준" in section
    assert years == {2025}          # 화면·머리말에 기준 연도를 밝히는 데 쓴다


def test_company_without_analysis_is_stated_not_dropped(db, tech):
    """분석이 없는 기업을 조용히 빼면 특허가 많은데 왜 안 보이는지 알 수 없다."""
    co = Company(corp_code="00000002", corp_name="나소재")
    db.add(co)
    db.commit()
    db.add(TechCompany(technology_id=tech.id, company_id=co.id, corp_name="나소재",
                       applicant_name="나소재", patent_count=9, status="tracked",
                       keyword_hits="[]"))
    db.commit()
    db.refresh(tech)

    section, years = tech_report._company_section(db, tech)
    assert "미수집" in section
    assert years == set()


def test_tech_terms_drops_short_tokens(db, tech):
    """2글자 이하는 아무 데나 걸려 오탐만 만든다."""
    assert "전고체" in tech_report.tech_terms(tech)
    assert "고체전해질" in tech_report.tech_terms(tech)
    assert all(len(t) >= 3 for t in tech_report.tech_terms(tech))


def test_mention_sentences_picks_only_matching(db, tech):
    """단계 판정을 모델에 맡기면 같은 산업이라는 이유로 올려잡는다(실측: 전고체
    배터리인데 'FCEV 수소공급시스템용 SUS 소재' 과제를 근거로 삼았다)."""
    text = ("FCEV 수소공급시스템용 SUS 소재 개발 과제를 수행했습니다.\n"
            "차세대 전지 개발 - 전고체전지, 바이폴라전지 개발")
    hits = tech_report.mention_sentences(text, tech_report.tech_terms(tech))
    assert len(hits) == 1
    assert "전고체전지" in hits[0]
    assert "FCEV" not in hits[0]


def test_mention_sentences_empty_when_absent(db, tech):
    text = "메모리 반도체와 디스플레이 사업을 영위하고 있습니다."
    assert tech_report.mention_sentences(text, tech_report.tech_terms(tech)) == []


def test_company_section_flags_absence_explicitly(db, tech):
    """언급이 없으면 '없다'고 코드가 못박아야 모델이 다른 과제를 끌어오지 않는다."""
    co = Company(corp_code="00000011", corp_name="가완성차")
    db.add(co)
    db.commit()
    r = Report(company_id=co.id, rcept_no="R11", report_name="사업보고서",
               report_type="annual", fiscal_year=2025)
    db.add(r)
    db.commit()
    db.add(Analysis(company_id=co.id, report_id=r.id, analysis_type="rnd",
                    status=AnalysisStatus.COMPLETED,
                    result_summary="FCEV 수소공급시스템용 SUS 소재 개발"))
    db.add(TechCompany(technology_id=tech.id, company_id=co.id, applicant_name="가완성차",
                       corp_name="가완성차", patent_count=20, status="tracked",
                       keyword_hits="[]"))
    db.commit()
    db.refresh(tech)

    section, _ = tech_report._company_section(db, tech)
    assert "이 기술은 사업보고서에 언급되지 않았습니다" in section
    assert "이 기술이 직접 언급된 대목" not in section


def test_patent_stats_splits_registered_and_pending():
    """등록은 권리 확보, 공개는 심사 중 — 합쳐 세면 의미가 사라진다."""
    items = [
        {**patent("가전자", app_no="A1"), "status": "등록"},
        {**patent("가전자", app_no="A2"), "status": "공개"},
        {**patent("가전자", app_no="A3"), "status": "거절"},
        {**patent("나소재", app_no="B1"), "status": "등록"},
    ]
    stats = tech_report.patent_stats([{"word": "k", "total": 4, "items": items}])
    assert stats["가전자"] == {"total": 3, "registered": 1, "pending": 1}
    assert stats["나소재"]["registered"] == 1


def test_patent_stats_folds_duplicates_across_keywords():
    p = {**patent("가전자", app_no="A1"), "status": "등록"}
    stats = tech_report.patent_stats([{"word": "k1", "total": 1, "items": [p]},
                                      {"word": "k2", "total": 1, "items": [p]}])
    assert stats["가전자"]["total"] == 1


def test_span_measures_only_patents_actually_used():
    """수집 전체로 재면 상위 N에 들지도 못한 옛 특허 1건이 범위를 30년으로 늘린다.

    실측: 수집 321건의 최소 출원일은 1994년이었지만 실제로 보고서에 실린 40건은
    2014~2025였고 그중 95%가 2016년 이후였다. '1994~2026'은 30년치를 종합한 것처럼
    읽혀 오해를 낳는다.
    """
    # 관심 기업 특허로 상한을 채우면 비관심 기업의 옛 특허는 잘려 나간다
    recent = [{**patent("가전자", app_no=f"N{i}"), "app_date": "20240101"}
              for i in range(tech_report.MAX_PATENTS)]
    old = {**patent("어느대학", app_no="OLD"), "app_date": "19941201"}
    results = [{"word": "k", "total": len(recent) + 1, "items": recent + [old]}]

    used = tech_report.select_patents(results, names={"가전자"})
    assert tech_report.date_span(used) == ("20240101", "20240101")
    assert all(it["app_no"] != "OLD" for it in used)
    # 수집 전체에는 여전히 1994년이 들어 있다 — 그걸로 재면 안 된다는 뜻
    assert any(it["app_date"] == "19941201" for it in results[0]["items"])


def test_select_patents_respects_max():
    many = [patent(f"기타{i}", app_no=f"X{i}") for i in range(tech_report.MAX_PATENTS + 10)]
    used = tech_report.select_patents([{"word": "k", "total": 1, "items": many}],
                                      names=set(), this_year=2025)
    assert len(used) == tech_report.MAX_PATENTS


def test_old_patents_are_filtered_out():
    """상한을 늘리면 뒤쪽(오래된 것)이 딸려 들어온다 — 연령으로 거른다."""
    fresh = {**patent("가전자", app_no="NEW"), "app_date": "20200101"}
    old = {**patent("가전자", app_no="OLD"), "app_date": "20100101"}
    used = tech_report.select_patents([{"word": "k", "total": 2, "items": [old, fresh]}],
                                      names=set(), this_year=2026)
    assert [it["app_no"] for it in used] == ["NEW"]


def test_undated_patents_are_kept():
    """출원일을 모르면 걸러야 할 근거가 없다 — 버리지 않는다."""
    undated = {**patent("가전자", app_no="U1"), "app_date": ""}
    used = tech_report.select_patents([{"word": "k", "total": 1, "items": [undated]}],
                                      names=set(), this_year=2026)
    assert len(used) == 1


def test_age_cut_is_released_when_nothing_recent():
    """오래된 것뿐인 분야에서 컷 때문에 빈손이 되는 건 더 나쁘다."""
    old = {**patent("가전자", app_no="OLD"), "app_date": "20000101"}
    used = tech_report.select_patents([{"word": "k", "total": 1, "items": [old]}],
                                      names=set(), this_year=2026)
    assert [it["app_no"] for it in used] == ["OLD"]


def test_age_cut_keeps_interest_priority():
    """연령 컷을 넣어도 관심 기업 우선은 유지돼야 한다."""
    others = [{**patent(f"대학{i}", app_no=f"X{i}"), "app_date": "20240101"}
              for i in range(tech_report.MAX_PATENTS)]
    mine = {**patent("삼성전자주식회사", app_no="M1"), "app_date": "20230101"}
    used = tech_report.select_patents([{"word": "k", "total": 1, "items": others + [mine]}],
                                      names={"삼성전자주식회사"}, this_year=2026)
    assert used[0]["app_no"] == "M1"


def test_year_histogram_lists_distribution():
    items = [{**patent("가", app_no="A1"), "app_date": "20240101"},
             {**patent("가", app_no="A2"), "app_date": "20240201"},
             {**patent("가", app_no="A3"), "app_date": "20230101"}]
    assert tech_report.year_histogram(items) == "2024년 2건, 2023년 1건"


def test_basis_line_formats_span():
    assert (tech_report.basis_line(("20140728", "20251021"), {2025})
            == "특허 출원일 2014.07~2025.10 / 2025년 사업보고서")


def test_basis_line_shows_year_range_when_companies_differ():
    """기업마다 최신 연도가 다를 수 있다 — 하나로 뭉뚱그리면 근거를 오독한다."""
    line = tech_report.basis_line(("20200101", "20250101"), {2024, 2025})
    assert "2024~2025년 사업보고서(기업별 최신)" in line
    assert "미수집" in tech_report.basis_line(None, set())


def test_prompt_states_basis_range(db, tech):
    prompt = tech_report.build_prompt(tech, [], "회사", "표", set(),
                                      ("20140728", "20251021"), {2025})
    assert "특허 출원일 2014.07~2025.10 / 2025년 사업보고서" in prompt
    # 초록 재료는 연령 컷을 받지만 기업 집계는 안 받는다 — 범위가 다름을 밝혀야 한다
    assert f"최근 {tech_report.MAX_PATENT_AGE_YEARS}년 이내 출원분" in prompt
    assert "기업 목록과 특허 건수는 기간 제한 없이 집계" in prompt


def test_prompt_marks_broad_keywords(db, tech):
    """넓은 키워드는 버리지 않고 드러낸다 — 모델이 가중치를 스스로 판단하게."""
    results = [{"word": "리튬 이차전지", "total": 60000, "items": []},
               {"word": "황화물계 고체전해질", "total": 318, "items": []}]
    prompt = tech_report.build_prompt(tech, results, "회사", "기타", set())
    broad_line = next(l for l in prompt.split("\n") if "리튬 이차전지" in l)
    narrow_line = next(l for l in prompt.split("\n") if "황화물계" in l and "총" in l)
    assert "넓은 키워드" in broad_line
    assert "넓은 키워드" not in narrow_line


def test_applicant_table_gives_exact_counts(db, tech):
    """건수를 표로 주지 않으면 모델이 초록을 훑어 '다수'라고 뭉갠다(실측)."""
    db.add(TechCompany(technology_id=tech.id, applicant_name="주식회사 엘지화학",
                       corp_name="LG화학", patent_count=16, status="tracked",
                       keyword_hits=json.dumps(["k1", "k2"])))
    db.add(TechCompany(technology_id=tech.id, applicant_name="한양대학교 산학협력단",
                       patent_count=12, status="excluded", keyword_hits="[]",
                       exclude_reason="법인번호 없음(개인·대학·연구소·외국)"))
    db.commit()
    db.refresh(tech)

    stats = {"주식회사 엘지화학": {"total": 16, "registered": 9, "pending": 5}}
    table = tech_report._applicant_table(db, tech, stats)
    # 등록과 공개를 갈라 준다 — 합계만 주면 "특허 16건 보유"로 뭉뚱그려진다
    assert "| 주식회사 엘지화학 | LG화학 | 16 | 9 | 5 | 2 | 추적 중 | 미수집 |" in table
    assert "|---|---|---|---|---|---|---|---|" in table   # 구분선 없으면 표로 안 읽힌다
    assert "법인번호 없음" in table


def test_unanalyzed_company_is_not_called_no_mention(db, tech):
    """'분석했는데 언급 없음'과 '분석 안 함'은 완전히 다른 정보다.

    실측: LG에너지솔루션(전고체 특허 16건)이 보고서 미수집인데 표에 "사업보고서에
    언급 없음"으로 나와, 전업 배터리 회사가 그 기술을 안 하는 것처럼 읽혔다.
    """
    co = Company(corp_code="00000004", corp_name="엘지에너지솔루션")
    db.add(co)
    db.commit()
    db.add(TechCompany(technology_id=tech.id, company_id=co.id,
                       applicant_name="주식회사 엘지에너지솔루션",
                       corp_name="엘지에너지솔루션", patent_count=16,
                       status="tracked", keyword_hits=json.dumps(["k1"])))
    db.commit()
    db.refresh(tech)

    assert "| 추적 중 | 미수집 |" in tech_report._applicant_table(db, tech)
    section, _ = tech_report._company_section(db, tech)
    assert "미수집" in section
    assert "하지 않는다는 뜻이 아닙니다" in section


def test_analyzed_company_gets_report_link(db, tech):
    co = Company(corp_code="00000005", corp_name="가전자")
    db.add(co)
    db.commit()
    r = Report(company_id=co.id, rcept_no="R1", report_name="사업보고서",
               report_type="annual", fiscal_year=2025)
    db.add(r)
    db.commit()
    db.add(Analysis(company_id=co.id, report_id=r.id, analysis_type="rnd",
                    status=AnalysisStatus.COMPLETED, result_summary="내용"))
    db.add(TechCompany(technology_id=tech.id, company_id=co.id, applicant_name="가전자",
                       corp_name="가전자", patent_count=3, status="tracked",
                       keyword_hits="[]"))
    db.commit()
    db.refresh(tech)

    # 링크가 있어야 보고서에서 개별 기업 분석으로 넘어갈 수 있다
    assert (f"[2025년 사업보고서](/companies/{co.id}/reports/{r.id})"
            in tech_report._applicant_table(db, tech))


def test_tracked_without_report_is_onboarded(db, tech):
    """등록만 되고 보고서가 없는 기업이 온보딩에서 빠지면 영영 분석되지 않는다."""
    from app.services import tech_scan

    have = Company(corp_code="00000006", corp_name="가전자")
    none_yet = Company(corp_code="00000007", corp_name="나소재")
    db.add_all([have, none_yet])
    db.commit()
    db.add(Report(company_id=have.id, rcept_no="R9", report_name="사업보고서",
                  report_type="annual", fiscal_year=2025, file_path="/tmp/x.zip"))
    db.commit()

    tracked = [{"applicant": "가전자", "patents": 5, "company_id": have.id},
               {"applicant": "나소재", "patents": 3, "company_id": none_yet.id}]
    picked = tech_scan._tracked_without_report(db, tracked)
    assert [x["applicant"] for x in picked] == ["나소재"]


@pytest.mark.parametrize("limit,expected", [(0, 8), (3, 3), (99, 8)])
def test_onboard_limit_zero_means_all(db, limit, expected):
    """분석 상한 0 = 전체. 후보를 다 태우겠다는 선택을 표현할 방법이 필요하다.

    DartCorp에 없는 후보를 주면 전부 '색인 조회 실패'로 떨어지므로,
    failed 개수로 실제 몇 건을 집어 들었는지 잴 수 있다(외부 호출 없이).
    """
    import asyncio

    from app.services import tech_pipeline

    cands = [{"applicant": f"기업{i}", "corp_code": f"{i:08d}", "patents": 10 - i}
             for i in range(8)]
    out = asyncio.run(tech_pipeline.onboard(db, cands, limit))
    assert len(out["failed"]) == expected
    assert out["registered"] == []


def test_match_companies_has_no_default_limit():
    """예전 기본값 30이 후보를 조용히 잘라 '전체'를 골라도 31번째부터 안 보였다.

    이 함수는 DB 조회만 하므로(외부 API를 부르지 않는다) 상한을 둘 이유가 없다.
    """
    import inspect

    from app.services import patent_search

    assert inspect.signature(patent_search.match_companies).parameters["limit"].default is None


def test_onboard_targets_are_ordered_by_patent_count(db):
    """onboard는 앞에서부터 자르므로 순서가 곧 우선순위다.

    실측: available을 그냥 앞에 이어붙였더니 특허 3건짜리 미등록 기업이
    16건짜리 기존 기업보다 먼저 갔다.
    """
    from app.services import tech_scan

    lg = Company(corp_code="00000008", corp_name="엘지에너지솔루션")
    posco = Company(corp_code="00000009", corp_name="포스코홀딩스")
    db.add_all([lg, posco])
    db.commit()

    matched = {
        "available": [{"applicant": "에코프로비엠", "patents": 3},
                      {"applicant": "기아", "patents": 14}],
        "tracked": [{"applicant": "엘지에너지솔루션", "patents": 16, "company_id": lg.id},
                    {"applicant": "포스코홀딩스", "patents": 8, "company_id": posco.id}],
        "excluded": [],
    }
    picked = tech_scan._onboard_targets(db, matched)
    assert [x["applicant"] for x in picked[:3]] == ["엘지에너지솔루션", "기아", "포스코홀딩스"]


def test_onboard_order_prefers_recent_patents():
    """누적 건수가 많아도 옛 특허뿐이면 뒤로 간다(실측: 연료전지에서 사업을 접은 기업들)."""
    from app.services import tech_pipeline

    cands = [{"applicant": "옛강자", "patents": 36, "recent": 0},
             {"applicant": "현역", "patents": 7, "recent": 7}]
    assert [x["applicant"] for x in tech_pipeline.rank(cands)] == ["현역", "옛강자"]


def test_onboard_order_puts_unrelated_last_but_keeps_it():
    """낱말만 겹친 기업(실측: 레독스 흐름전지 HLB제약)은 맨 뒤로 — 버리지는 않는다."""
    from app.services import tech_pipeline

    cands = [{"applicant": "흐름전지", "patents": 7, "recent": 7, "role": "unrelated"},
             {"applicant": "장비", "patents": 5, "recent": 5, "role": "peripheral"},
             {"applicant": "소재", "patents": 3, "recent": 3, "role": "core"}]
    assert [x["applicant"] for x in tech_pipeline.rank(cands)] == ["소재", "장비", "흐름전지"]


@pytest.mark.parametrize("cap", [0, 3])
def test_fit_judge_skipped_when_everyone_fits(monkeypatch, cap):
    """상한이 0(전체)이거나 후보가 상한 이하면 순서가 무의미하다 — LLM을 부르지 않는다."""
    import asyncio

    from app.services import tech_pipeline

    def boom(*a):
        raise AssertionError("호출되면 안 된다")
    monkeypatch.setattr(tech_pipeline, "_judge_sync", boom)
    cands = [{"applicant": f"기업{i}", "corp_name": f"기업{i}", "patents": i} for i in range(3)]
    out = asyncio.run(tech_pipeline.order_candidates("기술", "설명", cands, {}, cap))
    assert [x["applicant"] for x in out] == ["기업2", "기업1", "기업0"]


def test_fit_judge_failure_falls_back_to_recent_order(monkeypatch):
    """판정이 실패해도 온보딩을 막지 않는다."""
    import asyncio

    from app.services import tech_pipeline

    def fail(*a):
        raise RuntimeError("API 오류")
    monkeypatch.setattr(tech_pipeline, "_judge_sync", fail)
    cands = [{"applicant": "옛", "corp_name": "옛", "patents": 9, "recent": 0},
             {"applicant": "새", "corp_name": "새", "patents": 2, "recent": 2}]
    out = asyncio.run(tech_pipeline.order_candidates("기술", "설명", cands, {}, 1))
    assert [x["applicant"] for x in out] == ["새", "옛"]


def test_fit_judge_reorders_by_role(monkeypatch):
    """판정은 corp_name으로 돌아온다 — 출원인명과 달라도 붙어야 한다."""
    import asyncio

    from app.services import tech_pipeline

    monkeypatch.setattr(tech_pipeline, "_judge_sync", lambda *a: {
        "HLB제약": {"corp": "HLB제약", "role": "unrelated", "reason": "흐름전지"},
        "솔브레인": {"corp": "솔브레인", "role": "core", "reason": "고체전해질"}})
    cands = [{"applicant": "에이치엘비제약", "corp_name": "HLB제약", "patents": 7, "recent": 7},
             {"applicant": "솔브레인 주식회사", "corp_name": "솔브레인", "patents": 3, "recent": 3}]
    out = asyncio.run(tech_pipeline.order_candidates("전고체", "설명", cands, {}, 1))
    assert [x["corp_name"] for x in out] == ["솔브레인", "HLB제약"]
    assert out[0]["reason"] == "고체전해질"


def test_promote_fills_company_id(db, tech):
    """status만 tracked로 바꾸고 company_id를 빠뜨리면 겉보기엔 멀쩡한데
    기업 상세 링크도, 사업보고서 근거도 조용히 사라진다."""
    from app.services import tech_scan

    co = Company(corp_code="00000003", corp_name="다전자")
    db.add(co)
    db.commit()
    db.add(TechCompany(technology_id=tech.id, applicant_name="다전자주식회사",
                       corp_name="다전자", patent_count=7, status="available",
                       keyword_hits="[]"))
    db.commit()

    tech_scan._promote(db, tech, {"registered": [{"company_id": co.id, "corp_name": "다전자"}]})

    tc = db.query(TechCompany).filter(TechCompany.applicant_name == "다전자주식회사").one()
    assert tc.status == "tracked"
    assert tc.company_id == co.id
