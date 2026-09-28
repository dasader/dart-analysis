"""구역 추출기 검증 — 특히 '실패를 실패로 판정하는지'.

조용히 원문을 흘려보내면 서식이 바뀐 걸 아무도 모른 채 비용만 나간다.
"""
import pytest

from app.services.section_extract import ExtractionFailed, extract, find_sections

FILLER = "임원 및 직원 등의 현황 상세 내역과 주식소유현황 표. " * 400  # 약 1만 자


def build_report(*, with_toc: bool = True, body_scale: int = 6) -> str:
    """실제 사업보고서 구조를 축약 재현 — 목차 + 본문 12구역 + 감사보고서."""
    titles = [
        ("I", "회사의 개요"), ("II", "사업의 내용"), ("III", "재무에 관한 사항"),
        ("IV", "이사의 경영진단 및 분석의견"), ("V", "회계감사인의 감사의견 등"),
        ("VI", "이사회 등 회사의 기관에 관한 사항"), ("VII", "주주에 관한 사항"),
        ("VIII", "임원 및 직원 등에 관한 사항"), ("IX", "계열회사 등에 관한 사항"),
        ("X", "대주주 등과의 거래내용"), ("XI", "그 밖에 투자자 보호를 위하여 필요한 사항"),
        ("XII", "상세표"),
    ]
    parts = []
    if with_toc:  # 목차 — 12개 제목이 좁은 범위에 몰려 있다
        parts.append(" ".join(f"{r}. {t}" for r, t in titles))
    for r, t in titles:
        parts.append(f"\n{r}. {t}\n" + FILLER * body_scale)
    parts.append("【 전문가의 확인 】 독립된 감사인의 감사보고서 " + FILLER * 20)
    return "".join(parts)


def test_keeps_only_needed_sections():
    text = build_report()
    out = extract(text)
    # 남긴 구역
    assert "I. 회사의 개요" in out
    assert "II. 사업의 내용" in out
    assert "XII. 상세표" in out
    # 버린 구역
    assert "III. 재무에 관한 사항" not in out
    assert "VIII. 임원 및 직원" not in out
    assert len(out) < len(text) * 0.5


def test_drops_audit_report_after_last_section():
    """XII 뒤의 감사보고서·재무제표가 딸려오면 절감 효과가 사라진다."""
    assert "독립된 감사인의 감사보고서" not in extract(build_report())


def test_works_without_table_of_contents():
    """목차가 없는 보고서도 같은 규칙으로 처리된다."""
    out = extract(build_report(with_toc=False))
    assert "II. 사업의 내용" in out and "III. 재무에 관한 사항" not in out


def test_picks_body_not_table_of_contents():
    """목차는 12개가 수천 자 안에 몰려 있어 본문 체인에 밀려야 한다."""
    text = build_report()
    sections = find_sections(text)
    span = sections[-1][0] - sections[0][0]
    assert span > 100_000, "목차를 본문으로 오인했다"


def test_fails_when_required_section_missing():
    """서식이 바뀌어 필수 구역이 사라지면 예외 — LLM에 보내지 않는다."""
    text = build_report().replace("II. 사업의 내용", "2장 사업현황")
    with pytest.raises(ExtractionFailed, match="사업의 내용"):
        extract(text)


def test_fails_when_nothing_was_trimmed():
    """구역 경계를 잘못 잡아 거의 줄지 않으면 통과시키지 않는다."""
    # 남기는 구역(I·II·XII) 사이에 버릴 구역이 없으면 전량이 남는다
    text = ("I. 회사의 개요\n" + FILLER * 6
            + "II. 사업의 내용\n" + FILLER * 6
            + "XII. 상세표\n" + FILLER * 6)
    with pytest.raises(ExtractionFailed, match="거의 줄지 않았"):
        extract(text)


def test_fails_when_result_too_short():
    """본문을 놓쳐 껍데기만 남는 경우도 실패로 본다(II 길이로 잰다)."""
    text = ("I. 회사의 개요\n짧음\n"
            + "III. 재무에 관한 사항\n" + FILLER * 20
            + "II. 사업의 내용\n짧음\n")
    with pytest.raises(ExtractionFailed):
        extract(text)


def test_cross_reference_is_not_a_heading():
    """본문 안의 상호참조를 대제목으로 오인하면 앞 구역이 거기서 끊긴다.

    실측: 알앤엘재생의학연구소 II(사업의 내용) 본문에
    "III.재무에 관한 사항'을 참고하시기 바랍니다"가 있어 II가 740자로 잘렸고,
    진짜 본문 70,434자가 통째로 버려져 추출이 실패했다.
    """
    text = build_report()
    poisoned = text.replace(
        "II. 사업의 내용\n",
        "II. 사업의 내용\n자세한 내용은 'III. 재무에 관한 사항'을 참고하시기 바랍니다.\n",
        1)

    positions = {r: p for p, r in find_sections(poisoned)}
    # 상호참조(II 본문 안)가 아니라 진짜 III 대제목이 잡혀야 한다
    assert positions["III"] - positions["II"] > 50_000
    assert FILLER * 6 in extract(poisoned)  # II 본문이 통째로 남는다


def test_quoted_heading_both_sides_is_ignored():
    """여는 따옴표만 있는 경우(‘II. 사업의 내용)도 상호참조로 본다."""
    text = build_report()
    poisoned = text.replace("I. 회사의 개요\n",
                            "I. 회사의 개요\n앞서 ‘II. 사업의 내용 참조\n", 1)
    positions = {r: p for p, r in find_sections(poisoned)}
    assert positions["II"] - positions["I"] > 50_000


def test_short_report_passes_when_business_section_is_intact():
    """상보형: I·II가 멀쩡한데 짧은 보고서(I+II 1.7만 자)는 통과해야 한다.

    예전 합계 20,000자 검사는 이걸 떨어뜨렸다.
    """
    short = "임원 현황. " * 100  # 버릴 구역 — 비율 검사를 넘길 만큼
    text = ("I. 회사의 개요\n" + "회사 연혁과 종속회사. " * 500
            + "II. 사업의 내용\n" + "연구개발 과제와 제품. " * 900
            + "III. 재무에 관한 사항\n" + FILLER * 3
            + "VIII. 임원 및 직원\n" + short)
    out = extract(text)
    assert len(out) < 20_000
    assert "II. 사업의 내용" in out


def test_truncated_business_section_fails_even_with_iv_xi():
    """알앤엘형: II가 740자로 잘리면 IV·XI가 합계를 채워도 실패다."""
    text = build_report().replace(
        "II. 사업의 내용\n" + FILLER * 6, "II. 사업의 내용\n" + "짧은 본문. " * 100, 1)
    text = text.replace(
        "XI. 그 밖에 투자자 보호를 위하여 필요한 사항\n",
        "XI. 그 밖에 투자자 보호를 위하여 필요한 사항\n1. 공시내용 진행 및 변경사항\n"
        + FILLER * 2 + "2. 우발부채 등에 관한 사항\n소송 ", 1)
    with pytest.raises(ExtractionFailed, match="사업의 내용"):
        extract(text)


def _report_with_xi(sub1: str, sub2: str, sub3: str, sub4: str) -> str:
    return build_report().replace(
        "XI. 그 밖에 투자자 보호를 위하여 필요한 사항\n" + FILLER * 6,
        "XI. 그 밖에 투자자 보호를 위하여 필요한 사항\n"
        + "1. 공시내용 진행 및 변경사항\n" + sub1
        + "2. 우발부채 등에 관한 사항\n" + sub2
        + "3. 제재 등과 관련된 사항\n" + sub3
        + "4. 작성기준일 이후 발생한 주요사항 등 기타사항\n" + sub4, 1)


def test_xi_keeps_only_disclosure_and_other_subsections():
    """XI는 소절 1(수주 공시)·4(신기술 지정)만 — 2(소송)·3(제재)은 노이즈다."""
    out = extract(_report_with_xi(
        "방위사업청 체계개발 계약. ", "중요한 소송사건 손해배상. ", "과징금 제재. ",
        "건설신기술 지정 제1000호. "))
    assert "체계개발" in out and "건설신기술" in out
    assert "소송사건" not in out and "과징금" not in out


def test_xi_subsection_4_tail_survives():
    """현대건설: 건설신기술 14건이 소절 4의 뒤쪽(XI 51k자 이후)에 있다.

    XI 앞 N자로 자르면 0건이 되던 것 — 소절 1·2가 길어도 소절 4의 뒤쪽이 남아야 한다.
    """
    out = extract(_report_with_xi(
        "수주 계약. " * 3_000, "소송. " * 5_000, "제재. " * 800,
        "인증 현황. " * 700 + "건설신기술 제999호"))
    assert "건설신기술 제999호" in out
    xi = out[out.index("XI. 그 밖에"):]
    assert "[...이하 생략...]" in xi  # 소절 1(21,000자)은 상한에서 잘렸다


def test_iv_is_capped():
    """IV는 앞 15,000자만 — POSCO홀딩스는 98,512자다."""
    text = build_report().replace(
        "IV. 이사의 경영진단 및 분석의견\n",
        "IV. 이사의 경영진단 및 분석의견\nGlass 기판 개발. ", 1)
    out = extract(text)
    assert "Glass 기판" in out
    iv = out[out.index("IV. 이사의 경영진단"):]
    assert iv.index("[...이하 생략...]") <= 15_001  # 상한 + 줄바꿈
