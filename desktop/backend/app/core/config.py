from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    environment: Environment = Field(default="development", alias="LOCALSYNC_ENV")
    data_root: Path = Field(default=Path("data"), alias="LOCALSYNC_DATA_ROOT")
    database_url: str | None = Field(default=None, alias="LOCALSYNC_DATABASE_URL")
    log_level: str = Field(default="INFO", alias="LOCALSYNC_LOG_LEVEL")
    server_port: int = Field(default=8000, alias="LOCALSYNC_SERVER_PORT", ge=1, le=65535)
    discovery_enabled: bool = Field(default=True, alias="LOCALSYNC_DISCOVERY_ENABLED")
    discovery_instance_name: str | None = Field(
        default=None,
        alias="LOCALSYNC_DISCOVERY_INSTANCE_NAME",
    )
    max_upload_chunk_size: int = Field(
        default=16 * 1024 * 1024,
        alias="LOCALSYNC_MAX_UPLOAD_CHUNK_SIZE",
        gt=0,
    )

    model_config = SettingsConfigDict(extra="ignore")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of: {', '.join(sorted(allowed))}")
        return normalized

    @field_validator("discovery_instance_name")
    @classmethod
    def normalize_discovery_instance_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return stripped

    @model_validator(mode="after")
    def normalize_data_root(self) -> "Settings":
        self.data_root = self.data_root.expanduser()
        return self

    @computed_field
    @property
    def backup_root(self) -> Path:
        return self.data_root / "backups"

    @computed_field
    @property
    def temp_upload_root(self) -> Path:
        return self.data_root / ".localsync-temp"

    @computed_field
    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_root / 'localsync.db').as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
