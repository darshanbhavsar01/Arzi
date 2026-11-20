"""Runtime settings.

Every environment variable the service reads is declared here, so this module doubles as the
configuration reference. Model IDs are deliberately settings, never literals in code: the
available Gemini versions change faster than the codebase does.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
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
    """``{"<model id>": {"input_inr_per_1m": 7.5, "output_inr_per_1m": 30}}``; verify the
    numbers against the current Vertex AI pricing page before a live run."""
    use_dlp: bool = False
    use_docai: bool = False
    pseudonym_salt_secret: str | None = None
    pseudonym_salt: SecretStr = SecretStr("arzi-local-development-salt")
    """HMAC key for stable pseudonyms. Local default only; cloud must set a real secret."""

    replay_dir: Path = Path(__file__).resolve().parents[3] / "demo_cases"
    """Recorded LLM responses are read from ``<replay_dir>/*/llm_cache/``."""
    llm_record_dir: Path | None = None
    """When set in live mode, every response is also written here as a replay recording."""
    llm_timeout_s: float = Field(default=90.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_thinking_budget: int = Field(default=0, ge=-1)
    """Thinking tokens for extraction (0 = off). Transcription needs little reasoning."""
    extraction_concurrency: int = Field(default=3, ge=1, le=10)

    max_upload_mb: int = Field(default=20, ge=1, le=32)
    max_pages: int = Field(default=30, ge=1)
    demo_hospital_id: str = "sanjeevani-ahd"
    sse_heartbeat_s: float = Field(default=15.0, gt=0)

    static_dir: Path | None = None
    """Built SPA directory served by the API container; unset in local dev (Vite serves it)."""

    readiness_timeout_s: float = Field(default=3.0, gt=0)
    build_sha: str = "dev"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings; cached because the environment does not change at runtime."""
    return Settings()
