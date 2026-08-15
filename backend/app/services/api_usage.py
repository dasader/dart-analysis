"""외부 API 호출량 계측.

KIPRIS 무료 한도가 **월 1,000회**라 페이지네이션 몇 번이면 금방 닳는다.
남은 횟수를 모르는 채로 돌리면 어느 순간 조용히 실패하므로 직접 센다.

KIPRIS 포털이 보여주는 실제 사용량과 다를 수 있다(실패 호출 집계 여부가 불명확하다).
여기 숫자는 **우리가 보낸 요청 수**이고, 한도 관리는 보수적으로 이 값을 쓴다.
"""
import logging
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import ApiCall

logger = logging.getLogger(__name__)

# 제공자별 월 한도. 0이면 한도 없음(계측만)
MONTHLY_LIMIT = {"kipris": 1000}


def _period(when: datetime | None = None) -> str:
    return (when or datetime.utcnow()).strftime("%Y-%m")


def record(db: Session, provider: str, operation: str, query: str | None,
           ok: bool, note: str | None = None) -> None:
    """호출 1건 기록. 실패도 센다 — 한도는 성공 여부와 무관할 수 있다."""
    db.add(ApiCall(
        provider=provider, operation=operation,
        query=(query or "")[:200], ok=ok, note=(note or "")[:200] or None,
        period=_period(),
    ))
    db.commit()


def usage(db: Session, provider: str, period: str | None = None) -> dict:
    """이번 달 사용량과 잔여."""
    p = period or _period()
    total = db.query(func.count(ApiCall.id)).filter(
        ApiCall.provider == provider, ApiCall.period == p).scalar() or 0
    failed = db.query(func.count(ApiCall.id)).filter(
        ApiCall.provider == provider, ApiCall.period == p,
        ApiCall.ok.is_(False)).scalar() or 0
    limit = MONTHLY_LIMIT.get(provider, 0)
    return {
        "provider": provider, "period": p,
        "used": total, "failed": failed,
        "limit": limit or None,
        "remaining": max(0, limit - total) if limit else None,
    }


class QuotaExceeded(RuntimeError):
    """한도를 넘겨 호출을 막았다."""


def check(db: Session, provider: str, need: int = 1) -> None:
    """호출 전 잔여 확인. 모자라면 아예 보내지 않는다."""
    u = usage(db, provider)
    if u["remaining"] is None:
        return
    if u["remaining"] < need:
        raise QuotaExceeded(
            f"{provider} 월 한도 초과: {u['used']}/{u['limit']}회 사용, "
            f"{need}회 필요하나 {u['remaining']}회 남음 ({u['period']})"
        )
