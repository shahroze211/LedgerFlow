"""LLM provider interface + factory.

The extractor is the *only* place a foundation model touches the system, and it
sits behind this one small interface. Swap stub <-> OpenAI <-> Gemini by changing
one env var; everything downstream (validate, gate, sync) is provider-agnostic.
That seam is the Forward-Deployed-Engineer point: integration over cleverness.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..config import get_settings
from ..models.schemas import ExtractionResult


@runtime_checkable
class ExtractionProvider(Protocol):
    name: str

    def extract(self, *, text: str, media_type: str | None, source_ref: str) -> ExtractionResult:
        """Return structured fields + per-field confidence + source spans.

        Contract (enforced by callers and the prompt):
        - Never guess. A field that isn't clearly present is ``None`` with low
          confidence, not a hallucinated value.
        - ``field_confidence`` keys mirror the header field names.
        - ``field_sources`` carries the raw text span each field was grounded in.
        """
        ...


class ProviderError(RuntimeError):
    """Raised when a provider fails in a way that should be retried (P4)."""


def get_provider(name: str | None = None) -> ExtractionProvider:
    settings = get_settings()
    provider = (name or settings.llm_provider).lower()

    if provider == "stub":
        from .providers.stub import StubProvider

        return StubProvider()
    if provider == "openai":
        from .providers.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if provider == "gemini":
        from .providers.gemini_provider import GeminiProvider

        return GeminiProvider()

    raise ValueError(f"unknown LLM provider: {provider!r} (use stub|openai|gemini)")
