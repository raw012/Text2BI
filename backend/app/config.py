from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Text2BI API"
    database_url: str = "sqlite:///./text2bi.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    frontend_origin: str = "http://localhost:5173"
    max_upload_mb: int = 25
    upload_dir: Path = Path("uploads")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
