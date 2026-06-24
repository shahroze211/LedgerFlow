"""OpenAI extraction provider (selected via LEDGERFLOW_LLM_PROVIDER=openai)."""

from __future__ import annotations

import json

from ...config import get_settings
from ...models.schemas import ExtractionResult
from ..prompts import SYSTEM_PROMPT, user_prompt
from ..provider import ProviderError


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ProviderError("LEDGERFLOW_OPENAI_API_KEY is not set.")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise ProviderError("pip install openai to use the OpenAI provider.") from exc
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def extract(
        self, *, text: str, media_type: str | None, source_ref: str
    ) -> ExtractionResult:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt(text)},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
        except Exception as exc:  # network/timeout/etc -> retryable (P4)
            raise ProviderError(f"OpenAI call failed: {exc}") from exc

        try:
            return ExtractionResult.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ProviderError(f"OpenAI returned non-conforming JSON: {exc}") from exc
