import os

from career_os.department_agents import provider_order
from career_os.openhands_coding_agent import OpenHandsConfig, is_available


def test_openhands_is_not_required_by_default(monkeypatch):
    monkeypatch.delenv("OPENHANDS_ENABLED", raising=False)
    monkeypatch.delenv("OPENHANDS_API_KEY", raising=False)
    assert OpenHandsConfig.from_env().enabled is False
    assert is_available() is False


def test_openhands_is_engineering_only(monkeypatch):
    monkeypatch.setenv("OPENHANDS_ENABLED", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("AI_PROVIDER", "pool")
    assert provider_order("engineering")[0] == "openhands"
    assert "openhands" not in provider_order("fit")


def test_openhands_configuration_uses_deepseek_as_default_backend(monkeypatch):
    monkeypatch.setenv("OPENHANDS_ENABLED", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    config = OpenHandsConfig.from_env()
    assert config.api_key == "test-key"
    assert config.model == "deepseek/deepseek-chat"
    assert config.base_url == "https://api.deepseek.com"
    assert config.max_steps >= 1
