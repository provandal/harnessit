"""Tests for harnessit.config — credential file parsing + precedence."""

from __future__ import annotations

from pathlib import Path

import pytest

from harnessit.config import (
    DEFAULT_MODEL,
    ConfigError,
    Settings,
    _read_kv_credentials,
    _read_raw_credential,
    find_workspace_root,
    load_settings,
)


@pytest.fixture
def isolated_env(monkeypatch):
    """Strip credential env vars so file-based loading is exercised."""
    for key in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_HOST",
    ):
        monkeypatch.delenv(key, raising=False)


def _write_creds(root: Path, anthropic: str | None, langfuse_kv: dict[str, str] | None) -> None:
    if anthropic is not None:
        (root / ".anthropic-credentials").write_text(anthropic + "\n", encoding="utf-8")
    if langfuse_kv is not None:
        lines = [f'{k}="{v}"' for k, v in langfuse_kv.items()]
        (root / ".langfuse-credentials").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_read_raw_credential_strips_whitespace(tmp_path):
    creds = tmp_path / ".anthropic-credentials"
    creds.write_text("  sk-ant-xyz  \n", encoding="utf-8")
    assert _read_raw_credential(creds) == "sk-ant-xyz"


def test_read_raw_credential_missing_returns_none(tmp_path):
    assert _read_raw_credential(tmp_path / "nope") is None


def test_read_raw_credential_empty_returns_none(tmp_path):
    creds = tmp_path / ".anthropic-credentials"
    creds.write_text("   \n", encoding="utf-8")
    assert _read_raw_credential(creds) is None


def test_read_kv_credentials_quoted_and_unquoted(tmp_path):
    creds = tmp_path / ".langfuse-credentials"
    creds.write_text(
        '# a comment\n'
        'LANGFUSE_SECRET_KEY="sk-lf-secret"\n'
        'LANGFUSE_PUBLIC_KEY=pk-lf-public\n'
        '\n'
        'LANGFUSE_BASE_URL="https://us.cloud.langfuse.com"\n',
        encoding="utf-8",
    )
    parsed = _read_kv_credentials(creds)
    assert parsed == {
        "LANGFUSE_SECRET_KEY": "sk-lf-secret",
        "LANGFUSE_PUBLIC_KEY": "pk-lf-public",
        "LANGFUSE_BASE_URL": "https://us.cloud.langfuse.com",
    }


def test_read_kv_credentials_missing_returns_empty_dict(tmp_path):
    assert _read_kv_credentials(tmp_path / "nope") == {}


def test_find_workspace_root_walks_up(tmp_path):
    workspace = tmp_path / "ws"
    nested = workspace / "harnessit" / "src"
    nested.mkdir(parents=True)
    (workspace / ".anthropic-credentials").write_text("sk-ant-xyz", encoding="utf-8")

    assert find_workspace_root(start=nested) == workspace.resolve()


def test_find_workspace_root_returns_none_when_absent(tmp_path):
    assert find_workspace_root(start=tmp_path) is None


def test_load_settings_from_files(tmp_path, isolated_env):
    _write_creds(
        tmp_path,
        anthropic="sk-ant-from-file",
        langfuse_kv={
            "LANGFUSE_SECRET_KEY": "sk-lf-secret",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-public",
            "LANGFUSE_BASE_URL": "https://us.cloud.langfuse.com",
        },
    )
    settings = load_settings(workspace_root=tmp_path)

    assert isinstance(settings, Settings)
    assert settings.anthropic_api_key == "sk-ant-from-file"
    assert settings.langfuse_secret_key == "sk-lf-secret"
    assert settings.langfuse_public_key == "pk-lf-public"
    assert settings.langfuse_base_url == "https://us.cloud.langfuse.com"
    assert settings.model == DEFAULT_MODEL


def test_load_settings_env_vars_override_files(tmp_path, monkeypatch):
    _write_creds(
        tmp_path,
        anthropic="sk-ant-from-file",
        langfuse_kv={
            "LANGFUSE_SECRET_KEY": "sk-lf-from-file",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-from-file",
            "LANGFUSE_BASE_URL": "https://file.example.com",
        },
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-from-env")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://env.example.com")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    settings = load_settings(workspace_root=tmp_path)

    assert settings.anthropic_api_key == "sk-ant-from-env"
    assert settings.langfuse_secret_key == "sk-lf-from-env"
    assert settings.langfuse_base_url == "https://env.example.com"
    assert settings.langfuse_public_key == "pk-lf-from-file"


def test_load_settings_langfuse_host_alias(tmp_path, monkeypatch, isolated_env):
    _write_creds(
        tmp_path,
        anthropic="sk-ant-x",
        langfuse_kv={
            "LANGFUSE_SECRET_KEY": "sk-lf-x",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-x",
        },
    )
    monkeypatch.setenv("LANGFUSE_HOST", "https://host-alias.example.com")

    settings = load_settings(workspace_root=tmp_path)
    assert settings.langfuse_base_url == "https://host-alias.example.com"


def test_load_settings_model_override(tmp_path, isolated_env):
    _write_creds(
        tmp_path,
        anthropic="sk-ant-x",
        langfuse_kv={
            "LANGFUSE_SECRET_KEY": "sk",
            "LANGFUSE_PUBLIC_KEY": "pk",
            "LANGFUSE_BASE_URL": "https://us.cloud.langfuse.com",
        },
    )
    settings = load_settings(workspace_root=tmp_path, model="claude-haiku-4-5-20251001")
    assert settings.model == "claude-haiku-4-5-20251001"


def test_load_settings_missing_anthropic_raises(tmp_path, isolated_env):
    _write_creds(
        tmp_path,
        anthropic=None,
        langfuse_kv={
            "LANGFUSE_SECRET_KEY": "sk",
            "LANGFUSE_PUBLIC_KEY": "pk",
            "LANGFUSE_BASE_URL": "https://us.cloud.langfuse.com",
        },
    )
    with pytest.raises(ConfigError) as exc:
        load_settings(workspace_root=tmp_path)
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_load_settings_missing_langfuse_keys_raises(tmp_path, isolated_env):
    _write_creds(tmp_path, anthropic="sk-ant-x", langfuse_kv={})
    with pytest.raises(ConfigError) as exc:
        load_settings(workspace_root=tmp_path)
    msg = str(exc.value)
    assert "LANGFUSE_SECRET_KEY" in msg
    assert "LANGFUSE_PUBLIC_KEY" in msg
    assert "LANGFUSE_BASE_URL" in msg


def test_load_settings_no_workspace_root_no_env_raises(tmp_path, isolated_env, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        load_settings()
