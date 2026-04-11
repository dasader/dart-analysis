from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    opendart_api_key: str
    gemini_api_key: str
    backend_port: int = 8016
    frontend_port: int = 8097
    scheduler_interval_hours: int = 24
    # Gemini 2.5 flash preview TPM 한도: 2M tokens/min
    # 요청당 ~850K 토큰 기준 → 분당 2건 → 30초 간격
    analysis_interval_secs: int = 30
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
