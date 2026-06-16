"""
AIOrchestrator — routes ProcessedEvent objects through an LLM and returns
a validated AnalysisResult.

Caching strategy
────────────────
  In-memory TTLCache (cachetools) keyed by a deterministic hash of the event's
  identity + data values.  Two calls for the same event_id with the same actual
  value return the cached result instantly.

  The cache is instance-scoped so it is shared across all callers that use the
  same orchestrator instance (e.g. a FastAPI dependency singleton).

Provider abstraction
────────────────────
  ai_provider = "anthropic"  → uses anthropic.AsyncAnthropic
  ai_provider = "openai"     → uses openai.AsyncOpenAI

  Both paths normalise the response to the same AnalysisResult model.
  The Anthropic path uses assistant-turn prefill ("{") to guarantee JSON output.
  The OpenAI path uses response_format={"type": "json_object"}.

Error handling
──────────────
  • JSON parse failures retry once after stripping prose / fences.
  • Pydantic validation failures surface as AIAnalysisError with the raw
    response attached so callers can log and alert.
"""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from cachetools import TTLCache

from app.core.config import Settings, get_settings
from app.core.prompts import SYSTEM_PROMPT, build_user_prompt
from app.models import AnalysisResult, ProcessedEvent

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Custom exception
# ─────────────────────────────────────────────────────────────────────────────

class AIAnalysisError(Exception):
    def __init__(self, message: str, raw_response: str = "") -> None:
        super().__init__(message)
        self.raw_response = raw_response


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class AIOrchestrator:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._cache: TTLCache = TTLCache(
            maxsize=self._settings.ai_cache_max_size,
            ttl=self._settings.ai_cache_ttl_seconds,
        )
        # Per-key lock prevents cache stampede under concurrent requests
        self._inflight: dict[str, asyncio.Event] = {}
        self._inflight_results: dict[str, AnalysisResult] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    async def analyze(self, processed_event: ProcessedEvent) -> AnalysisResult:
        """
        Analyse a pre-processed economic event.

        Returns a cached AnalysisResult on repeated calls for the same event
        data without hitting the AI provider.
        """
        cache_key = self._cache_key(processed_event)

        # Fast path: cache hit
        if cache_key in self._cache:
            logger.debug("Cache hit for event %s", processed_event.event.event_id)
            cached = self._cache[cache_key]
            return cached.model_copy(update={"cached": True})

        # Stampede guard: if another coroutine is already fetching this key,
        # wait for it instead of firing a duplicate request.
        if cache_key in self._inflight:
            await self._inflight[cache_key].wait()
            if cache_key in self._cache:
                return self._cache[cache_key].model_copy(update={"cached": True})

        event = asyncio.Event()
        self._inflight[cache_key] = event
        try:
            result = await self._call_provider(processed_event)
            self._cache[cache_key] = result
            return result
        finally:
            event.set()
            self._inflight.pop(cache_key, None)

    def cache_info(self) -> dict[str, Any]:
        return {
            "size": len(self._cache),
            "maxsize": self._cache.maxsize,
            "ttl_seconds": self._cache.ttl,
        }

    def clear_cache(self) -> None:
        self._cache.clear()

    # ── Routing ───────────────────────────────────────────────────────────────

    async def _call_provider(self, processed_event: ProcessedEvent) -> AnalysisResult:
        if self._settings.ai_provider == "anthropic":
            return await self._call_anthropic(processed_event)
        if self._settings.ai_provider == "gemini":
            return await self._call_gemini(processed_event)
        return await self._call_openai(processed_event)

    # ── Anthropic path ────────────────────────────────────────────────────────

    async def _call_anthropic(self, processed_event: ProcessedEvent) -> AnalysisResult:
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise AIAnalysisError(
                "anthropic package not installed. Run: pip install anthropic"
            ) from exc

        client = _anthropic.AsyncAnthropic(api_key=self._settings.anthropic_api_key)
        model = self._settings.anthropic_model

        logger.info(
            "Calling Anthropic (%s) for event %s", model, processed_event.event.event_id
        )

        message = await client.messages.create(
            model=model,
            max_tokens=self._settings.ai_max_tokens,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": build_user_prompt(processed_event)},
                # Prefill forces the model to begin its response with "{"
                # so the output is guaranteed to be a JSON object.
                {"role": "assistant", "content": "{"},
            ],
        )

        # The response continues from the "{" prefill
        raw = "{" + message.content[0].text
        return self._parse_and_validate(raw, model, processed_event.event.event_id)

    # ── OpenAI path ───────────────────────────────────────────────────────────

    async def _call_openai(self, processed_event: ProcessedEvent) -> AnalysisResult:
        try:
            import openai as _openai
        except ImportError as exc:
            raise AIAnalysisError(
                "openai package not installed. Run: pip install openai"
            ) from exc

        client = _openai.AsyncOpenAI(api_key=self._settings.openai_api_key)
        model = self._settings.openai_model

        logger.info(
            "Calling OpenAI (%s) for event %s", model, processed_event.event.event_id
        )

        response = await client.chat.completions.create(
            model=model,
            max_tokens=self._settings.ai_max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(processed_event)},
            ],
        )

        raw = response.choices[0].message.content or ""
        return self._parse_and_validate(raw, model, processed_event.event.event_id)

    # ── Gemini path ───────────────────────────────────────────────────────────

    async def _call_gemini(self, processed_event: ProcessedEvent) -> AnalysisResult:
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise AIAnalysisError(
                "google-generativeai package not installed. Run: pip install google-generativeai"
            ) from exc

        genai.configure(api_key=self._settings.gemini_api_key)
        model_name = self._settings.gemini_model

        logger.info(
            "Calling Gemini (%s) for event %s", model_name, processed_event.event.event_id
        )

        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={"response_mime_type": "application/json"},
            system_instruction=SYSTEM_PROMPT,
        )

        response = await model.generate_content_async(build_user_prompt(processed_event))
        raw = response.text
        return self._parse_and_validate(raw, model_name, processed_event.event.event_id)

    # ── Parsing + validation ──────────────────────────────────────────────────

    def _parse_and_validate(
        self, raw: str, model_used: str, event_id: str
    ) -> AnalysisResult:
        """Parse raw LLM text → AnalysisResult, retrying once after fence stripping."""
        data = self._extract_json(raw)
        if data is None:
            raise AIAnalysisError(
                f"Could not extract JSON from model response for event {event_id}",
                raw_response=raw,
            )

        # Inject orchestrator-level metadata before Pydantic validation
        data["event_id"] = event_id
        data["model_used"] = model_used
        data["cached"] = False
        data["analyzed_at"] = datetime.now(timezone.utc).isoformat()

        try:
            return AnalysisResult(**data)
        except Exception as exc:
            raise AIAnalysisError(
                f"AnalysisResult validation failed for event {event_id}: {exc}",
                raw_response=raw,
            ) from exc

    @staticmethod
    def _extract_json(text: str) -> dict | None:
        """
        Best-effort JSON extractor.
        Handles:
          - Clean JSON strings
          - Markdown-fenced ```json ... ``` blocks
          - Prose-wrapped JSON (finds first '{' to last '}')
        """
        text = text.strip()

        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strip markdown fences
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fenced:
            try:
                return json.loads(fenced.group(1))
            except json.JSONDecodeError:
                pass

        # Last resort: extract from first '{' to last '}'
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _cache_key(processed_event: ProcessedEvent) -> str:
        e = processed_event.event
        raw = f"{e.event_id}:{e.actual}:{e.forecast}:{e.impact_level.value}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Canonical singleton factory (used by routers AND the scheduler)
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_ai_orchestrator() -> AIOrchestrator:
    """
    Return the process-wide AIOrchestrator singleton.

    Override via app.dependency_overrides[get_ai_orchestrator] in tests.
    """
    return AIOrchestrator()
