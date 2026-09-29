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
import logging
import re
from collections import defaultdict
from datetime import datetime

from google.genai import types
from sqlalchemy.orm import Session

from app.config import gemini
from app.constants import AnalysisStatus, TechStatus
from app.models import Analysis, Report, Technology
from app.services import patent_search, tech_scan
from app.services.report_service import extract_text_from_report

logger = logging.getLogger(__name__)

MODEL = "gemini-3.8-flash"   # MINIMAL 미지원 — LOW가 하한
MAX_OUTPUT_TOKENS = 16384

# 「기술 개요」를 쓸 초록 재료의 수. **기업 목록과는 무관하다** — 기업 발굴과
# 특허 건수 집계는 수집 전체(실측 321건)로 하고, 이 상한은 프롬프트에 실을 초록만 자른다
MAX_PATENTS = 80
ABSTRACT_CHARS = 500
MAX_ANALYSIS_CHARS = 3000

# rnd는 앞 N자 대신 이 절들을 제목으로 잘라 싣는다. 「기술 사업화 동향」이 사업화 단계
# 판정의 핵심 근거인데 3.8-flash에서 길어져(POSCO홀딩스 52행·3,971자) 앞 3,000자에서 잘렸다.
# 상한은 실측 최대의 여유분 — 요약 최대 243자, 사업화 동향 최대 3,971자(3.8 LOW, 7개사)
RND_SECTIONS = {"요약": 600, "기술 사업화 동향": 5000}

# 이보다 오래된 특허는 초록 재료에서 뺀다.
# 상한을 늘리면 뒤쪽(관련도가 낮고 오래된 것)이 딸려 들어오는데, 10년도 더 된 특허의
# 조성·공정을 현재 기술 개요에 섞으면 지금 무엇이 쟁점인지가 흐려진다.
# 실측(전고체 배터리): 상위 40건의 95%가 이미 최근 10년 안이라 이 컷으로 잃는 게 거의 없다.
# 값은 patent_search.RECENT_YEARS에서 바꾼다 — 여기는 프롬프트·로그 표시용 별칭이다
MAX_PATENT_AGE_YEARS = patent_search.RECENT_YEARS

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

소주제(`###`) 3~5개로 나눠 각각 3~5문장씩 쓰십시오. 첫 소주제는 "이 기술이 풀려는 문제"로
하고, 나머지는 **초록에 실제로 많이 나온 접근**을 기준으로 이 기술 분야의 말로 이름 붙이십시오
(예: 소재 분야면 조성·합성 공정, 바이오면 표적·전달 방법·세포 제조, 소프트웨어면 모델 구조·
학습 방법). 소주제 제목에 괄호 설명을 붙이지 마십시오.
구체적인 물질명·수치·공정명·표적명을 초록에서 그대로 인용해 쓰십시오.

## 주요 기업
표는 자료의 「주요 기업」 표 틀을 **행·순서·링크 그대로** 옮기고 `?` 칸만 채우십시오.
틀에 없는 기업을 더하지 마십시오. 자료에 「등록 후보」 줄이 있으면 표 바로 아래에 그대로 옮기십시오.
**특허 건수는 뒤의 「출원인 집계」에 이미 나오므로 여기서는 반복하지 마십시오.**

여기서 답할 것은 하나입니다 — **이 기업이 이 기술을 실제로 어느 단계까지 가져갔는가.**
개발만 하는가, 관심 표명 수준인가, 사업으로 계획하고 있는가, 이미 추진·양산 중인가.

| 기업 | 단계 | 근거 | 분석보고서 |
|---|---|---|---|
| (틀 그대로) | (`?`면 아래 다섯 중 하나) | (`?`면 그 단계의 근거가 된 대목의 핵심 구절을 따옴표로 짧게 인용) | (틀 그대로) |

단계는 **사업보고서에서 확인되는 것**을 기준으로 다섯 중 하나를 고르십시오.
특허만으로는 연구 사실만 알 수 있을 뿐 단계를 알 수 없습니다.
- `추진·양산 중` — **이 기술 제품의** 양산 설비, 공급 계약, 매출 발생이 확인됨
  (같은 대목에 붙은 다른 제품의 계약·수주는 해당하지 않습니다)
- `사업계획` — 투자 결정, 합작·MOU, 실증 프로젝트, 파일럿 라인 등 구체적 움직임이 있음
- `연구개발` — 사업보고서의 연구개발 과제·조직에 이 기술이 **명시적으로** 올라와 있음
- `관심·검토` — 특허는 내지만 사업보고서에 이 기술 언급이 없음(= 아직 공시 단계가 아님)
- `판단 불가` — 사업보고서가 미수집이거나 근거가 부족함

**단계 판정의 근거는 「추적 중 기업의 사업보고서 분석」에 있는
`이 기술이 직접 언급된 대목`뿐입니다.**
- `단계: … (확정)`이 적힌 기업은 **그 단계를 그대로** 쓰십시오
- 그 밖의 기업은 대목을 **모두** 읽고, 그중 **가장 높은 단계의 신호**로 정하십시오.
  연혁·임원 보수 사유·조직 신설 같은 대목에도 신호가 있습니다(예: "사업화 추진팀 신설",
  "실증 프로젝트 업무협약", "지분 투자"는 `사업계획`, 이 기술 제품의 "공장 준공"은 `추진·양산 중`)
- 용어가 걸렸어도 이 기술과 무관한 맥락(예: 종자 '유전자원', 가전제품 배터리)뿐이면 `관심·검토`입니다
같은 산업이라는 이유로 다른 과제를 끌어와 올려잡지 마십시오. 표의 `근거` 칸과 아래 서술이
어긋나서는 안 됩니다.

표 아래에 기업마다 **3~5문장**으로 자세히 쓰십시오. 다음을 담으십시오.
- 특허에서 읽히는 그 기업의 기술적 접근 방향 (어떤 문제를 어떤 방식으로 푸는가)
- 사업보고서에서 확인되는 사업화 신호 — 연구개발 항목에 올라와 있는가, 투자·MOU·
  실증·합작 같은 구체적 움직임이 있는가, 아니면 언급이 없는가
- 권리를 확보했는지 (등록 특허가 있는가) — **건수를 나열하지 마십시오.**
  숫자는 뒤의 「출원인 집계」에 이미 있습니다. "총 n건 보유" 같은 문장을 쓰지 마십시오
근거가 없는 항목은 없다고 쓰고 넘어가십시오. 지어내지 마십시오.

## 시사점
3~5개. 각 항목 끝에 근거를 `[특허]` 또는 `[사업보고서]`로 표시하십시오.
**시사점이 마지막 절입니다.** 대학·연구소 목록은 따로 붙으므로 쓰지 마십시오."""


def select_patents(results: list[dict], names: set[str],
                   this_year: int | None = None) -> list[dict]:
    """프롬프트에 실을 대표 특허. 관심 기업(추적중·등록가능)의 것을 앞세운다.

    관심 기업 우선이 아니면 대학·외국기업 초록이 지면을 다 써서 정작
    "어느 기업이 하는가"에 답할 근거가 밀린다.

    순서는 KIPRIS 관련도순을 그대로 따른다(같은 우선순위 안에서). 최신순으로 다시
    정렬하지 않는 이유는, 관련도가 낮은 최신 특허가 관련도 높은 것을 밀어내기 때문이다.
    대신 `MAX_PATENT_AGE_YEARS`로 오래된 것을 **거른다** — 순서가 아니라 자격의 문제다.
    """
    cutoff = patent_search.recent_cutoff(this_year)

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


# 사업보고서 대조에 쓸 용어는 수집한 특허의 이 비율 이상에 나와야 한다.
# 기술명의 머리말(예: '전고체 배터리'의 '배터리')은 소비자 용어라 특허는 거의 쓰지 않는데
# (실측: 전고체 특허 671건 중 3%) 사업보고서에는 흔하다(11개사 중 8곳, 삼성전자는 청소기
# 배터리로 30회). 이게 걸리면 전고체와 무관한 기아·삼성전자·현대차가 '직접 언급'을 얻어
# 모델이 셋을 `연구개발`로 올렸다. 핵심어는 이 선을 여유 있게 넘는다(전고체 57%·황화물계 52%)
TERM_MIN_SHARE = 0.05


def tech_terms(tech: Technology, results: list[dict] | None = None) -> list[str]:
    """기술명·키워드에서 뽑은 검색 용어. 사업보고서에 이 기술이 실제로 나오는지 재는 데 쓴다.

    `results`를 주면 **특허가 실제로 쓰는 말**만 남긴다(`TERM_MIN_SHARE`).
    """
    words: set[str] = set()
    for src in [tech.name, *tech_scan.get_keywords(tech)]:
        for tok in re.split(r"[\s,·/]+", src):
            tok = tok.strip()
            if len(tok) >= 3:
                words.add(tok)
    if results:
        docs = {it["app_no"] or id(it): it["title"] + (it.get("abstract") or "")
                for r in results for it in r["items"]}.values()
        kept = {w for w in words if sum(w in d for d in docs) >= TERM_MIN_SHARE * len(docs)}
        if kept:             # 전부 걸러지면 거를 근거가 약한 것이다 — 원래대로 쓴다
            words = kept
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


def _source_text(report: Report) -> str | None:
    """사업보고서 원문. 읽기 실패는 None — 보고서 생성이 원문 파싱 때문에 통째로 죽으면 안 된다."""
    if not report.file_path:
        return None
    try:
        return extract_text_from_report(report.file_path, report.rcept_no) or None
    except Exception:
        logger.warning("원문 읽기 실패, 건너뜀: report_id=%s", report.id)
        return None


def _mentions_in_source(body: str | None, terms: list[str], limit: int = 5) -> list[str]:
    """사업보고서 원문(`_source_text`)에서 기술 용어가 나온 대목."""
    if not body:
        return []

    # 같은 대목이 겹쳐 잡히거나(용어 둘이 한 문장에) 원문에 두 번 실리는(임원 보수 사유 등)
    # 경우를 접는다. 실측: POSCO홀딩스 4칸 중 2칸이 같은 연혁 한 줄이었다
    out: list[str] = []
    end = -1
    for m in re.finditer("|".join(re.escape(t) for t in terms), body):
        if m.start() < end:
            continue
        end = m.start() + 110
        seg = re.sub(r"\s+", " ", body[max(0, m.start() - 90): end]).strip()
        line = f"(원문) …{seg}…"
        if line not in out:
            out.append(line)
        if len(out) >= limit:
            break
    return out


def _section(md: str, title: str, cap: int) -> str | None:
    """`## title`부터 다음 `## ` 제목 전까지. 상한을 넘으면 줄 단위로 자른다(표 행이 반쪽 나지 않게)."""
    m = re.search(rf"^## {re.escape(title)}[^\n]*\n", md, re.M)
    if not m:
        return None
    nxt = re.search(r"^## ", md[m.end():], re.M)
    sec = md[m.start(): (m.end() + nxt.start()) if nxt else len(md)].rstrip()
    if len(sec) > cap:
        sec = sec[:cap].rsplit("\n", 1)[0] + "\n…(이하 생략)"
    return sec


def _analysis_excerpt(a: Analysis) -> str:
    """분석 결과 중 프롬프트에 실을 부분. rnd는 RND_SECTIONS 절, 나머지와 절이 없는 옛 결과는 앞 N자."""
    md = a.result_summary or ""
    if a.analysis_type == "rnd":
        secs = {t: _section(md, t, cap) for t, cap in RND_SECTIONS.items()}
        if secs["기술 사업화 동향"]:
            return "\n\n".join(s for s in secs.values() if s)
    return md[:MAX_ANALYSIS_CHARS]


def _live(tech: Technology) -> list:
    """마지막 스캔에 나온 출원인만. 이탈 기업은 지우지 않고 `last_seen_at`으로 드러내므로
    (tech_scan._merge) 거르지 않으면 키워드를 바꾸기 전의 기업이 보고서에 남는다
    — 실측: 옛 키워드 '리튬 이온 전도도'로만 걸렸던 HLB제약이 전고체 보고서의 주요 기업에 올랐다."""
    at = tech.last_scanned_at
    live = [tc for tc in tech.companies if not (at and tc.last_seen_at and tc.last_seen_at < at)]
    return sorted(live, key=lambda t: -t.patent_count)   # 표·본문·부록 모두 특허 건수순


def _support_query(db: Session, ids: list[int], *cols):
    """보조 근거로 쓰는 완료 분석(SUPPORT_TYPES)과 그 보고서 — 최신 회계연도가 앞에 온다.
    본문(`_company_section`)과 출원인 표 링크(`_report_links`)가 같은 조건을 써야 링크가 어긋나지 않는다."""
    return (db.query(*cols)
            .join(Report, Report.id == Analysis.report_id)
            .filter(Analysis.company_id.in_(ids),
                    Analysis.status == AnalysisStatus.COMPLETED,
                    Analysis.analysis_type.in_(SUPPORT_TYPES))
            .order_by(Report.fiscal_year.desc()))


def _company_section(db: Session, tech: Technology,
                     terms: list[str] | None = None) -> tuple[str, set[int]]:
    """추적 중 기업의 사업보고서 분석 요약 — 각 기업의 **최신 연도** 1건만.

    반환: (마크다운, 쓰인 회계연도 집합). 연도 집합은 보고서 머리말에
    "몇 년도 사업보고서 기준인가"를 밝히는 데 쓴다 — 기업마다 최신 연도가
    다를 수 있으므로 하나로 뭉뚱그리면 안 된다.
    """
    blocks: list[str] = []
    table: list[str] = []            # 「주요 기업」 표의 틀 — 행·링크·확정 단계는 코드가 정한다
    years: set[int] = set()
    terms = terms or tech_terms(tech)
    live = _live(tech)

    # 추적 기업의 분석을 한 번에 — 기업마다 조회하면 N+1이다. 최신 연도가 앞에 온다
    ids = [tc.company_id for tc in live if tc.status == TechStatus.TRACKED and tc.company_id]
    by_co: dict[int, list] = defaultdict(list)
    if ids:
        for a, r in _support_query(db, ids, Analysis, Report):
            by_co[a.company_id].append((a, r))
    links = {cid: (rows[0][1].id, rows[0][1].fiscal_year) for cid, rows in by_co.items()}

    for tc in live:
        if tc.status != TechStatus.TRACKED or not tc.company_id:
            continue

        name = tc.corp_name or tc.applicant_name
        rows = by_co.get(tc.company_id, [])
        if not rows:
            blocks.append(f"### {name}\n- **단계: 판단 불가 (확정)**\n- **사업보고서 미수집** — "
                          f"아직 수집·분석하지 않았습니다. 이 기업이 그 기술을 하지 않는다는 뜻이 아닙니다.")
            table.append(f"| {name} | 판단 불가 | 사업보고서 미수집 | 미수집 |")
            continue

        latest_year = rows[0][1].fiscal_year
        years.add(latest_year)
        url, cell = _report_cell(links, tc.company_id)
        parts = [f"### {name}\n- {latest_year}년 사업보고서 기준"
                 + (f" / 분석보고서 링크: {url}" if url else "")]

        # 이 기술 용어가 실제로 나온 문장 — 단계 판정의 유일한 근거다.
        # **원문까지 뒤진다.** 분석 요약은 R&D·국가전략기술만 다루므로 회사 연혁의
        # "대만 전고체 전문기업 프롤로지움 지분 투자" 같은 사업화 신호를 놓친다
        # (실측: POSCO홀딩스가 원문 3회인데 요약엔 0회라 '관심·검토'로 내려갔다)
        joined = "\n".join((a.result_summary or "") for a, r in rows
                           if r.fiscal_year == latest_year)
        # 원문은 요약의 남은 칸이 아니라 **자기 몫**을 갖는다. 요약이 4칸을 다 채우면
        # 원문을 보지 않았는데, 사업화 신호는 대개 원문에만 있다(실측: 삼성SDI의
        # "BMW와 전고체 배터리 실증 프로젝트 업무협약"·"ASB 사업화 추진팀 신설"이
        # 한 번도 프롬프트에 실리지 않아 단계가 회차마다 흔들렸다)
        # 분석 결과에는 모델의 해석이 섞인다. **원문에 없는 기술 용어는 근거로 받지 않는다.**
        # 실측: 현대자동차 원문에 '전고체'가 0회인데 3.8-flash 분석이 Solid Power·Factorial 지분
        # 투자를 "전고체 배터리 상용화 경쟁에 대비"로 풀어 써서, 그 문장이 '직접 언급'으로 잡혀
        # 4회 모두 `사업계획`이 됐다. 원문을 못 읽으면 예전처럼 분석 결과를 그대로 본다
        body = _source_text(rows[0][1])
        seen = [t for t in terms if t in body] if body else terms
        hits = mention_sentences(joined, seen, limit=3) if seen else []
        hits += _mentions_in_source(body, terms)
        if hits:
            parts.append("- **이 기술이 직접 언급된 대목:**\n"
                         + "\n".join(f"  - {h}" for h in hits))
            table.append(f"| {name} | ? | ? | {cell} |")
        else:
            table.append(f"| {name} | 관심·검토 | 사업보고서에 언급 없음 | {cell} |")
            parts.append("- **단계: 관심·검토 (확정)**\n"
                         "- **이 기술은 사업보고서에 언급되지 않았습니다.** 같은 산업의 "
                         "다른 과제를 근거로 삼지 마십시오.")

        for a, r in rows:
            if r.fiscal_year != latest_year:
                continue
            parts.append(f"\n**{a.analysis_type}**\n{_analysis_excerpt(a)}")
        blocks.append("\n".join(parts))

    if not blocks:
        return "(추적 중인 기업이 없습니다)", years

    # 행 선택·링크·확정 단계를 모델에 맡기면 3.5-flash-lite가 추적 기업을 빠뜨리고(3회 중 2회)
    # 미등록 후보에 대학·연구소를 섞었다(3회 중 2회). 코드가 아는 것은 코드가 채운다
    blocks.append("### 「주요 기업」 표 틀\n이 표를 행·순서·링크 그대로 옮기고 `?` 칸만 채우십시오.\n\n"
                  "| 기업 | 단계 | 근거 | 분석보고서 |\n|---|---|---|---|\n" + "\n".join(table))
    cands = [tc.corp_name for tc in live if tc.status == TechStatus.AVAILABLE and tc.corp_name]
    if cands:
        blocks.append("### 등록 후보\n표 아래에 이 줄을 그대로 옮기십시오.\n\n"
                      f"등록 후보(DART 상장·미등록, 사업보고서 미수집): {', '.join(cands)}")
    return "\n\n".join(blocks), years


# KIPRIS registerStatus 실측 분포: 공개·등록·거절·취하·소멸
# 권리를 확보한 '등록'과 아직 심사 중인 '공개'는 의미가 전혀 다르므로 갈라서 센다
_REGISTERED = "등록"
_PENDING = "공개"


def patent_stats(results: list[dict]) -> dict[str, dict]:
    """출원인별 상태 집계. 같은 특허가 여러 키워드에 걸리면 출원번호로 접는다."""
    stats: dict[str, dict] = {}
    for _, it in patent_search.unique_items(results):
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
    out: dict[int, tuple[int, int]] = {}
    for cid, rid, year in _support_query(db, ids, Analysis.company_id, Report.id, Report.fiscal_year):
        out.setdefault(cid, (rid, year))      # 정렬이 내림차순이라 첫 항목이 최신
    return out


def _report_cell(links: dict[int, tuple[int, int]], company_id: int | None) -> tuple[str, str]:
    """(분석보고서 URL, 표의 「분석보고서」 칸). 없으면 ("", "미수집")."""
    link = links.get(company_id) if company_id else None
    if not link:
        return "", "미수집"
    url = f"/companies/{company_id}/reports/{link[0]}"
    return url, f"[{link[1]}년 사업보고서]({url})"


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
    rows = _live(tech)[:30]
    if not rows:
        return "(스캔 결과가 없습니다)"

    links = _report_links(db, tech)
    label = {TechStatus.TRACKED: "추적 중", TechStatus.AVAILABLE: "미등록(DART 있음)",
             TechStatus.EXCLUDED: "사업보고서 없음"}
    out = ["| 출원인 | DART 기업명 | 특허 합계 | 등록 | 공개(심사중) | 키워드 적중 | 상태 | 분석보고서 |",
           "|---|---|---|---|---|---|---|---|"]
    for tc in rows:
        hits = len(tech_scan.json_list(tc.keyword_hits))
        status = label.get(tc.status, tc.status)
        if tc.status == TechStatus.EXCLUDED and tc.exclude_reason:
            status = f"{status} — {tc.exclude_reason}"

        s = (stats or {}).get(tc.applicant_name) or {}
        # 합계도 등록·공개와 같은 검색에서 잰다. 스캔 시점 값(patent_count)과 섞으면
        # 합계 < 등록+공개가 되는 행이 생긴다
        total = s.get("total", tc.patent_count)
        reg = s.get("registered", "?")
        pend = s.get("pending", "?")

        _, cell = _report_cell(links, tc.company_id)

        out.append(f"| {tc.applicant_name} | {tc.corp_name or '-'} | {total} | "
                   f"{reg} | {pend} | {hits} | {status} | {cell} |")
    return "\n".join(out)


# 이 제목은 프론트(TechReport.tsx)가 접는 기준이다 — 바꾸면 양쪽을 같이 바꾼다
APPENDIX_TITLE = "## 참고 — 산업 밖 주체"
_APPENDIX_RE = re.compile(r"^##\s*참고.*산업\s*밖\s*주체.*$", re.M)


def appendix(tech: Technology, stats: dict[str, dict]) -> str:
    """「참고 — 산업 밖 주체」는 코드가 쓴다. 표를 옮겨 적는 일이라 모델에 맡길 이유가 없는데,
    맡기면 틀린다 — 실측(3.5-flash-lite 3회): 공개 건수를 `합계−등록`으로 계산해 13곳을
    틀렸고(거절·취하가 빠진다), 제목을 "참고 — 참고 — 산업 밖 주체"로 써서 화면 접기가 풀렸다."""
    lines = []
    for tc in _live(tech)[:30]:
        if tc.status != TechStatus.EXCLUDED:
            continue
        s = stats.get(tc.applicant_name) or {}
        lines.append(f"- {tc.applicant_name} — {s.get('total', tc.patent_count)}건"
                     f" (등록 {s.get('registered', '?')} · 공개 {s.get('pending', '?')})")
    return f"{APPENDIX_TITLE}\n\n" + "\n".join(lines) if lines else ""


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
        + ("  ※넓은 키워드(기술 특이성이 희석됨)" if patent_search.is_broad(r["total"]) else "")
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
    r = gemini().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW),
        ),
    )
    return r.text or ""


def assemble(db: Session, tech: Technology, results: list[dict]) -> tuple[str, str, str]:
    """검색 결과 → (프롬프트, 근거 범위 한 줄, 부록). 검색과 분리해 두면 캐시로 재현 실험을 할 수 있다."""
    names = {tc.applicant_name for tc in _live(tech)
             if tc.status != TechStatus.EXCLUDED}
    stats = patent_stats(results)                   # 기업 집계는 기간 제한 없이 전체
    items = select_patents(results, names)          # 초록 재료는 최근분만, 범위도 이걸로 잰다
    span = date_span(items)
    company_md, years = _company_section(db, tech, tech_terms(tech, results))
    prompt = build_prompt(tech, results, company_md,
                          _applicant_table(db, tech, stats), names, span, years, items)
    return prompt, basis_line(span, years), appendix(tech, stats)


def finish(md: str, tail: str) -> str:
    """모델 본문 + 코드가 쓴 부록. 지시를 어기고 모델이 부록을 쓴 경우 그 부분은 버린다."""
    md = _APPENDIX_RE.split(md, maxsplit=1)[0].rstrip()
    return f"{md}\n\n{tail}" if tail else md


async def generate(db: Session, tech: Technology) -> str:
    """기술 종합 보고서를 만들어 저장하고 마크다운을 돌려준다.

    특허를 다시 검색한다 — 스캔은 출원인 집계만 저장하고 초록을 버리기 때문이다.
    KIPRIS 한도는 api_usage가 호출 전에 막는다.
    """
    keywords = tech_scan.get_keywords(tech)
    if not keywords:
        raise ValueError("검색 키워드가 없습니다. 먼저 키워드를 설정하십시오.")

    # 스캔과 같은 IPC 조건으로 검색한다 — 조건이 다르면 화면의 기업 목록과 보고서 표가 어긋난다.
    # 코어가 없어도 여기서 저장하지 않는다(코어를 정하는 건 스캔이다)
    try:
        results, _ = await tech_scan.search_in_core(db, tech, keywords, pages=1)
    except tech_scan.ScanIncomplete as e:
        raise ValueError(f"특허 검색이 실패해 보고서를 만들 수 없습니다: {e}") from e

    # 원문 ZIP 수십 개를 풀고 정규식을 돌리므로 스레드로 넘긴다 — 이벤트 루프(큐 워커·API)를 막지 않게
    prompt, basis, tail = await asyncio.to_thread(assemble, db, tech, results)
    logger.info("기술 보고서 프롬프트 %d자 (기술=%s, 근거=%s)", len(prompt), tech.name, basis)

    md = await asyncio.to_thread(_call, prompt)
    if not md.strip():
        raise ValueError("모델이 빈 응답을 반환했습니다.")

    md = finish(md, tail)
    tech.report_md = md
    tech.report_basis = basis
    tech.report_generated_at = datetime.utcnow()
    db.commit()
    return md
