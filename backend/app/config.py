from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    opendart_api_key: str
    gemini_api_key: str
    backend_port: int = 8016
    frontend_port: int = 8097
    scheduler_interval_hours: int = 24
    # batch 작업 상태 확인 주기 (실측 turnaround 8.3분)
    batch_poll_interval_secs: int = 60
    # 신규 보고서 수집 후 분석까지 자동 요청할지. 기본 off — 의도치 않은 비용 방지
    scheduler_auto_analyze: bool = False
    # 보고서에서 분석에 쓰이는 구역만 추려 LLM에 보낼지 (입력 ~85% 절감)
    section_extract_enabled: bool = True
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
