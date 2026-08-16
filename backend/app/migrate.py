"""누락된 컬럼을 채우는 최소 마이그레이션.

`Base.metadata.create_all`은 **없는 테이블만** 만든다. 기존 테이블에 컬럼이 추가되면
조용히 무시하고, 나중에 그 컬럼을 읽는 순간 OperationalError로 터진다.
이 프로젝트에는 Alembic이 없으므로 시작 시 한 번 훑어 채운다.

컬럼 추가만 다룬다. 타입 변경·삭제·데이터 이관이 필요해지면 그때는 Alembic을 들여야 한다.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# (테이블, 컬럼, DDL 타입) — 이미 있으면 건너뛴다
ADDITIONS: list[tuple[str, str, str]] = [
    ("companies", "jurir_no", "VARCHAR"),
    ("technologies", "report_md", "TEXT"),
    ("technologies", "report_generated_at", "DATETIME"),
    ("technologies", "report_basis", "VARCHAR"),
    ("technologies", "keyword_stats", "TEXT"),
]


def run(engine: Engine) -> None:
    """신규 테이블 생성 + 누락 컬럼 추가. 앱과 스크립트 양쪽에서 부른다."""
    from app.database import Base
    import app.models  # noqa: F401  — 모델을 메타데이터에 등록시킨다

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, column, ddl_type in ADDITIONS:
            if table not in existing_tables:
                continue  # create_all이 새로 만들 테이블 — 이미 컬럼이 들어 있다
            cols = {c["name"] for c in inspector.get_columns(table)}
            if column in cols:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
            logger.info("마이그레이션: %s.%s 추가", table, column)


if __name__ == "__main__":
    # `make migrate` / `python -m app.migrate` — 앱을 띄우지 않고 스키마만 맞춘다.
    # 앱 시작 시에도 같은 run()이 돌므로 평소에는 부를 일이 없다. 배포 순서상
    # 컨테이너를 올리기 전에 스키마를 먼저 맞춰야 할 때를 위한 진입점이다.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from app.database import engine

    run(engine)
    print(f"스키마 확인 완료 — 컬럼 점검 {len(ADDITIONS)}건")
