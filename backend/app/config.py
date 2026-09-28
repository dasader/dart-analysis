from functools import cache
from pathlib import Path

from google import genai
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    opendart_api_key: str
    gemini_api_key: str
    # KIPRIS 특허검색 (data.go.kr 발급 ServiceKey)
    kipris_api_key: str = ""
    # 포트는 여기 없다 — docker-compose가 .env에서 직접 읽는다(${BACKEND_PORT:-8016}).
    # 파이썬 쪽에 두면 실제와 어긋나도 아무도 모른다(frontend_port가 8097로 남아 있었다).
    scheduler_interval_hours: int = 24
    # batch 작업 상태 확인 주기 (실측 turnaround 8.3분)
    batch_poll_interval_secs: int = 60
    # 신규 보고서 수집 후 분석까지 자동 요청할지. 기본 off — 의도치 않은 비용 방지
    scheduler_auto_analyze: bool = False
    # 보고서에서 분석에 쓰이는 구역만 추려 LLM에 보낼지 (입력 ~85% 절감)
    section_extract_enabled: bool = True
    # 기술 스캔 주기(일). 특허는 출원 후 18개월 뒤 공개되므로 월 1회면 충분하다
    tech_scan_interval_days: int = 30
    tech_scan_enabled: bool = True
    # 관리자 키 — 비어 있으면 인증 비활성화(모든 관리 요청 통과)
    admin_key: str = ""
    data_dir: Path = Path("/app/data")

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'db.sqlite3'}"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    model_config = {
        "env_file": [".env", "../.env"],
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()


@cache
def gemini() -> genai.Client:
    """Gemini 클라이언트. 처음 부를 때 한 번만 만든다 — import 시점에 만들면 키 없는 환경에서 죽는다."""
    return genai.Client(api_key=settings.gemini_api_key)
