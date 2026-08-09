"""런타임 설정 — DB에 저장하고, 값이 없으면 .env 기본값을 쓴다.

.env는 앱 시작 시 한 번만 읽히므로 재시작 없이 바꿔야 하는 값만 여기서 다룬다.
"""
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppSetting

# 화면에서 켜고 끌 수 있는 값 — key: (라벨, 설명, .env 기본값)
TOGGLES: dict[str, tuple[str, str, bool]] = {
    "scheduler_auto_analyze": (
        "신규 보고서 자동 분석",
        "스케줄러가 수집한 신규 사업보고서를 자동으로 분석 요청합니다. "
        "끄면 관리자가 직접 분석 버튼을 눌러야 합니다.",
        settings.scheduler_auto_analyze,
    ),
    "section_extract_enabled": (
        "보고서 구역 추출",
        "분석에 필요한 구역만 추려 AI에 전달합니다(입력 약 87% 절감). "
        "끄면 보고서 전문이 전달되어 비용이 약 8배로 늘어납니다.",
        settings.section_extract_enabled,
    ),
}


def get(db: Session, key: str) -> bool:
    row = db.get(AppSetting, key)
    if row is None:
        return TOGGLES[key][2]
    return row.value == "true"


def set_value(db: Session, key: str, value: bool) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=str(value).lower()))
    else:
        row.value = str(value).lower()
    db.commit()


def list_all(db: Session) -> list[dict]:
    return [
        {"key": key, "label": label, "description": desc, "value": get(db, key)}
        for key, (label, desc, _) in TOGGLES.items()
    ]
