import pytest

from arzi.config import AuthMode, Environment, LlmMode, Settings, get_settings


def test_defaults_are_safe_for_local_development(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("GOOGLE_CLOUD_PROJECT", "ARZI_LLM_MODE", "ARZI_ENV", "ARZI_AUTH_MODE"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.env is Environment.LOCAL
    assert settings.llm_mode is LlmMode.REPLAY
    assert settings.auth_mode is AuthMode.DEMO
    assert settings.gcp_region == "asia-south1"
    assert settings.daily_budget_inr == 150
    assert settings.model_flash is None


def test_reads_prefixed_and_standard_google_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "arzi-demo")
    monkeypatch.setenv("ARZI_LLM_MODE", "live")
    monkeypatch.setenv("ARZI_MODEL_FLASH", "gemini-x-flash")
    monkeypatch.setenv("ARZI_DAILY_BUDGET_INR", "90")

    settings = Settings(_env_file=None)

    assert settings.google_cloud_project == "arzi-demo"
    assert settings.llm_mode is LlmMode.LIVE
    assert settings.model_flash == "gemini-x-flash"
    assert settings.daily_budget_inr == 90


def test_rejects_unknown_llm_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARZI_LLM_MODE", "yolo")

    with pytest.raises(ValueError, match="llm_mode"):
        Settings(_env_file=None)


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()

    assert get_settings() is get_settings()
