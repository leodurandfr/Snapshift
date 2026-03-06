from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://screenloop:screenloop@localhost:5433/screenloop"

    # API Security
    api_token: str = "change-me-to-a-random-secret-token"

    # Storage
    storage_path: Path = Path("./storage")

    # Capture defaults
    capture_timeout: int = 60
    default_retention_days: int = 90

    # Browsertrix (WACZ archive)
    browsertrix_image: str = "webrecorder/browsertrix-crawler:latest"
    browsertrix_time_limit: int = 120
    browsertrix_size_limit_mb: int = 200
    browsertrix_crawl_dir: str = "/tmp/browsertrix-crawls"
    browsertrix_host_crawl_dir: str = ""

    # Server
    backend_port: int = 8000


settings = Settings()
