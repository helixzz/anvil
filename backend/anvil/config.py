from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ANVIL_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://anvil:anvil@db:5432/anvil"
    bearer_token: str = Field(default="dev-token", min_length=8)
    runner_socket: Path = Path("/run/anvil/runner.sock")
    data_dir: Path = Path("/var/lib/anvil")
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: list[str] = Field(default_factory=list)
    log_level: str = "info"
    simulation_mode: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
