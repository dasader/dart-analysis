from fastapi import APIRouter, Depends

from app.dependencies import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/verify", dependencies=[Depends(require_admin)])
def verify_admin():
    """관리자 키 검증용. require_admin 통과 시 200."""
    return {"ok": True}
