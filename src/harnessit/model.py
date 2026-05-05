"""Naked frontier model layer.

Thin wrapper around ``anthropic.Anthropic`` that accepts a system
prompt + a user message and returns a structured ``Completion``. The
"naked" qualifier is per Build Plan v0.3 §2.1 stage 2 — no tools, no
retrieval, no memory. Stage 3 grows this into the tool surface.

The Anthropic client is injected via constructor so tests can swap in a
fake without touching the network. Production callers use
``ModelClient.from_settings()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from harnessit.config import Settings


@dataclass(frozen=True)
class Completion:
    """Structured result of a single naked-model call."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None


class _MessagesAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class _AnthropicLike(Protocol):
    messages: _MessagesAPI


class ModelClient:
    """Naked frontier-model client.

    Parameters
    ----------
    client:
        An object exposing ``client.messages.create(...)`` — the
        Anthropic SDK's ``Anthropic`` instance, or a fake in tests.
    model:
        Model id used for every call (no per-call override yet).
    default_max_tokens:
        Default cap on output tokens. Callers can override per call.
    """

    def __init__(
        self,
        *,
        client: _AnthropicLike,
        model: str,
        default_max_tokens: int = 4096,
    ) -> None:
        self._client = client
        self.model = model
        self.default_max_tokens = default_max_tokens

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: Any) -> "ModelClient":
        """Construct using a real ``anthropic.Anthropic`` from Settings."""
        from anthropic import Anthropic

        return cls(
            client=Anthropic(api_key=settings.anthropic_api_key),
            model=settings.model,
            **kwargs,
        )

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int | None = None,
    ) -> Completion:
        """One-shot completion with a system prompt + a single user turn."""
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.default_max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _to_completion(response)


def _to_completion(response: Any) -> Completion:
    """Extract Completion fields from an Anthropic Message response."""
    text = "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    )
    usage = response.usage
    return Completion(
        text=text,
        model=response.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        stop_reason=response.stop_reason,
    )
