from pathlib import Path

from omega_v5.paths import REPO_ROOT, env_path


def test_env_path_prefers_explicit_override(monkeypatch):
    monkeypatch.setenv("OMEGA_ENV_PATH", "test.env")
    monkeypatch.delenv("OMEGA_ENV_PROFILE", raising=False)
    monkeypatch.delenv("OMEGA_RUNTIME_PROFILE", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    resolved = env_path()
    assert resolved == REPO_ROOT / "test.env"


def test_env_path_selects_test_profile(monkeypatch):
    monkeypatch.delenv("OMEGA_ENV_PATH", raising=False)
    monkeypatch.setenv("OMEGA_ENV_PROFILE", "test")
    monkeypatch.delenv("OMEGA_RUNTIME_PROFILE", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    resolved = env_path()
    assert resolved == REPO_ROOT / "test.env"


def test_env_path_selects_production_profile(monkeypatch):
    monkeypatch.delenv("OMEGA_ENV_PATH", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("OMEGA_RUNTIME_PROFILE", raising=False)
    monkeypatch.delenv("OMEGA_ENV_PROFILE", raising=False)

    resolved = env_path()
    assert resolved == REPO_ROOT / "production.env"


def test_env_path_defaults_to_dotenv_when_no_profile(monkeypatch):
    monkeypatch.delenv("OMEGA_ENV_PATH", raising=False)
    monkeypatch.delenv("OMEGA_ENV_PROFILE", raising=False)
    monkeypatch.delenv("OMEGA_RUNTIME_PROFILE", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    resolved = env_path()
    assert resolved == REPO_ROOT / ".env"
