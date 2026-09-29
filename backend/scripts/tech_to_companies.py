"""프로토타입 — 기술 설명에서 분석까지 한 번에.

  기술 설명 → 검색 키워드(LLM) → 특허 검색 → 출원인 집계
           → 법인번호로 DART 기업 조인 → [--onboard] 등록·보고서 수집·분석 큐 투입

`--onboard` 없이 돌리면 **조회만** 한다(비용 없음). 붙이면 실제로 기업을 등록하고
보고서를 받고 분석을 건다 — 보고서 1건당 약 $0.048이므로 --max로 상한을 둔다.

실행:
    cd backend
    DATA_DIR=../data python -m scripts.tech_to_companies "전고체 배터리용 황화물계 고체전해질"
    DATA_DIR=../data python -m scripts.tech_to_companies "..." --onboard --max 3
    DATA_DIR=../data python -m scripts.tech_to_companies --usage
"""
import argparse
import asyncio

from app.database import SessionLocal, engine
from app.migrate import run as run_migrations
from app.services import api_usage, keyword_extract, patent_search, tech_pipeline
from app.services.dart_client import aclose_http


def show_usage(db) -> None:
    u = api_usage.usage(db, "kipris")
    print(f"KIPRIS {u['period']}: {u['used']}회 사용 (실패 {u['failed']}) "
          f"/ 한도 {u['limit'] or '-'} / 잔여 {u['remaining'] if u['remaining'] is not None else '-'}")


async def run(args) -> None:
    run_migrations(engine)
    db = SessionLocal()
    try:
        show_usage(db)

        keywords = args.keywords
        if not keywords:
            print(f"\n■ 기술 설명 ({len(args.description)}자)\n  {args.description}")
            keywords = await keyword_extract.extract(args.description)
            print(f"\n■ 검색 키워드 {len(keywords)}개 (LLM 추출)")
        else:
            print(f"\n■ 검색 키워드 {len(keywords)}개 (직접 지정)")
        for k in keywords:
            print(f"  - {k} ({len(k)}자)")

        print(f"\n■ 특허 검색 (키워드당 {args.pages}페이지)")
        results = []
        for k in keywords:
            try:
                res = await patent_search.search(db, k, pages=args.pages)
            except api_usage.QuotaExceeded as e:
                print(f"  {k:<24} 중단 — {e}")
                break
            except patent_search.PatentSearchError as e:
                print(f"  {k:<24} 실패 — {e}")
                continue
            results.append(res)
            broad = " ← 넓음(기술 특이성 희석)" if patent_search.is_broad(res["total"]) else ""
            print(f"  {k:<24} 총 {res['total']:>7,}건 / 수집 {len(res['items']):>4}건{broad}")

        if not results:
            print("\n검색 결과가 없어 중단합니다.")
            return

        results, _ = patent_search.core_only(results)
        applicants, kw_hits, patents = patent_search.aggregate_applicants(results)
        m = patent_search.match_companies(db, applicants, kw_hits, patents, limit=args.top)
        n_broad = sum(1 for r in results if patent_search.is_broad(r["total"]))
        if n_broad:
            print(f"\n  ※ 넓은 키워드 {n_broad}개 포함. 아래 '키워드' 열이 1이면 "
                  f"그 키워드에서만 나온 것이라 기술 연관성이 약할 수 있습니다.")
        print(f"\n■ 출원인 {len(applicants)}명 → "
              f"추적중 {len(m['tracked'])} / 등록가능 {len(m['available'])} / 제외 {len(m['excluded'])}")

        if m["tracked"]:
            print("\n  [추적 중] 바로 분석 가능")
            for x in m["tracked"]:
                print(f"    {x['corp_name'][:18]:<20} {x['patents']:>3}건  "
                      f"키워드 {len(x['keywords'])}개  {x['corp_code']}")

        if m["available"]:
            print("\n  [등록 가능] DART에 있으나 아직 추적하지 않음")
            for x in m["available"]:
                print(f"    {x['corp_name'][:18]:<20} {x['patents']:>3}건  "
                      f"키워드 {len(x['keywords'])}개  {x['applicant'][:20]}")

        if m["excluded"]:
            print(f"\n  [제외] {len(m['excluded'])}명")
            for x in m["excluded"][:8]:
                print(f"    {x['applicant'][:28]:<30} {x['patents']:>3}건  {x['reason']}")
            if len(m["excluded"]) > 8:
                print(f"    ... 외 {len(m['excluded']) - 8}명")

        if not args.onboard:
            print(f"\n(조회만 했습니다. --onboard --max N 을 붙이면 상위 N개를 "
                  f"등록·수집·분석합니다. 보고서 1건당 약 $0.048)")
            print()
            show_usage(db)
            return

        print(f"\n■ 온보딩 (상위 {args.max}개)")
        cands = await tech_pipeline.order_candidates(
            (args.description or " ".join(keywords))[:40], args.description or ", ".join(keywords),
            m["available"], patents, args.max)
        out = await tech_pipeline.onboard(db, cands, args.max, args.year)
        for r in out["registered"]:
            why = f"  [{r['role']}] {r['reason'] or ''}" if r.get("role") else ""
            print(f"  등록: {r['corp_name']}{why}")
        for r in out["reports"]:
            print(f"  보고서: {r['company']} {r['fiscal_year']}년 (id={r['report_id']})")
        for f in out["failed"]:
            print(f"  실패: {f.get('corp_name', f['applicant'])} — {f['reason']}")
        print(f"\n  분석 큐 투입: 보고서 {out['queued_reports']}건")
        print("  (batch는 수 분 걸립니다. /settings/batches 에서 진행 상황 확인)")

        print()
        show_usage(db)
    finally:
        db.close()
        await aclose_http()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("description", nargs="?", help="기술 설명문")
    ap.add_argument("-k", "--keywords", nargs="+", help="LLM 추출을 건너뛰고 직접 지정")
    ap.add_argument("--pages", type=int, default=1, help="키워드당 페이지 (100건/페이지)")
    ap.add_argument("--top", type=int, default=30, help="상위 몇 명의 출원인을 매칭할지")
    ap.add_argument("--onboard", action="store_true", help="등록·보고서 수집·분석까지 실행")
    ap.add_argument("--max", type=int, default=3, help="온보딩할 기업 수 상한")
    ap.add_argument("--year", type=int, help="수집할 사업연도 (기본: 작년)")
    ap.add_argument("--usage", action="store_true", help="호출량만 확인")
    args = ap.parse_args()

    if args.usage:
        run_migrations(engine)
        db = SessionLocal()
        try:
            show_usage(db)
        finally:
            db.close()
        return

    if not args.description and not args.keywords:
        ap.error("기술 설명문 또는 -k 키워드가 필요합니다")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
