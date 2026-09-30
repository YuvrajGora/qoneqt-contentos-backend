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
    model = settings.groq_model
    if not model:
        raise ProviderConfigError(
            "GROQ_MODEL is not configured. "
            "Set it in your .env file (e.g. GROQ_MODEL=llama-3.3-70b-versatile)."
        )

    client = _get_client()

    try:
        logger.debug("Sending content-plan request to Groq (model=%s)", model)
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
    except AuthenticationError as exc:
        raise ProviderAuthError(
            "Groq authentication failed. Check that GROQ_API_KEY is valid."
        ) from exc
    except RateLimitError as exc:
        raise ProviderRateLimitError(
            "Groq rate limit reached. Try again shortly."
        ) from exc
    except APITimeoutError as exc:
        raise ProviderNetworkError(
            "Groq request timed out. Check your network connection."
        ) from exc
    except APIConnectionError as exc:
        raise ProviderNetworkError(
            f"Could not connect to Groq: {exc}"
        ) from exc
    except APIStatusError as exc:
        raise ProviderResponseError(
            f"Groq returned HTTP {exc.status_code}. See logs for details."
        ) from exc

    raw_content = completion.choices[0].message.content
    if not raw_content:
        raise ProviderResponseError("Groq returned an empty response body.")

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(
            f"Groq response was not valid JSON: {exc}"
        ) from exc
