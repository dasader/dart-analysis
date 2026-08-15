"""기술 종합 보고서 — 특허가 주재료, 사업보고서가 보조.

**왜 특허가 주재료인가.** 실측으로 갈렸다. 전고체 배터리 상위 출원인 3사의
사업보고서 원문에서 기술 키워드를 셌더니:

  삼성SDI    82,622자  '전고체' 2회
  삼성전자   210,033자  '전고체' 0회, '고체전해질' 0회, '이차전지' 0회
  현대자동차  139,184자  '전고체' 0회

특허로는 각각 17·22·20건을 낸 기업들이다. 사업보고서는 **지금 매출을 내는 사업**을
공시하고, 특허는 **출원 18개월 뒤 공개되는 미래 기술**이라 시점과 성격이 다르다.
그래서 사업보고서를 아무리 짜내도 그 기술 이야기는 나오지 않는다(길이를 늘리면
환각만 는다 — 국가전략기술 분석에서 이미 겪었다).

사업보고서는 기술 자체가 아니라 **"그 기업이 이 분야를 밀 체력이 되는가"**(R&D 투자
규모·국가전략기술 해당 여부)를 대는 보조 근거로만 쓴다.

보고서 1건은 LLM 호출 1회고 입력이 수만 자라 batch(8분)를 쓸 이유가 없다.
keyword_extract와 같은 실시간 경로를 쓴다.
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from functools import partial

from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import AnalysisStatus
from app.models import Analysis, Report, Technology
from app.services import patent_search, tech_scan
from app.services.report_service import extract_text_from_report

logger = logging.getLogger(__name__)

MODEL = "gemini-3.5-flash-lite"
MAX_OUTPUT_TOKENS = 16384

# 「기술 개요」를 쓸 초록 재료의 수. **기업 목록과는 무관하다** — 기업 발굴과
# 특허 건수 집계는 수집 전체(실측 321건)로 하고, 이 상한은 프롬프트에 실을 초록만 자른다
MAX_PATENTS = 80
ABSTRACT_CHARS = 500
MAX_ANALYSIS_CHARS = 3000

# 이보다 오래된 특허는 초록 재료에서 뺀다.
# 상한을 늘리면 뒤쪽(관련도가 낮고 오래된 것)이 딸려 들어오는데, 10년도 더 된 특허의
# 조성·공정을 현재 기술 개요에 섞으면 지금 무엇이 쟁점인지가 흐려진다.
# 실측(전고체 배터리): 상위 40건의 95%가 이미 최근 10년 안이라 이 컷으로 잃는 게 거의 없다.
MAX_PATENT_AGE_YEARS = 10

# 사업보고서 보조 근거로 쓸 분석. 종속회사 변동은 기술과 무관하므로 넣지 않는다
SUPPORT_TYPES = ("rnd", "national_tech")

SYSTEM = """당신은 기술 동향 분석가입니다. 특정 기술에 대해 "어떤 기업이 이 기술을
실제로 하고 있는가"를 밝히는 보고서를 씁니다.

**근거의 성격을 구분하십시오. 이것이 이 보고서의 핵심입니다.**
- **특허**는 그 기업이 이 기술을 실제로 개발하고 있다는 직접 증거입니다. 다만 출원 후
  18개월 뒤에 공개되므로 1~2년 전의 활동입니다
- **사업보고서**는 지금 매출을 내는 사업을 공시한 것입니다. 아직 양산 전인 기술은
  대개 실리지 않습니다. **사업보고서에 그 기술 언급이 없다는 것은 그 기업이 그 기술을
  안 한다는 뜻이 아닙니다** — 아직 사업화 단계가 아니라는 뜻입니다. 이 점을 혼동하지 마십시오

규칙:
- **주어진 자료에 없는 것은 쓰지 마십시오.** 기재가 없으면 "자료에 없음"이라고 쓰고
  추측하지 마십시오. 매출 전망·시장 규모·경쟁 순위처럼 자료에 없는 수치를 지어내지 마십시오
- **"분석했는데 언급이 없다"와 "아직 분석하지 않았다"를 절대 섞지 마십시오.**
  출원인 집계표의 `사업보고서 분석` 열을 그대로 따르십시오.
  - `있음`인데 그 기술 서술이 없으면 → "사업보고서에 언급 없음"
  - `미수집`이면 → "사업보고서 미수집" (이 기업이 그 기술을 안 한다는 뜻이 **아닙니다**.
    아직 자료를 모으지 않았을 뿐이므로 판단하지 말고 그대로 쓰십시오)
- 기업을 평가할 때 특허 근거와 사업보고서 근거를 **각각 무엇에서 나온 것인지 밝혀** 쓰십시오
- **등록과 공개(심사중)를 구분하십시오.** 등록은 권리를 확보한 것이고 공개는 아직
  심사 중입니다. "특허 n건"으로 뭉뚱그리지 마십시오
- 표는 반드시 GFM 형식으로 쓰십시오. 헤더 바로 아래에 `|---|---|` 구분선을 넣지 않으면
  표로 렌더되지 않습니다
- **LaTeX·수식 기호를 쓰지 마십시오.** `$...$`, `\text{}`, `_{}`, `^{}`는 그대로 노출됩니다.
  화학식은 일반 텍스트로 쓰십시오 (예: `Li6PS5Cl`, `31P-NMR`, `PS4 3-`)

다음 구조로 작성하십시오. **순서를 지키십시오.**

## 요약
3~5문장. 이 기술을 하는 곳이 어디이고 무엇이 두드러지는지.
**보고서 본문에서 당신 자신이나 분석 과정을 언급하지 마십시오.**
("본 분석가는", "본 보고서는 …를 근거로 작성되었습니다" 같은 문장으로 시작하지 마십시오.
근거 범위는 맨 첫 줄에 이미 적었습니다.) 곧바로 기술과 기업 이야기로 들어가십시오.

## 기술 개요
**이 보고서에서 가장 자세해야 할 부분입니다.** 주어진 특허 초록에서 읽히는 기술의
실제 내용을 정리하십시오. 초록에만 있는 정보이므로 사업보고서로는 알 수 없는 것입니다.

소주제로 나눠 각각 3~5문장씩 쓰십시오. 예를 들어 이런 축으로 나눌 수 있습니다.
- 이 기술이 풀려는 문제 (무엇이 한계이고 왜 어려운가)
- 핵심 소재·조성 (결정 구조, 도핑·치환 원소, 조성비)
- 제조·공정 (합성 방법, 열처리, 입도 제어, 시트화)
- 성능·안정성 확보 방법 (이온전도도, 수분·대기 안정성, 계면 저항)
축은 실제 초록에 나타난 것에 맞춰 정하십시오. 초록에 없는 축은 만들지 마십시오.
구체적인 물질명·수치·공정명을 초록에서 그대로 인용해 쓰십시오.

## 주요 기업
사업보고서가 있는 기업(추적 중·미등록)만 다룹니다.
**특허 건수는 뒤의 「출원인 집계」에 이미 나오므로 여기서는 반복하지 마십시오.**

여기서 답할 것은 하나입니다 — **이 기업이 이 기술을 실제로 어느 단계까지 가져갔는가.**
개발만 하는가, 관심 표명 수준인가, 사업으로 계획하고 있는가, 이미 추진·양산 중인가.

| 기업 | 단계 | 근거 | 분석보고서 |
|---|---|---|---|
| (DART 기업명) | (아래 다섯 중 하나) | (그렇게 본 이유를 한 문장으로) | (출원인 집계표의 `분석보고서` 칸을 **링크 문법 그대로** 옮기십시오. `미수집`이면 그대로 "미수집") |

단계는 **사업보고서에서 확인되는 것**을 기준으로 다섯 중 하나를 고르십시오.
특허만으로는 연구 사실만 알 수 있을 뿐 단계를 알 수 없습니다.
- `추진·양산 중` — 양산 설비, 공급 계약, 매출 발생이 확인됨
- `사업계획` — 투자 결정, 합작·MOU, 실증 프로젝트, 파일럿 라인 등 구체적 움직임이 있음
- `연구개발` — 사업보고서의 연구개발 과제·조직에 이 기술이 **명시적으로** 올라와 있음
- `관심·검토` — 특허는 내지만 사업보고서에 이 기술 언급이 없음(= 아직 공시 단계가 아님)
- `판단 불가` — 사업보고서가 미수집이거나 근거가 부족함

**단계 판정의 근거는 「추적 중 기업의 사업보고서 분석」에 있는
`이 기술이 직접 언급된 대목`뿐입니다.** 그 항목이 없는 기업은 사업보고서에 이 기술이
나오지 않는다는 뜻이므로 반드시 `관심·검토`입니다. 같은 산업이라는 이유로 다른 과제를
끌어와 올려잡지 마십시오. 표의 `근거` 칸과 아래 서술이 어긋나서는 안 됩니다.

표 아래에 기업마다 **3~5문장**으로 자세히 쓰십시오. 다음을 담으십시오.
- 특허에서 읽히는 그 기업의 기술적 접근 방향 (어떤 문제를 어떤 방식으로 푸는가)
- 사업보고서에서 확인되는 사업화 신호 — 연구개발 항목에 올라와 있는가, 투자·MOU·
  실증·합작 같은 구체적 움직임이 있는가, 아니면 언급이 없는가
- 권리를 확보했는지 (등록 특허가 있는가) — **건수를 나열하지 마십시오.**
  숫자는 뒤의 「출원인 집계」에 이미 있습니다. "총 n건 보유" 같은 문장을 쓰지 마십시오
근거가 없는 항목은 없다고 쓰고 넘어가십시오. 지어내지 마십시오.

## 시사점
3~5개. 각 항목 끝에 근거를 `[특허]` 또는 `[사업보고서]`로 표시하십시오.

## 참고 — 산업 밖 주체
**반드시 이 제목으로, 보고서의 맨 마지막에 두십시오.**
대학·연구소·외국기업 등 사업보고서가 없는 출원인을 건수와 함께 나열만 하십시오.
해설은 붙이지 마십시오. 없으면 이 절 자체를 생략하십시오."""


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def select_patents(results: list[dict], names: set[str],
                   this_year: int | None = None) -> list[dict]:
    """프롬프트에 실을 대표 특허. 관심 기업(추적중·등록가능)의 것을 앞세운다.

    관심 기업 우선이 아니면 대학·외국기업 초록이 지면을 다 써서 정작
    "어느 기업이 하는가"에 답할 근거가 밀린다.

    순서는 KIPRIS 관련도순을 그대로 따른다(같은 우선순위 안에서). 최신순으로 다시
    정렬하지 않는 이유는, 관련도가 낮은 최신 특허가 관련도 높은 것을 밀어내기 때문이다.
    대신 `MAX_PATENT_AGE_YEARS`로 오래된 것을 **거른다** — 순서가 아니라 자격의 문제다.
    """
    year = this_year if this_year is not None else datetime.utcnow().year
    cutoff = f"{year - MAX_PATENT_AGE_YEARS}0000"

    seen: set[str] = set()
    fresh: list[tuple[int, dict]] = []
    old: list[tuple[int, dict]] = []
    for res in results:
        for it in res["items"]:
            if not it.get("abstract") or (it["app_no"] and it["app_no"] in seen):
                continue
            if it["app_no"]:
                seen.add(it["app_no"])
            priority = 0 if any(a in names for a in it["applicants"]) else 1
            date = it.get("app_date") or ""
            # 출원일을 모르는 것은 버리지 않는다 — 걸러야 할 근거가 없다
            (old if date and date < cutoff else fresh).append((priority, it))

    fresh.sort(key=lambda r: r[0])
    picked = [it for _, it in fresh[:MAX_PATENTS]]
    if picked:
        return picked

    # 오래된 것밖에 없는 분야라면 컷 때문에 빈손이 되는 게 더 나쁘다
    old.sort(key=lambda r: r[0])
    logger.warning("최근 %d년 특허가 없어 연령 컷을 풀었습니다", MAX_PATENT_AGE_YEARS)
    return [it for _, it in old[:MAX_PATENTS]]


def _patent_section(items: list[dict]) -> str:
    if not items:
        return "(초록이 있는 특허가 없습니다)"
    return "\n".join(
        f"- 출원인: {', '.join(it['applicants']) or '미상'} / "
        f"출원일: {it['app_date'] or '?'} / 상태: {it['status'] or '?'}\n"
        f"  제목: {it['title']}\n"
        f"  초록: {it['abstract'][:ABSTRACT_CHARS]}"
        for it in items)


def tech_terms(tech: Technology) -> list[str]:
    """기술명·키워드에서 뽑은 검색 용어. 사업보고서에 이 기술이 실제로 나오는지 재는 데 쓴다."""
    words: set[str] = set()
    for src in [tech.name, *tech_scan.get_keywords(tech)]:
        for tok in re.split(r"[\s,·/]+", src):
            tok = tok.strip()
            if len(tok) >= 3:
                words.add(tok)
    return sorted(words)


def mention_sentences(text: str, terms: list[str], limit: int = 4) -> list[str]:
    """분석 결과에서 기술 용어가 실제로 나온 문장만 추린다.

    모델에게 "명시적으로 올라와 있는가"를 판단하게 하면 같은 산업이라는 이유로
    올려잡는다(실측: 전고체 배터리인데 "FCEV 수소공급시스템용 SUS 소재" 과제를
    근거로 삼았다). 어느 문장이 걸렸는지를 코드가 뽑아 주면 헷갈릴 여지가 없다.
    """
    out: list[str] = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+", text):
        s = sent.strip(" |-")
        if s and any(t in s for t in terms):
            out.append(s[:200])
            if len(out) >= limit:
                break
    return out


def _mentions_in_source(report: Report, terms: list[str], limit: int = 4) -> list[str]:
    """사업보고서 원문에서 기술 용어가 나온 대목. 읽기 실패는 조용히 넘긴다
    (보고서 생성이 원문 파싱 때문에 통째로 죽으면 안 된다)."""
    if limit <= 0 or not report.file_path:
        return []
    try:
        body = extract_text_from_report(report.file_path)
    except Exception:
        logger.warning("원문 읽기 실패, 건너뜀: report_id=%s", report.id)
        return []
    if not body:
        return []

    out: list[str] = []
    for m in re.finditer("|".join(re.escape(t) for t in terms), body):
        seg = re.sub(r"\s+", " ", body[max(0, m.start() - 90): m.start() + 110]).strip()
        out.append(f"(원문) …{seg}…")
        if len(out) >= limit:
            break
    return out


def _company_section(db: Session, tech: Technology) -> tuple[str, set[int]]:
    """추적 중 기업의 사업보고서 분석 요약 — 각 기업의 **최신 연도** 1건만.

    반환: (마크다운, 쓰인 회계연도 집합). 연도 집합은 보고서 머리말에
    "몇 년도 사업보고서 기준인가"를 밝히는 데 쓴다 — 기업마다 최신 연도가
    다를 수 있으므로 하나로 뭉뚱그리면 안 된다.
    """
    blocks: list[str] = []
    years: set[int] = set()
    links = _report_links(db, tech)
    terms = tech_terms(tech)

    for tc in sorted(tech.companies, key=lambda t: -t.patent_count):
        if tc.status != "tracked" or not tc.company_id:
            continue

        name = tc.corp_name or tc.applicant_name
        rows = (db.query(Analysis, Report)
                .join(Report, Report.id == Analysis.report_id)
                .filter(Analysis.company_id == tc.company_id,
                        Analysis.status == AnalysisStatus.COMPLETED,
                        Analysis.analysis_type.in_(SUPPORT_TYPES))
                .order_by(Report.fiscal_year.desc())
                .all())
        if not rows:
            blocks.append(f"### {name}\n- **사업보고서 미수집** — 아직 수집·분석하지 "
                          f"않았습니다. 이 기업이 그 기술을 하지 않는다는 뜻이 아닙니다.")
            continue

        latest_year = rows[0][1].fiscal_year
        years.add(latest_year)
        link = links.get(tc.company_id)
        url = f"/companies/{tc.company_id}/reports/{link[0]}" if link else ""
        parts = [f"### {name}\n- {latest_year}년 사업보고서 기준"
                 + (f" / 분석보고서 링크: {url}" if url else "")]

        # 이 기술 용어가 실제로 나온 문장 — 단계 판정의 유일한 근거다.
        # **원문까지 뒤진다.** 분석 요약은 R&D·국가전략기술만 다루므로 회사 연혁의
        # "대만 전고체 전문기업 프롤로지움 지분 투자" 같은 사업화 신호를 놓친다
        # (실측: POSCO홀딩스가 원문 3회인데 요약엔 0회라 '관심·검토'로 내려갔다)
        joined = "\n".join((a.result_summary or "") for a, r in rows
                           if r.fiscal_year == latest_year)
        hits = mention_sentences(joined, terms)
        hits += _mentions_in_source(rows[0][1], terms, limit=4 - len(hits))
        if hits:
            parts.append("- **이 기술이 직접 언급된 대목:**\n"
                         + "\n".join(f"  - {h}" for h in hits))
        else:
            parts.append("- **이 기술은 사업보고서에 언급되지 않았습니다.** 같은 산업의 "
                         "다른 과제를 근거로 삼지 마십시오.")

        for a, r in rows:
            if r.fiscal_year != latest_year:
                continue
            parts.append(f"\n**{a.analysis_type}**\n{(a.result_summary or '')[:MAX_ANALYSIS_CHARS]}")
        blocks.append("\n".join(parts))

    return ("\n\n".join(blocks) if blocks else "(추적 중인 기업이 없습니다)"), years


# KIPRIS registerStatus 실측 분포: 공개·등록·거절·취하·소멸
# 권리를 확보한 '등록'과 아직 심사 중인 '공개'는 의미가 전혀 다르므로 갈라서 센다
_REGISTERED = "등록"
_PENDING = "공개"


def patent_stats(results: list[dict]) -> dict[str, dict]:
    """출원인별 상태 집계. 같은 특허가 여러 키워드에 걸리면 출원번호로 접는다."""
    seen: set[str] = set()
    stats: dict[str, dict] = {}
    for res in results:
        for it in res["items"]:
            if it["app_no"] and it["app_no"] in seen:
                continue
            if it["app_no"]:
                seen.add(it["app_no"])
            for name in it["applicants"]:
                s = stats.setdefault(name, {"total": 0, "registered": 0, "pending": 0})
                s["total"] += 1
                if it["status"] == _REGISTERED:
                    s["registered"] += 1
                elif it["status"] == _PENDING:
                    s["pending"] += 1
    return stats


def date_span(items: list[dict]) -> tuple[str, str] | None:
    """출원일 범위.

    **보고서에 실제로 실린 특허만 넘겨야 한다.** 수집 전체로 재면 상위 40건에
    들지도 못한 1994년 특허 1건 때문에 "1994~2026"이 되어, 30년치를 종합한
    것처럼 읽힌다(실측: 실제로 쓰인 40건은 2014~2025이고 그중 95%가 2016년 이후).
    """
    dates = [it["app_date"] for it in items if it.get("app_date")]
    return (min(dates), max(dates)) if dates else None


def _fmt_date(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}.{yyyymmdd[4:6]}" if len(yyyymmdd) >= 6 else yyyymmdd


def _report_links(db: Session, tech: Technology) -> dict[int, tuple[int, int]]:
    """company_id → (최신 분석완료 보고서 id, 회계연도). 링크와 기준연도를 여기서 정한다."""
    ids = [tc.company_id for tc in tech.companies if tc.company_id]
    if not ids:
        return {}
    rows = (db.query(Analysis.company_id, Report.id, Report.fiscal_year)
            .join(Report, Report.id == Analysis.report_id)
            .filter(Analysis.company_id.in_(ids),
                    Analysis.status == AnalysisStatus.COMPLETED,
                    Analysis.analysis_type.in_(SUPPORT_TYPES))
            .order_by(Report.fiscal_year.desc()).all())
    out: dict[int, tuple[int, int]] = {}
    for cid, rid, year in rows:
        out.setdefault(cid, (rid, year))      # 정렬이 내림차순이라 첫 항목이 최신
    return out


def _applicant_table(db: Session, tech: Technology,
                     stats: dict[str, dict] | None = None) -> str:
    """출원인 집계표. 건수를 표로 먼저 주지 않으면 모델이 초록을 훑어 '다수'라고 뭉갠다.

    **등록과 공개를 가른다.** 등록은 권리를 확보한 것이고 공개는 아직 심사 중이라
    의미가 다르다. 합계만 주면 모델이 "특허 16건 보유"처럼 뭉뚱그린다.

    **분석 여부도 따로 준다.** "분석했는데 그 기술 언급이 없다"(= 아직 양산 전)와
    "분석 자체를 안 했다"(= 그냥 자료 없음)는 완전히 다른 정보인데, 이 구분을
    주지 않으면 모델이 둘 다 "사업보고서에 언급 없음"으로 써서 전업 배터리 회사가
    그 기술을 안 하는 것처럼 읽힌다(실측: LG에너지솔루션).
    """
    rows = sorted(tech.companies, key=lambda t: -t.patent_count)[:30]
    if not rows:
        return "(스캔 결과가 없습니다)"

    links = _report_links(db, tech)
    label = {"tracked": "추적 중", "available": "미등록(DART 있음)", "excluded": "사업보고서 없음"}
    out = ["| 출원인 | DART 기업명 | 특허 합계 | 등록 | 공개(심사중) | 키워드 적중 | 상태 | 분석보고서 |",
           "|---|---|---|---|---|---|---|---|"]
    for tc in rows:
        try:
            hits = len(json.loads(tc.keyword_hits or "[]"))
        except json.JSONDecodeError:
            hits = 0
        status = label.get(tc.status, tc.status)
        if tc.status == "excluded" and tc.exclude_reason:
            status = f"{status} — {tc.exclude_reason}"

        s = (stats or {}).get(tc.applicant_name) or {}
        reg = s.get("registered", "?")
        pend = s.get("pending", "?")

        link = links.get(tc.company_id) if tc.company_id else None
        cell = (f"[{link[1]}년 사업보고서](/companies/{tc.company_id}/reports/{link[0]})"
                if link else "미수집")

        out.append(f"| {tc.applicant_name} | {tc.corp_name or '-'} | {tc.patent_count} | "
                   f"{reg} | {pend} | {hits} | {status} | {cell} |")
    return "\n".join(out)


def basis_line(span: tuple[str, str] | None, years: set[int]) -> str:
    """이 보고서가 무엇을 근거로 삼았는지 한 줄. 화면과 보고서 양쪽에서 쓴다."""
    pat = (f"특허 출원일 {_fmt_date(span[0])}~{_fmt_date(span[1])}"
           if span else "특허 기간 미상")
    if not years:
        rep = "사업보고서 미수집"
    elif len(years) == 1:
        rep = f"{next(iter(years))}년 사업보고서"
    else:
        rep = f"{min(years)}~{max(years)}년 사업보고서(기업별 최신)"
    return f"{pat} / {rep}"


def year_histogram(items: list[dict]) -> str:
    """실린 특허의 출원연도 분포. 모델이 '최근 동향'과 '오래된 기반 기술'을
    구분해 쓸 수 있게 한다."""
    counts: dict[str, int] = {}
    for it in items:
        if it.get("app_date"):
            counts[it["app_date"][:4]] = counts.get(it["app_date"][:4], 0) + 1
    if not counts:
        return "(출원일 정보 없음)"
    return ", ".join(f"{y}년 {counts[y]}건" for y in sorted(counts, reverse=True))


def build_prompt(tech: Technology, results: list[dict], company_md: str,
                 applicant_md: str, names: set[str],
                 span: tuple[str, str] | None = None,
                 years: set[int] | None = None,
                 items: list[dict] | None = None) -> str:
    searched = "\n".join(
        f"- {r['word']} — 총 {r['total']:,}건"
        + ("  ※넓은 키워드(기술 특이성이 희석됨)" if r["total"] > patent_search.BROAD_THRESHOLD else "")
        for r in results)
    items = items if items is not None else select_patents(results, names)

    return f"""# 대상 기술
{tech.name}

{tech.description}

# 이 보고서의 근거 범위
{basis_line(span, years or set())}

- 위 범위는 아래 「대표 특허」에 실제로 실린 특허의 출원일 구간입니다(관련도순 상위).
  기술 개요의 재료는 **최근 {MAX_PATENT_AGE_YEARS}년 이내 출원분**으로 한정했습니다 —
  기업 목록과 특허 건수는 기간 제한 없이 집계한 것이라 범위가 다릅니다
- 실린 특허의 출원연도 분포: {year_histogram(items)}
- 특허는 출원 **18개월 뒤**에 공개되므로 가장 최근 1~2년은 아직 덜 드러납니다.
  최신 연도의 건수가 적은 것은 활동이 준 것이 아닙니다
- 사업보고서는 **기업마다 가장 최근 것 1건**을 씁니다. 연도가 기업마다 다를 수 있습니다
- 보고서 첫머리에 이 범위를 한 줄로 밝히십시오

# 특허 검색 결과
{searched}

# 대표 특허 (초록)
{_patent_section(items)}

# 추적 중 기업의 사업보고서 분석 (보조 근거)
{company_md}

# 출원인 집계
아래 숫자를 그대로 쓰십시오. "다수"처럼 뭉개지 말고 건수를 밝히십시오.
`분석보고서` 칸의 링크는 **문법 그대로** 옮기십시오.

{applicant_md}
"""


def _call(prompt: str) -> str:
    r = _get_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MINIMAL),
        ),
    )
    return r.text or ""


async def generate(db: Session, tech: Technology) -> str:
    """기술 종합 보고서를 만들어 저장하고 마크다운을 돌려준다.

    특허를 다시 검색한다 — 스캔은 출원인 집계만 저장하고 초록을 버리기 때문이다.
    KIPRIS 한도는 api_usage가 호출 전에 막는다.
    """
    keywords = tech_scan.get_keywords(tech)
    if not keywords:
        raise ValueError("검색 키워드가 없습니다. 먼저 키워드를 설정하십시오.")

    results = []
    for word in keywords:
        try:
            results.append(await patent_search.search(db, word))
        except Exception as e:
            # 키워드 하나가 실패해도 나머지로 보고서는 쓸 수 있다. 다만 무엇이 빠졌는지는 남긴다
            logger.warning("특허 검색 실패, 건너뜀: %r — %s", word, e)
    if not results:
        raise ValueError("특허 검색이 모두 실패해 보고서를 만들 수 없습니다.")

    names = {tc.applicant_name for tc in tech.companies
             if tc.status in ("tracked", "available")}
    stats = patent_stats(results)                   # 기업 집계는 기간 제한 없이 전체
    items = select_patents(results, names)          # 초록 재료는 최근분만, 범위도 이걸로 잰다
    span = date_span(items)
    company_md, years = _company_section(db, tech)
    prompt = build_prompt(tech, results, company_md,
                          _applicant_table(db, tech, stats), names, span, years, items)
    logger.info("기술 보고서 프롬프트 %d자 (기술=%s, 근거=%s)",
                len(prompt), tech.name, basis_line(span, years))

    loop = asyncio.get_running_loop()
    md = await loop.run_in_executor(None, partial(_call, prompt))
    if not md.strip():
        raise ValueError("모델이 빈 응답을 반환했습니다.")

    tech.report_md = md
    tech.report_basis = basis_line(span, years)
    tech.report_generated_at = datetime.utcnow()
    db.commit()
    return md
