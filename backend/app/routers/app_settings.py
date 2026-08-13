from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.schemas import AppSettingResponse, AppSettingUpdate
from app.services import app_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=list[AppSettingResponse])
def list_settings(db: Session = Depends(get_db)):
    return app_settings.list_all(db)


@router.put("/{key}", response_model=AppSettingResponse, dependencies=[Depends(require_admin)])
def update_setting(key: str, body: AppSettingUpdate, db: Session = Depends(get_db)):
    if key not in app_settings.TOGGLES:
        raise HTTPException(404, f"설정을 찾을 수 없습니다: {key}")

    app_settings.set_value(db, key, body.value)
    label, description, _ = app_settings.TOGGLES[key]
    return AppSettingResponse(
        key=key, label=label, description=description, value=body.value
    )
