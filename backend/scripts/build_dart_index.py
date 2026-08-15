"""DART 기업 색인 구축 — corpCode.xml 적재 + 법인번호 백필.

특허 출원인의 법인번호로 corp_code를 역인출하려면 색인이 있어야 한다.
corpCode.xml에는 법인번호가 없어 기업마다 company.json을 한 번씩 불러야 하는데,
전체 11만여 개를 다 부르면 과하므로 **상장사(약 4천)부터** 채운다.

중간에 끊겨도 이어서 돌릴 수 있다 — 이미 확인한 기업은 건너뛴다.

실행:
    cd backend
    DATA_DIR=../data python -m scripts.build_dart_index            # 목록 적재 + 상장사 백필
    DATA_DIR=../data python -m scripts.build_dart_index --list-only # 목록만
    DATA_DIR=../data python -m scripts.build_dart_index --limit 100 # 조금만 (시험)
"""
import argparse
import asyncio
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx

from app.config import settings
from app.database import SessionLocal, engine
from app.migrate import run as run_migrations
from app.models import DartCorp

DART_BASE = "https://opendart.fss.or.kr/api"


def load_corp_list(db) -> int:
    """corpCode.xml을 색인에 반영. 이미 있는 기업의 법인번호는 보존한다."""
    url = f"{DART_BASE}/corpCode.xml"
    resp = httpx.get(url, params={"crtfc_key": settings.opendart_api_key}, timeout=180)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        root = ET.fromstring(zf.read("CORPCODE.xml"))

    existing = {c.corp_code for c in db.query(DartCorp.corp_code).all()}
    added = 0
    for item in root.iter("list"):
        code = (item.findtext("corp_code") or "").strip()
        name = (item.findtext("corp_name") or "").strip()
        if not code or not name:
            continue
        if code in existing:
            continue
        db.add(DartCorp(
            corp_code=code, corp_name=name,
            stock_code=(item.findtext("stock_code") or "").strip() or None,
        ))
        added += 1
        if added % 5000 == 0:
            db.commit()
    db.commit()
    return added


async def fill_jurir(db, limit: int | None, listed_only: bool = True,
                     delay: float = 0.2) -> tuple[int, int]:
    """법인번호가 아직 없는 기업을 company.json으로 채운다. (채움, 없음)"""
    q = db.query(DartCorp).filter(DartCorp.jurir_checked_at.is_(None))
    if listed_only:
        q = q.filter(DartCorp.stock_code.isnot(None))
    targets = q.limit(limit).all() if limit else q.all()
    if not targets:
        return 0, 0

    print(f"  법인번호 미확인 {len(targets):,}개 조회 시작")
    filled = empty = errors = 0
    consecutive_errors = 0

    # DART 공식 제한은 **분당 1,000회**이고, 넘기면 API가 아니라 네트워크 레이어에서
    # IP를 차단한다 — 에러 JSON이 아니라 TCP가 끊기고 사이트 전체가 막힌다(공식 1시간).
    # 그래서 직렬 + 간격으로 간다. delay 0.2 = 300req/min (한도의 30%).
    async with httpx.AsyncClient(timeout=30) as client:
        for i, corp in enumerate(targets, 1):
            for attempt in range(3):
                try:
                    r = await client.get(f"{DART_BASE}/company.json", params={
                        "crtfc_key": settings.opendart_api_key, "corp_code": corp.corp_code})
                    data = r.json()
                    break
                except Exception as e:
                    if attempt == 2:
                        errors += 1
                        consecutive_errors += 1
                        if consecutive_errors == 1 or consecutive_errors % 50 == 0:
                            print(f"    ! {corp.corp_name}: {type(e).__name__} "
                                  f"(연속 {consecutive_errors}회)", flush=True)
                        data = None
                        break
                    await asyncio.sleep(2 ** attempt * 3)   # 3s, 6s
            if data is None:
                if consecutive_errors >= 30:
                    print(f"\n  연속 오류 {consecutive_errors}회 — 속도 제한으로 보고 중단합니다.")
                    print("  잠시 후 같은 명령을 다시 실행하면 이어서 채웁니다.")
                    break
                continue

            consecutive_errors = 0
            status = data.get("status")
            if status == "020":
                # 일일 20,000건 초과. HTTP 200으로 오므로 상태코드만 보면 놓친다.
                print(f"\n  일일 한도 초과(020) — 내일 이어서 실행하세요.")
                break
            corp.jurir_checked_at = datetime.utcnow()
            if status != "000":
                empty += 1
            else:
                digits = re.sub(r"\D", "", data.get("jurir_no") or "")
                if len(digits) == 13:
                    corp.jurir_no = digits
                    filled += 1
                else:
                    empty += 1

            await asyncio.sleep(delay)
            if i % 100 == 0:
                db.commit()
                print(f"    {i:,}/{len(targets):,} "
                      f"(법인번호 {filled:,} / 없음 {empty:,} / 오류 {errors:,})", flush=True)
    db.commit()
    return filled, empty


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-only", action="store_true", help="corpCode.xml 적재만")
    ap.add_argument("--limit", type=int, help="법인번호 조회 건수 상한")
    ap.add_argument("--all", action="store_true", help="비상장 포함 전체 (호출 많음)")
    ap.add_argument("--delay", type=float, default=0.2,
                    help="호출 간격(초). 0.2 = 300req/min으로 공식 한도(분당 1,000)의 30%")
    args = ap.parse_args()

    run_migrations(engine)
    db = SessionLocal()
    try:
        print("corpCode.xml 적재...")
        added = load_corp_list(db)
        total = db.query(DartCorp).count()
        listed = db.query(DartCorp).filter(DartCorp.stock_code.isnot(None)).count()
        have = db.query(DartCorp).filter(DartCorp.jurir_no.isnot(None)).count()
        print(f"  신규 {added:,} / 전체 {total:,} (상장 {listed:,}) / 법인번호 보유 {have:,}")

        if args.list_only:
            return

        filled, empty = await fill_jurir(db, args.limit, listed_only=not args.all,
                                         delay=args.delay)
        have = db.query(DartCorp).filter(DartCorp.jurir_no.isnot(None)).count()
        print(f"\n완료: 이번에 {filled:,}개 채움 (법인번호 없음 {empty:,}) / 누적 보유 {have:,}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
