from typing import TypeVar

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
