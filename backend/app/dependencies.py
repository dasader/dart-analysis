from fastapi import Header, HTTPException

from app.config import settings


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """관리자 인증. admin_key 미설정 시 통과(인증 비활성화), 설정 시 헤더 일치 필요."""
    if not settings.admin_key:
        return
    if x_admin_key != settings.admin_key:
        raise HTTPException(status_code=401, detail="관리자 인증이 필요합니다.")
