from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./tracehunt.db"
    redis_url: str = ""
    demo_mode: bool = True
    seed_demo: bool = True
    api_key: str = ""
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    monitor_allow_private_networks: bool = False
    run_worker: bool = False
    alert_webhook_url: str = ""
    error_threshold: int = Field(default=5, ge=2, le=10000)
    error_window_seconds: int = Field(default=300, ge=30, le=3600)
    incident_cooldown_seconds: int = Field(default=900, ge=30, le=86400)
    max_body_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    retention_days: int = Field(default=30, ge=1, le=3650)

    @model_validator(mode="after")
    def secure_production(self):
        if not self.demo_mode and len(self.api_key) < 24:
            raise ValueError("API_KEY must contain at least 24 characters when DEMO_MODE=false")
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
