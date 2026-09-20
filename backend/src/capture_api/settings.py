import hashlib
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

type ChaosProfile = Literal["calm", "flaky", "storm", "degraded-pcap", "expiring-tokens"]
type LogLevel = Literal["critical", "error", "warning", "info", "debug", "trace"]

CHAOS_PROFILES: tuple[ChaosProfile, ...] = (
    "calm",
    "flaky",
    "storm",
    "degraded-pcap",
    "expiring-tokens",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CAP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    seed: str = Field(default="demo", min_length=1, max_length=64)
    epoch: AwareDatetime = datetime(2025, 10, 27, 12, 0, 0, tzinfo=UTC)
    host: str = "127.0.0.1"
    port: int = Field(default=8700, ge=1, le=65535)
    access_ttl_s: int = Field(default=90, ge=1)
    refresh_idle_s: int = Field(default=1800, ge=1)
    refresh_max_s: int = Field(default=28800, ge=1)
    chaos: ChaosProfile = "calm"
    admin_token: str = Field(default="lf-dev-admin", min_length=1)
    allowed_origins: Annotated[tuple[str, ...], NoDecode] = ("http://localhost:3000",)
    full_history: bool = False
    teammate_bot: bool = True
    cursor_secret: str = ""
    log_level: LogLevel = "info"

    @field_validator("epoch", mode="after")
    @classmethod
    def _epoch_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC).replace(microsecond=value.microsecond // 1000 * 1000)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(part.strip().rstrip("/") for part in value.split(",") if part.strip())
        return value

    @model_validator(mode="after")
    def _derive_cursor_secret(self) -> "Settings":
        if not self.cursor_secret:
            derived = hashlib.blake2b(
                f"capture_api-cursor|{self.seed}".encode(), digest_size=32
            ).hexdigest()
            object.__setattr__(self, "cursor_secret", derived)
        return self

    @property
    def epoch_ms(self) -> int:
        return int(self.epoch.timestamp() * 1000)

    @property
    def cursor_key(self) -> bytes:
        return self.cursor_secret.encode()

    @property
    def teammate_bot_enabled(self) -> bool:
        return self.teammate_bot and not self.full_history


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
