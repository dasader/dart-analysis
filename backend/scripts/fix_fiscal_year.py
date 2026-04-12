"""기존 잘못 저장된 fiscal_year를 보고서명 기준으로 일괄 교정.

이전 버전(공시일 기준)으로 다운로드된 보고서들의 fiscal_year가
보고서명에서 파싱한 연도와 다를 경우 교정합니다.

실행:
    # 로컬
    cd backend && DATA_DIR=./data python -m scripts.fix_fiscal_year

    # Docker
    docker-compose exec backend python -m scripts.fix_fiscal_year
"""

from app.database import SessionLocal
from app.models import Report
from app.services.dart_client import extract_fiscal_year_from_name


def main() -> None:
    db = SessionLocal()
    try:
        reports = db.query(Report).all()
        print(f"전체 보고서 {len(reports)}건 검사 시작")

        updated = 0
        skipped = 0
        for r in reports:
            parsed = extract_fiscal_year_from_name(r.report_name)
            if parsed is None:
                print(f"  [스킵] id={r.id} 파싱 실패: {r.report_name!r}")
                skipped += 1
                continue
            if r.fiscal_year != parsed:
                print(
                    f"  [교정] id={r.id} {r.report_name!r}: "
                    f"{r.fiscal_year} -> {parsed}"
                )
                r.fiscal_year = parsed
                updated += 1

        if updated:
            db.commit()
        print(f"\n교정 완료: {updated}건 업데이트, {skipped}건 스킵, "
              f"{len(reports) - updated - skipped}건 변경 없음")
    finally:
        db.close()


if __name__ == "__main__":
    main()
