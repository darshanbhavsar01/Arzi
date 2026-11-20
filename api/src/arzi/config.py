"""Runtime settings.

Every environment variable the service reads is declared here, so this module doubles as the
configuration reference. Model IDs are deliberately settings, never literals in code: the
available Gemini versions change faster than the codebase does.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


class LlmMode(StrEnum):
    LIVE = "live"
    REPLAY = "replay"
    FAKE = "fake"


class AuthMode(StrEnum):
    DEMO = "demo"
    FIREBASE = "firebase"


class Settings(BaseSettings):
    """Typed view of the process environment (prefix ``ARZI_`` unless noted)."""

    model_config = SettingsConfigDict(env_prefix="ARZI_", frozen=True, extra="ignore")

    env: Environment = Environment.LOCAL
    google_cloud_project: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLOUD_PROJECT", "ARZI_GOOGLE_CLOUD_PROJECT"),
    )
    gcp_region: str = "asia-south1"
    vertex_location: str = "asia-south1"
    firestore_database: str = "(default)"
    bucket: str | None = None

    model_flash: str | None = None
    model_pro: str | None = None
    model_tts: str | None = None
    model_live: str | None = None

    llm_mode: LlmMode = LlmMode.REPLAY
    auth_mode: AuthMode = AuthMode.DEMO

    daily_budget_inr: int = Field(default=150, ge=0)
    price_table_json: str | None = None
    use_dlp: bool = False
    use_docai: bool = False
    pseudonym_salt_secret: str | None = None

    static_dir: Path | None = None
    """Built SPA directory served by the API container; unset in local dev (Vite serves it)."""

    readiness_timeout_s: float = Field(default=3.0, gt=0)
    build_sha: str = "dev"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings; cached because the environment does not change at runtime."""
    return Settings()
