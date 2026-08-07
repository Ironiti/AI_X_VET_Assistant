"""Lightweight event-loop heartbeat for external bot monitoring."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time


logger = logging.getLogger(__name__)
DEFAULT_INTERVAL_SECONDS = 30


def default_heartbeat_path(filename: str) -> Path:
    configured = os.getenv("BOT_HEARTBEAT_FILE", "").strip()
    if configured:
        return Path(configured)
    if os.name == "nt":
        return Path("data") / "heartbeats" / filename
    return Path("/run/ai-vet-heartbeats") / filename


def write_heartbeat(
    bot_name: str,
    path: Path,
    *,
    timestamp: float | None = None,
    pid: int | None = None,
) -> None:
    """Atomically update a JSON heartbeat file."""
    timestamp = time.time() if timestamp is None else timestamp
    pid = os.getpid() if pid is None else pid
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "bot": bot_name,
        "pid": pid,
        "status": "running",
        "timestamp": timestamp,
        "updated_at": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
    }
    temp_path = path.with_name(f".{path.name}.{pid}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


async def heartbeat_loop(
    bot_name: str,
    filename: str,
    *,
    stop_event: asyncio.Event | None = None,
    interval_seconds: int | None = None,
) -> None:
    """Refresh heartbeat while the bot event loop remains responsive."""
    path = default_heartbeat_path(filename)
    configured_interval = os.getenv("BOT_HEARTBEAT_INTERVAL_SECONDS", "").strip()
    if interval_seconds is None:
        try:
            interval_seconds = int(configured_interval) if configured_interval else DEFAULT_INTERVAL_SECONDS
        except ValueError:
            interval_seconds = DEFAULT_INTERVAL_SECONDS
    interval_seconds = max(5, interval_seconds)

    logger.info("[HEARTBEAT] %s -> %s every %ss", bot_name, path, interval_seconds)
    while stop_event is None or not stop_event.is_set():
        try:
            write_heartbeat(bot_name, path)
        except OSError as exc:
            logger.error("[HEARTBEAT] Could not update %s: %s", path, exc)

        if stop_event is None:
            await asyncio.sleep(interval_seconds)
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue
