"""Telegram-only proxy selection with a reserve proxy fallback."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProxyCandidate:
    name: str
    url: str


ProxyChecker = Callable[[str, str, float], tuple[bool, str]]


def env_flag_enabled(value: str | bool | None, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if not normalized:
        return default
    return normalized not in {"0", "false", "no", "off"}


def mask_proxy(proxy_url: str) -> str:
    if not proxy_url:
        return "direct"
    if "@" not in proxy_url:
        return proxy_url
    scheme, rest = proxy_url.split("://", 1) if "://" in proxy_url else ("", proxy_url)
    host = rest.split("@", 1)[1]
    return f"{scheme + '://' if scheme else ''}***@{host}"


def build_proxy_candidates(
    primary_proxy_url: str | None,
    reserve_proxy_url: str | None,
) -> list[ProxyCandidate]:
    candidates: list[ProxyCandidate] = []
    seen: set[str] = set()

    for name, proxy_url in (
        ("primary", (primary_proxy_url or "").strip()),
        ("reserve", (reserve_proxy_url or "").strip()),
    ):
        if not proxy_url or proxy_url in seen:
            continue
        seen.add(proxy_url)
        candidates.append(ProxyCandidate(name=name, url=proxy_url))

    return candidates


def check_telegram_getme(bot_token: str, proxy_url: str, timeout: float) -> tuple[bool, str]:
    handlers: list[urllib.request.BaseHandler] = []
    if proxy_url:
        handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/getMe",
        headers={"User-Agent": "ai-vet-telegram-proxy-check/1.0"},
    )

    try:
        with opener.open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return False, str(exc)

    if not payload.get("ok"):
        return False, "Telegram getMe returned ok=false"
    username = (payload.get("result") or {}).get("username", "unknown")
    return True, f"getMe ok: @{username}"


def select_telegram_proxy(
    *,
    bot_token: str,
    primary_proxy_url: str | None,
    reserve_proxy_url: str | None,
    preflight_enabled: str | bool | None = True,
    timeout: float = 5,
    checker: ProxyChecker = check_telegram_getme,
) -> str | None:
    candidates = build_proxy_candidates(primary_proxy_url, reserve_proxy_url)
    if not candidates:
        logger.info("[TG PROXY] No Telegram proxy configured, using direct connection")
        return None

    if len(candidates) == 1 or not env_flag_enabled(preflight_enabled):
        selected = candidates[0]
        logger.info("[TG PROXY] Using %s proxy: %s", selected.name, mask_proxy(selected.url))
        return selected.url

    for candidate in candidates:
        ok, message = checker(bot_token, candidate.url, timeout)
        if ok:
            logger.info(
                "[TG PROXY] Selected %s proxy %s (%s)",
                candidate.name,
                mask_proxy(candidate.url),
                message,
            )
            return candidate.url
        logger.warning(
            "[TG PROXY] %s proxy failed: %s (%s)",
            candidate.name,
            mask_proxy(candidate.url),
            message,
        )

    fallback = candidates[0]
    logger.error(
        "[TG PROXY] All configured proxies failed during preflight; using primary anyway: %s",
        mask_proxy(fallback.url),
    )
    return fallback.url
