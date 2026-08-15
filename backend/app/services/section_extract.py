#!/usr/bin/env python3
"""사업보고서에서 3종 분석에 필요한 구역만 남긴다.

DART 사업보고서는 기업공시서식 작성기준에 따라 대제목이 표준화돼 있다.
분석에 쓰이는 건 I(종속회사 현황) · II(사업의 내용·연구개발) · XII(상세표)뿐이고,
나머지(재무제표·임원 명단·주주 현황)는 이 분석엔 잡음이다.

로마숫자만으로 제목을 찾으면 재무제표 안의 하위 항목("I. 매출액", "II. 비유동자산")을
대제목으로 오인한다 — 제목 문구까지 함께 맞춘다.

**추출에 실패하면 예외를 던진다.** 조용히 원문을 흘려보내면 형식이 바뀐 걸
아무도 모른 채 비용만 나가므로, 실패를 드러내 소스를 고치게 한다.
"""
import re


# 표준 대제목 — (로마숫자, 제목 앞부분). 회사마다 뒷부분 표현이 조금씩 다르다.
SECTIONS = [
    ("I", "회사의 개요"),
    ("II", "사업의 내용"),
    ("III", "재무에 관한 사항"),
    ("IV", "이사의 경영진단"),
    ("V", "회계감사인의 감사의견"),
    ("VI", "이사회 등 회사의 기관"),
    ("VII", "주주에 관한 사항"),
    ("VIII", "임원 및 직원"),
    ("IX", "계열회사 등에 관한 사항"),
    ("X", "대주주 등과의 거래내용"),
    ("XI", "그 밖에 투자자 보호"),
    ("XII", "상세표"),
]

# 남길 구역
KEEP = {"I", "II", "XII"}

# 목차가 본문 앞에 한 벌 있다 — 항목들이 좁은 범위에 몰려 있으므로 간격으로 거른다
# 마지막 구역(XII. 상세표) 뒤에는 감사보고서·재무제표가 이어진다.
# 본문의 끝을 알리는 표지 — 실측상 모든 보고서에서 이 순서로 나타난다.
_BODY_END = re.compile(r"【\s*전문가의 확인\s*】|독립된 감사인의 감사보고서")

# 상호참조를 감싸는 따옴표. 진짜 대제목 뒤에는 하위 항목("1. …")이 오지 따옴표가 오지 않는다
_QUOTES_CLOSE = frozenset("'\"’”」』")
_QUOTES_OPEN = frozenset("'\"‘“「『")


class ExtractionFailed(Exception):
    """보고서 형식이 예상과 달라 구역을 신뢰할 수 없다."""


def _is_cross_reference(text: str, start: int, end: int) -> bool:
    """본문 안에서 다른 구역을 가리키는 문장인가.

    "II.사업의 내용'을 참조하시기 바랍니다", "'III. 재무에 관한 사항'을 참고하시기"처럼
    **따옴표로 감싼 인용**이 상호참조의 표지다. 이것을 대제목으로 오인하면 앞 구역이
    거기서 끊긴다 — 실측에서 알앤엘재생의학연구소의 II(사업의 내용)가 740자로 잘려
    본문 70,434자가 통째로 버려졌다.
    """
    return (text[end:end + 1] in _QUOTES_CLOSE
            or text[max(0, start - 1):start] in _QUOTES_OPEN)


def find_sections(text: str) -> list[tuple[int, str]]:
    """본문 대제목 위치를 (위치, 로마숫자)로 반환.

    같은 제목이 목차와 본문에 여러 번 나오므로, 정규 순서(I→XII)로 이어지는
    체인 중 **가장 넓게 퍼진 것**을 본문으로 고른다. 목차는 12개 항목이 수천 자
    안에 몰려 있어 자연히 탈락한다. (목차가 없는 보고서도 같은 규칙으로 처리된다.)
    """
    occurrences: dict[str, list[int]] = {}
    for roman, title in SECTIONS:
        pattern = re.compile(rf"{roman}\.\s*{re.escape(title)}")
        found = [m.start() for m in pattern.finditer(text)
                 if not _is_cross_reference(text, m.start(), m.end())]
        if found:
            occurrences[roman] = found

    def chain_from(start: int) -> list[tuple[int, str]]:
        """start 이후로 정규 순서를 지키며 가장 이른 출현을 이어 붙인다."""
        out = [(start, SECTIONS[0][0])]
        cursor = start
        for roman, _ in SECTIONS[1:]:
            nxt = next((p for p in occurrences.get(roman, []) if p > cursor), None)
            if nxt is not None:
                out.append((nxt, roman))
                cursor = nxt
        return out

    best: list[tuple[int, str]] = []
    for start in occurrences.get(SECTIONS[0][0], []):
        candidate = chain_from(start)
        span = candidate[-1][0] - candidate[0][0]
        if span > (best[-1][0] - best[0][0] if best else -1):
            best = candidate
    return best


def extract(text: str) -> str:
    """분석에 필요한 구역만 이어붙인다.

    형식이 달라 신뢰할 수 없으면 ExtractionFailed를 던진다.
    """
    sections = find_sections(text)
    found = {r for _, r in sections}

    # I(종속회사)·II(사업의 내용)는 3종 분석의 근거라 없으면 진행할 수 없다
    missing = {"I", "II"} - found
    if missing:
        titles = [t for r, t in SECTIONS if r in missing]
        raise ExtractionFailed(
            f"보고서에서 필수 구역을 찾지 못했습니다: {', '.join(titles)}. "
            "보고서 서식이 바뀌었을 수 있습니다."
        )

    # 마지막 구역은 다음 대제목이 없으므로 본문 끝 표지로 자른다
    body_end = _BODY_END.search(text, sections[-1][0])
    tail = body_end.start() if body_end else len(text)

    kept = []
    for i, (pos, roman) in enumerate(sections):
        if roman not in KEEP:
            continue
        end = sections[i + 1][0] if i + 1 < len(sections) else tail
        kept.append(text[pos:end])

    result = "\n\n".join(kept)

    # 거의 줄지 않았다면 구역 경계를 잘못 잡은 것이다 — 통과시키면 절감 효과도 없다
    ratio = len(result) / len(text)
    if ratio > 0.7:
        raise ExtractionFailed(
            f"구역 추출 결과가 원문의 {ratio:.0%}로 거의 줄지 않았습니다. "
            "구역 경계를 잘못 잡았을 수 있습니다."
        )
    # 반대로 너무 적게 남아도 본문을 놓친 것이다
    if len(result) < 20_000:
        raise ExtractionFailed(
            f"구역 추출 결과가 {len(result):,}자로 지나치게 짧습니다. "
            "본문을 제대로 찾지 못했을 수 있습니다."
        )
    return result


