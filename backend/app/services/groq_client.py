"""
Isolated Groq API client.

The rest of the backend should not import from the groq SDK directly.
Swap this module to change the underlying provider without touching the
content planner or routes.
"""

import json
import logging
from typing import Any, Dict

from groq import Groq, AuthenticationError, RateLimitError, APIConnectionError, APITimeoutError, APIStatusError

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions — provider-neutral so callers don't need to know Groq
# ---------------------------------------------------------------------------

class ProviderConfigError(Exception):
    """GROQ_API_KEY is missing or the client cannot be initialised."""


class ProviderAuthError(Exception):
    """Authentication with the provider failed (bad API key)."""


class ProviderRateLimitError(Exception):
    """The provider rate-limited this request."""


class ProviderNetworkError(Exception):
    """Network or timeout error reaching the provider."""


class ProviderResponseError(Exception):
    """The provider returned an unexpected or malformed response."""


# ---------------------------------------------------------------------------
# Lazy client initialisation — validated on first use, not at import time
# ---------------------------------------------------------------------------

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = settings.groq_api_key
        if not api_key:
            raise ProviderConfigError(
                "GROQ_API_KEY is not configured. "
                "Set it in your .env file or as an environment variable."
            )
        _client = Groq(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def generate_structured_json(
    system_prompt: str,
    user_prompt: str,
) -> Dict[str, Any]:
    """
    Send a structured-output request to Groq and return the parsed JSON dict.

    Uses response_format={"type": "json_object"} which is broadly supported
    across Groq-hosted models (llama-3.x, mixtral, gemma-3, etc.).

    Raises provider-neutral exceptions on failure.
    Never logs credentials or authorization headers.
    """
    client = _get_client()

    models_to_try = []
    if settings.groq_model:
        models_to_try.append(settings.groq_model)
    for m in ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile"]:
        if m not in models_to_try:
            models_to_try.append(m)

    last_exc = None
    for model in models_to_try:
        try:
            logger.info("Sending content-plan request to Groq (model=%s)", model)
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=4096,
            )
            raw_content = completion.choices[0].message.content
            if not raw_content:
                continue
            return json.loads(raw_content)
        except AuthenticationError as exc:
            raise ProviderAuthError(
                "Groq authentication failed. Check that GROQ_API_KEY is valid."
            ) from exc
        except RateLimitError as exc:
            logger.warning("Groq model %s rate-limited: %s", model, exc)
            last_exc = exc
            continue
        except APIStatusError as exc:
            logger.warning("Groq model %s status error (%s): %s", model, exc.status_code, exc)
            last_exc = exc
            continue
        except (APITimeoutError, APIConnectionError) as exc:
            logger.warning("Groq network error with %s: %s", model, exc)
            last_exc = exc
            continue
        except json.JSONDecodeError as exc:
            logger.warning("Groq response from %s was not valid JSON: %s", model, exc)
            last_exc = exc
            continue

    if last_exc:
        raise ProviderResponseError(f"All Groq models failed. Last error: {last_exc}") from last_exc
    raise ProviderResponseError("Groq returned an empty response.")
