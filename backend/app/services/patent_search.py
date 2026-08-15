"""KIPRIS 특허 검색 → 출원인 집계 → DART 기업 조인.

게이트웨이가 둘이고 인증 파라미터명이 다르다. 여기서는 data.go.kr 발급 키를 쓰는
`/kipo-api/kipi/` + `ServiceKey` 조합만 다룬다. 서비스 경로의 `Sevice`는 오타가 아니라
실제 경로이고, `patent`·`utility`는 필수다(빠지면 파라미터 오류).

호출은 전부 api_usage를 거친다 — 무료 한도가 월 1,000회뿐이라 세지 않으면 조용히 말라죽는다.
"""
import asyncio
import logging
from collections import Counter
from functools import partial

import httpx
from sqlalchemy.orm import Session
import xml.etree.ElementTree as ET

from app.config import settings
from app.models import ApplicantCorp, Company, DartCorp
from app.services import api_usage

logger = logging.getLogger(__name__)

BASE = "https://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice"
PROVIDER = "kipris"

# 실측: 7자 2,440건 → 27자 318건(정밀) → 86자 8건(과협소) → 251자 20,029건(노이즈)
GOOD_QUERY_LEN = (4, 30)

# 총건수가 이보다 크면 "넓은 키워드"로 본다. 결과가 쓰레기가 되는 건 아니지만
# (관련도순이라 상위 100건은 여전히 관련 있다) 기술 특이성이 희석된다 —
# "그 기술을 하는 곳" 대신 "그 산업의 큰 회사"가 올라온다.
# 실측: 좁은 것만 쓴 상위 10과 전부 쓴 상위 10이 9개 겹쳤다. 버릴 만큼 해롭지는 않으므로
# 버리지 않고 **몇 개 키워드에서 나왔는지**를 함께 보여 구분하게 한다.
BROAD_THRESHOLD = 20_000


class PatentSearchError(RuntimeError):
    pass


def _get(op: str, params: dict) -> str:
    """동기 호출 — executor에서 돌린다."""
    params = {**params, "ServiceKey": settings.kipris_api_key}
    r = httpx.get(f"{BASE}/{op}", params=params, timeout=60)
    r.raise_for_status()
    return r.text


def _parse(xml_text: str) -> tuple[str, int, list[dict]]:
    """(resultCode, totalCount, items)"""
    root = ET.fromstring(xml_text)
    code = next((e.text for e in root.iter("resultCode")), "?")
    total_raw = next((e.text for e in root.iter("totalCount")), "0")
    items = []
    for it in root.iter("item"):
        items.append({
            "applicants": [a.strip() for a in
                           (it.findtext("applicantName") or "").split("|") if a.strip()],
            "title": (it.findtext("inventionTitle") or "").strip(),
            "app_no": (it.findtext("applicationNumber") or "").strip(),
            "app_date": (it.findtext("applicationDate") or "").strip(),
            "ipc": (it.findtext("ipcNumber") or "").strip(),
            "status": (it.findtext("registerStatus") or "").strip(),
            # 초록은 기술 종합 보고서의 유일한 기술 근거다 — 사업보고서에는
            # 아직 양산 전인 기술이 실리지 않는다(실측: 삼성전자 원문 '전고체' 0회)
            "abstract": (it.findtext("astrtCont") or "").strip(),
        })
    return code, int(total_raw or 0), items


async def search(db: Session, word: str, pages: int = 1, rows: int = 100) -> dict:
    """키워드 1건 검색. 반환: {total, items, pages_fetched}

    한도를 먼저 확인하고, 모자라면 호출하지 않고 QuotaExceeded를 던진다.
    """
    if not settings.kipris_api_key:
        raise PatentSearchError("KIPRIS_API_KEY가 설정되지 않았습니다.")
    api_usage.check(db, PROVIDER, need=pages)

    loop = asyncio.get_running_loop()
    total, collected, fetched = 0, [], 0

    for page in range(1, pages + 1):
        params = {"word": word, "patent": "true", "utility": "true",
                  "pageNo": page, "numOfRows": rows}
        try:
            text = await loop.run_in_executor(None, partial(_get, "getWordSearch", params))
            code, total, items = _parse(text)
        except Exception as e:
            api_usage.record(db, PROVIDER, "getWordSearch", word, ok=False,
                             note=f"{type(e).__name__}: {e}")
            raise PatentSearchError(f"검색 실패: {e}") from e

        fetched += 1
        ok = code == "00"
        api_usage.record(db, PROVIDER, "getWordSearch", word, ok=ok,
                         note=None if ok else f"resultCode={code}")
        if not ok:
            raise PatentSearchError(f"KIPRIS 오류 resultCode={code} (word={word!r})")

        collected.extend(items)
        if len(items) < rows:
            break

    return {"word": word, "total": total, "items": collected, "pages_fetched": fetched}


def aggregate_applicants(results: list[dict]) -> tuple[Counter, dict[str, set[str]]]:
    """여러 검색 결과에서 출원인별 (특허 건수, 등장한 키워드 집합)을 낸다.

    같은 특허가 여러 키워드에 걸리면 중복 집계되므로 출원번호로 한 번 접는다.

    키워드 집합을 함께 주는 이유: 넓은 키워드 하나에서만 많이 나온 대기업과
    여러 키워드에 걸쳐 꾸준히 나온 기업은 성격이 다르다. 점수만으로는 안 갈린다.
    """
    seen: set[str] = set()
    counter: Counter = Counter()
    keywords: dict[str, set[str]] = {}
    for res in results:
        for item in res["items"]:
            if item["app_no"] and item["app_no"] in seen:
                continue
            if item["app_no"]:
                seen.add(item["app_no"])
            for name in item["applicants"]:
                counter[name] += 1
                keywords.setdefault(name, set()).add(res["word"])
    return counter, keywords


def match_companies(db: Session, applicants: Counter, limit: int = 30,
                    keywords: dict[str, set[str]] | None = None) -> dict:
    """출원인명 → 법인번호 → DART 기업.

    이름으로 매칭하지 않는다 — 특허는 한글 표기("주식회사 엘지화학"), DART는 영문
    표기("(주)LG화학")를 써서 문자열로는 안 붙는다. 법인번호가 유일한 조인 키다.

    결과를 셋으로 나눈다. 처방이 다르기 때문이다.
      tracked   이미 추적 중인 기업 — 바로 분석 가능
      available DART에는 있으나 미등록 — **등록만 하면 분석 대상**
      excluded  법인번호가 없거나 DART에 없음 — 개인·대학·연구소·외국기업
    """
    names = [n for n, _ in applicants.most_common(limit)]
    if not names:
        return {"tracked": [], "available": [], "excluded": []}

    # 출원인명 → 법인번호
    by_name: dict[str, str] = {}
    for r in db.query(ApplicantCorp).filter(ApplicantCorp.applicant_name.in_(names)).all():
        if r.jurir_no and r.applicant_name not in by_name:
            by_name[r.applicant_name] = r.jurir_no

    jurirs = set(by_name.values())
    tracked_by_jurir = {c.jurir_no: c for c in
                        db.query(Company).filter(Company.jurir_no.in_(jurirs)).all()} if jurirs else {}
    index_by_jurir = {d.jurir_no: d for d in
                      db.query(DartCorp).filter(DartCorp.jurir_no.in_(jurirs)).all()} if jurirs else {}

    tracked, available, excluded = [], [], []
    for name in names:
        cnt = applicants[name]
        jurir = by_name.get(name)
        base = {"applicant": name, "patents": cnt, "jurir_no": jurir,
                "keywords": sorted(keywords.get(name, [])) if keywords else []}

        if jurir and jurir in tracked_by_jurir:
            c = tracked_by_jurir[jurir]
            tracked.append({**base, "corp_code": c.corp_code,
                            "corp_name": c.corp_name, "company_id": c.id})
        elif jurir and jurir in index_by_jurir:
            d = index_by_jurir[jurir]
            available.append({**base, "corp_code": d.corp_code,
                              "corp_name": d.corp_name, "stock_code": d.stock_code})
        else:
            excluded.append({**base, "reason":
                             "DART 색인에 없음(비상장·미수집)" if jurir
                             else "법인번호 없음(개인·대학·연구소·외국)"})
    return {"tracked": tracked, "available": available, "excluded": excluded}
