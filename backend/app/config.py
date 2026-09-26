from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Text2BI API"
    database_url: str = "sqlite:///./text2bi.db"
    db_host: str | None = None
    db_name: str = "text2bi"
    db_username: str = "text2bi"
    db_password: str | None = None
    qwen_api_key: str | None = None
    qwen_model: str = "qwen-plus"
    qwen_vl_model: str = "qwen-vl-max"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    frontend_origin: str = "http://localhost:5173"
    backend_public_url: str = "http://localhost:8000"
    max_upload_mb: int = 25
    max_workflow_iterations: int = 5
    upload_dir: Path = Path("uploads")
    upload_bucket: str | None = None
    api_root_path: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
