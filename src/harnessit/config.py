"""Workspace-aware configuration loader.

Two credential file conventions are supported, established at the
workspace root:

* ``.anthropic-credentials`` — raw API key value on a single line.
* ``.langfuse-credentials`` — shell-style ``KEY="value"`` lines for the
  three Langfuse keys (``LANGFUSE_SECRET_KEY``, ``LANGFUSE_PUBLIC_KEY``,
  ``LANGFUSE_BASE_URL``).

Precedence is environment variables > credential files. The workspace
root is located by walking up from a given start directory looking for
either credential file; tests pass an explicit ``workspace_root``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "claude-opus-4-7"

ANTHROPIC_CREDENTIAL_FILE = ".anthropic-credentials"
LANGFUSE_CREDENTIAL_FILE = ".langfuse-credentials"


class ConfigError(RuntimeError):
    """Raised when required credentials cannot be resolved."""


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    langfuse_secret_key: str
    langfuse_public_key: str
    langfuse_base_url: str
    model: str = DEFAULT_MODEL


def find_workspace_root(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` looking for a credentials file.

    Returns the first directory containing either credentials file, or
    ``None`` if none is found before reaching the filesystem root. The
    workspace is identified by the presence of credentials, not by a
    sentinel file — this matches the existing convention.
    """
    here = (start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ANTHROPIC_CREDENTIAL_FILE).exists():
            return candidate
        if (candidate / LANGFUSE_CREDENTIAL_FILE).exists():
            return candidate
    return None


def _read_raw_credential(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


_KV_LINE = re.compile(r'^\s*([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\r\n]*)"?\s*$')


def _read_kv_credentials(path: Path) -> dict[str, str]:
    """Parse a ``KEY="value"`` shell-style credential file.

    Tolerates unquoted values, blank lines, and ``#`` comments.
    """
    if not path.exists():
        return {}
    parsed: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _KV_LINE.match(stripped)
        if match:
            parsed[match.group(1)] = match.group(2)
    return parsed


def load_settings(
    *,
    workspace_root: Path | None = None,
    model: str | None = None,
) -> Settings:
    """Load settings from env vars + workspace credential files.

    Parameters
    ----------
    workspace_root:
        Directory containing the credential files. If None, located via
        ``find_workspace_root()``.
    model:
        Override the model name. Defaults to ``ANTHROPIC_MODEL`` env var
        or ``DEFAULT_MODEL``.

    Raises
    ------
    ConfigError
        If any required credential is missing from both the environment
        and the credential files.
    """
    root = workspace_root or find_workspace_root()

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    langfuse_kv: dict[str, str] = {}
    if root is not None:
        if anthropic_key is None:
            anthropic_key = _read_raw_credential(root / ANTHROPIC_CREDENTIAL_FILE)
        langfuse_kv = _read_kv_credentials(root / LANGFUSE_CREDENTIAL_FILE)

    secret = os.environ.get("LANGFUSE_SECRET_KEY") or langfuse_kv.get("LANGFUSE_SECRET_KEY")
    public = os.environ.get("LANGFUSE_PUBLIC_KEY") or langfuse_kv.get("LANGFUSE_PUBLIC_KEY")
    base_url = (
        os.environ.get("LANGFUSE_BASE_URL")
        or os.environ.get("LANGFUSE_HOST")
        or langfuse_kv.get("LANGFUSE_BASE_URL")
        or langfuse_kv.get("LANGFUSE_HOST")
    )

    missing = [
        name
        for name, value in [
            ("ANTHROPIC_API_KEY", anthropic_key),
            ("LANGFUSE_SECRET_KEY", secret),
            ("LANGFUSE_PUBLIC_KEY", public),
            ("LANGFUSE_BASE_URL", base_url),
        ]
        if not value
    ]
    if missing:
        searched = root if root is not None else "(no workspace root found)"
        raise ConfigError(
            f"Missing required settings: {', '.join(missing)}. "
            f"Searched workspace root: {searched}"
        )

    return Settings(
        anthropic_api_key=anthropic_key,  # type: ignore[arg-type]
        langfuse_secret_key=secret,  # type: ignore[arg-type]
        langfuse_public_key=public,  # type: ignore[arg-type]
        langfuse_base_url=base_url,  # type: ignore[arg-type]
        model=model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL,
    )
