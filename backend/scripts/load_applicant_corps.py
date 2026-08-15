"""특허 출원인 법인번호 벌크(KIPRIS `CORP_APPLICANT.txt`)를 적재한다.

특허 출원인명은 한글 표기("주식회사 엘지화학"), DART는 영문 표기("(주)LG화학")를 쓰므로
이름으로는 매칭되지 않는다. 법인번호로 정확 조인하기 위한 테이블이다.

데이터는 KIPRIS Plus "출원인 법인 및 사업자 번호" 상품에서 ZIP으로 받는다(수수료 없음).
분기별 갱신이므로 **전량 교체**한다 — 증분 병합은 삭제된 출원인을 남겨 조인을 오염시킨다.

형식: UTF-8, `¶` 구분, 헤더 1줄
    출원인코드¶출원인명¶출원인영문명¶법인번호¶사업자번호

실행:
    # 로컬 (ZIP 또는 TXT 어느 쪽이든)
    cd backend && DATA_DIR=./data python -m scripts.load_applicant_corps ~/Corporate_20260720.zip

    # Docker
    docker-compose exec backend python -m scripts.load_applicant_corps /app/data/Corporate.zip
"""
import io
import re
import sys
import zipfile
from pathlib import Path

from app.database import Base, SessionLocal, engine
from app.migrate import run as run_migrations
from app.models import ApplicantCorp

SEP = "¶"
EXPECTED_HEADER = ["출원인코드", "출원인명", "출원인영문명", "법인번호", "사업자번호"]


def _open_text(path: Path) -> io.TextIOBase:
    """ZIP이면 안의 TXT를, 아니면 파일 자체를 텍스트로 연다."""
    if path.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(path)
        names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not names:
            raise SystemExit(f"ZIP 안에 .txt가 없습니다: {zf.namelist()}")
        return io.TextIOWrapper(zf.open(names[0]), encoding="utf-8")
    return path.open(encoding="utf-8")


def parse(path: Path):
    """(적재할 dict 목록, 건너뛴 줄 수)"""
    rows, skipped = [], 0
    with _open_text(path) as f:
        header = [c.strip() for c in f.readline().rstrip("\n").split(SEP)]
        if header[:5] != EXPECTED_HEADER:
            raise SystemExit(
                f"헤더가 예상과 다릅니다. 서식이 바뀌었을 수 있습니다.\n"
                f"  기대: {EXPECTED_HEADER}\n  실제: {header[:5]}"
            )
        seen = set()
        for line in f:
            parts = [p.strip() for p in line.rstrip("\n").split(SEP)]
            if len(parts) < 5 or not parts[0] or not parts[1]:
                skipped += 1
                continue
            code = parts[0]
            if code in seen:          # 같은 출원인코드가 두 번 나오면 첫 줄을 쓴다
                skipped += 1
                continue
            seen.add(code)
            jurir = re.sub(r"\D", "", parts[3])
            bizr = re.sub(r"\D", "", parts[4])
            rows.append({
                "applicant_code": code,
                "applicant_name": parts[1],
                "applicant_name_eng": parts[2] or None,
                "jurir_no": jurir if len(jurir) == 13 else None,
                "bizr_no": bizr if len(bizr) == 10 else None,
            })
    return rows, skipped


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1]).expanduser()
    if not path.exists():
        raise SystemExit(f"파일이 없습니다: {path}")

    print(f"파싱: {path}")
    rows, skipped = parse(path)
    with_jurir = sum(1 for r in rows if r["jurir_no"])
    print(f"  {len(rows):,}건 (건너뜀 {skipped:,})")
    print(f"  법인번호 보유 {with_jurir:,}건 ({100 * with_jurir / len(rows):.1f}%)")

    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    db = SessionLocal()
    try:
        before = db.query(ApplicantCorp).count()
        # 분기 갱신은 전량 교체 — 증분 병합은 삭제분을 남긴다
        db.query(ApplicantCorp).delete()
        db.bulk_insert_mappings(ApplicantCorp, rows)
        db.commit()
        after = db.query(ApplicantCorp).count()
        print(f"적재 완료: {before:,} → {after:,}건")
    finally:
        db.close()


if __name__ == "__main__":
    main()
