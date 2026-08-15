"""특허 출원인 법인번호 벌크(KIPRIS `CORP_APPLICANT.txt`)를 적재한다.

특허 출원인명은 한글 표기("주식회사 엘지화학"), DART는 영문 표기("(주)LG화학")를 쓰므로
이름으로는 매칭되지 않는다. 법인번호로 정확 조인하기 위한 테이블이다.

데이터는 KIPRIS Plus "출원인 법인 및 사업자 번호" 상품에서 ZIP으로 받는다(수수료 없음).
분기별 갱신이므로 **전량 교체**한다 — 증분 병합은 삭제된 출원인을 남겨 조인을 오염시킨다.

적재 로직은 `app.services.backup`에 있다 — 설정 화면의 업로드 기능과 같은 코드를 쓴다.

실행:
    # 로컬 (ZIP 또는 TXT 어느 쪽이든)
    cd backend && DATA_DIR=./data python -m scripts.load_applicant_corps ~/Corporate_20260720.zip

    # Docker
    docker-compose exec backend python -m scripts.load_applicant_corps /app/data/Corporate.zip
"""
import sys
from pathlib import Path

from app.database import engine
from app.migrate import run as run_migrations
from app.services.backup import BackupError, load_applicant_corps


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1]).expanduser()
    if not path.exists():
        raise SystemExit(f"파일이 없습니다: {path}")

    run_migrations(engine)
    print(f"파싱·적재: {path}")
    try:
        r = load_applicant_corps(path)
    except BackupError as e:
        raise SystemExit(str(e)) from e

    print(f"  건너뜀 {r['skipped']:,}줄")
    print(f"  법인번호 보유 {r['with_jurir']:,}건 "
          f"({100 * r['with_jurir'] / r['after']:.1f}%)")
    print(f"적재 완료: {r['before']:,} → {r['after']:,}건")


if __name__ == "__main__":
    main()
