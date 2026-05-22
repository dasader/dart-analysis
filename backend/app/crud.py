from typing import Any, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import Base

T = TypeVar("T", bound=Base)


def get_or_404(db: Session, model: type[T], obj_id: int, detail: str) -> T:
    """기본키로 레코드를 조회하고, 없으면 404를 던진다."""
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, detail)
    return obj


def group_agg(db: Session, agg: Any, group_col: Any, ids: list[int], *filters: Any) -> dict:
    """group_col 별 집계(agg)를 단일 group_by 쿼리로 {그룹값: 집계값} dict로 반환.

    N개 그룹의 집계를 N+1 없이 1쿼리로 수행하기 위한 공용 헬퍼.
    """
    if not ids:
        return {}
    rows = (
        db.query(group_col, agg)
        .filter(group_col.in_(ids), *filters)
        .group_by(group_col)
        .all()
    )
    return dict(rows)


def apply_update(obj: Any, body: Any) -> None:
    """Pydantic 모델에서 명시적으로 설정된(set) 필드만 obj에 반영하는 부분 업데이트."""
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, val)
