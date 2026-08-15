"""기존 기업의 법인등록번호(jurir_no)를 채운다.

corpCode.xml에는 법인번호가 없어 기업마다 company.json을 한 번씩 호출해야 한다.
신규 등록은 라우터에서 자동으로 채우므로, 이 스크립트는 **이미 등록된 기업**용이다.

실행:
    cd backend && DATA_DIR=./data python -m scripts.backfill_jurir_no
    docker-compose exec backend python -m scripts.backfill_jurir_no
"""
import asyncio

from app.database import SessionLocal, engine
from app.migrate import run as run_migrations
from app.models import Company
from app.services.dart_client import aclose_http, fetch_jurir_no


async def main() -> None:
    # 앱을 거치지 않고 실행되므로 컬럼 추가를 여기서도 보장한다
    run_migrations(engine)

    db = SessionLocal()
    try:
        targets = db.query(Company).filter(Company.jurir_no.is_(None)).all()
        if not targets:
            print("채울 기업이 없습니다.")
            return

        print(f"대상 {len(targets)}개")
        filled = failed = 0
        for company in targets:
            try:
                jurir = await fetch_jurir_no(company.corp_code)
            except Exception as e:
                print(f"  {company.corp_name}: 조회 실패 — {type(e).__name__}")
                failed += 1
                continue
            if jurir:
                company.jurir_no = jurir
                filled += 1
                print(f"  {company.corp_name}: {jurir}")
            else:
                failed += 1
                print(f"  {company.corp_name}: 법인번호 없음")
        db.commit()
        print(f"\n완료: 채움 {filled} / 실패·없음 {failed}")
    finally:
        db.close()
        await aclose_http()


if __name__ == "__main__":
    asyncio.run(main())
