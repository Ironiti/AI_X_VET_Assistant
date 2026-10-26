"""Provider selection shared by chat and remote embeddings.

Credentials are loaded from ENV only. Keep the internal embedding model name
stable so changing its API gateway does not invalidate the existing index.
"""
import os

from config import OPENROUTER_API_KEY, POLZA_AI_API_KEY


AI_PROVIDER = os.getenv("AI_PROVIDER", "polza").strip().lower() or "polza"
if AI_PROVIDER not in {"polza", "timeweb", "openrouter"}:
    raise RuntimeError("Unsupported AI_PROVIDER setting.")

USE_TIMEWEB_AI = AI_PROVIDER == "timeweb"
USE_POLZA_AI = AI_PROVIDER == "polza"


def api_settings():
    if USE_TIMEWEB_AI:
        key = os.getenv("TIMEWEB_AI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("TIMEWEB_AI_API_KEY not found.")
        return "https://api.timeweb.ai/v1", key
    if USE_POLZA_AI:
        return "https://api.polza.ai/api/v1", POLZA_AI_API_KEY
    return "https://openrouter.ai/api/v1", OPENROUTER_API_KEY


def chat_model_name(model_name):
    if USE_TIMEWEB_AI and model_name in {
        "google/gemini-2.5-flash-lite", "@preset/vet-ai-agent"
    }:
        return os.getenv("TIMEWEB_CHAT_MODEL", "gemini/gemini-3.1-flash-lite").strip() or "gemini/gemini-3.1-flash-lite"
    return model_name


def embedding_api_model_name(model_name):
    if USE_TIMEWEB_AI and model_name == "text-embedding-3-large":
        return "openai/text-embedding-3-large"
    return model_name


def chat_retry_options():
    # Legacy providers retain their existing SDK policy.
    return {"max_retries": 1} if USE_TIMEWEB_AI else {}


def embedding_retry_options():
    # The embedding wrapper already has retries; do not multiply them in the SDK.
    return {"timeout": 10.0, "max_retries": 0} if USE_TIMEWEB_AI else {}
