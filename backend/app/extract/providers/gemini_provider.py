"""Gemini extraction provider (selected via LEDGERFLOW_LLM_PROVIDER=gemini)."""

from __future__ import annotations

import json

from ...config import get_settings
from ...models.schemas import ExtractionResult
from ..prompts import SYSTEM_PROMPT, user_prompt
from ..provider import ProviderError


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise ProviderError("LEDGERFLOW_GEMINI_API_KEY is not set.")
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                "pip install google-generativeai to use the Gemini provider."
            ) from exc
        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(
            settings.gemini_model,
            system_instruction=SYSTEM_PROMPT,
            generation_config={"temperature": 0, "response_mime_type": "application/json"},
        )

    def extract(
        self, *, text: str, media_type: str | None, source_ref: str
    ) -> ExtractionResult:
        try:
            resp = self._model.generate_content(user_prompt(text))
            raw = resp.text or "{}"
        except Exception as exc:  # retryable (P4)
            raise ProviderError(f"Gemini call failed: {exc}") from exc

        try:
            return ExtractionResult.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ProviderError(f"Gemini returned non-conforming JSON: {exc}") from exc
