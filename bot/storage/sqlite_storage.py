"""Persistent SQLite storage for aiogram FSM state and data."""

from __future__ import annotations

import asyncio
import pickle
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import aiosqlite
from aiogram.exceptions import DataNotDictLikeError
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey


class SQLiteStorage(BaseStorage):
    """Store dialog state in a local SQLite database across bot restarts."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._connection: aiosqlite.Connection | None = None
        self._init_lock = asyncio.Lock()
        self._update_lock = asyncio.Lock()

    @staticmethod
    def _key_values(key: StorageKey) -> tuple[int, int, int, int, str, str]:
        return (
            key.bot_id,
            key.chat_id,
            key.user_id,
            getattr(key, "thread_id", None) or 0,
            getattr(key, "business_connection_id", None) or "",
            getattr(key, "destiny", "default"),
        )

    async def _get_connection(self) -> aiosqlite.Connection:
        if self._connection is not None:
            return self._connection

        async with self._init_lock:
            if self._connection is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                connection = await aiosqlite.connect(self.path, timeout=10)
                await connection.execute("PRAGMA journal_mode=WAL")
                await connection.execute("PRAGMA busy_timeout=10000")
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS fsm_storage (
                        bot_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        thread_id INTEGER NOT NULL DEFAULT 0,
                        business_connection_id TEXT NOT NULL DEFAULT '',
                        destiny TEXT NOT NULL DEFAULT 'default',
                        state TEXT,
                        data BLOB NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (
                            bot_id,
                            chat_id,
                            user_id,
                            thread_id,
                            business_connection_id,
                            destiny
                        )
                    )
                    """
                )
                await connection.commit()
                self._connection = connection

        return self._connection

    async def set_state(self, key: StorageKey, state: State | str | None = None) -> None:
        connection = await self._get_connection()
        state_value = state.state if isinstance(state, State) else state
        empty_data = pickle.dumps({}, protocol=pickle.HIGHEST_PROTOCOL)
        await connection.execute(
            """
            INSERT INTO fsm_storage (
                bot_id, chat_id, user_id, thread_id,
                business_connection_id, destiny, state, data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (
                bot_id, chat_id, user_id, thread_id,
                business_connection_id, destiny
            ) DO UPDATE SET
                state = excluded.state,
                updated_at = CURRENT_TIMESTAMP
            """,
            (*self._key_values(key), state_value, empty_data),
        )
        await connection.commit()

    async def get_state(self, key: StorageKey) -> str | None:
        connection = await self._get_connection()
        cursor = await connection.execute(
            """
            SELECT state
            FROM fsm_storage
            WHERE bot_id = ? AND chat_id = ? AND user_id = ?
              AND thread_id = ? AND business_connection_id = ? AND destiny = ?
            """,
            self._key_values(key),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, Mapping):
            message = f"Data must be a dict or dict-like object, got {type(data).__name__}"
            raise DataNotDictLikeError(message)

        connection = await self._get_connection()
        payload = pickle.dumps(dict(data), protocol=pickle.HIGHEST_PROTOCOL)
        await connection.execute(
            """
            INSERT INTO fsm_storage (
                bot_id, chat_id, user_id, thread_id,
                business_connection_id, destiny, state, data
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT (
                bot_id, chat_id, user_id, thread_id,
                business_connection_id, destiny
            ) DO UPDATE SET
                data = excluded.data,
                updated_at = CURRENT_TIMESTAMP
            """,
            (*self._key_values(key), payload),
        )
        await connection.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        connection = await self._get_connection()
        cursor = await connection.execute(
            """
            SELECT data
            FROM fsm_storage
            WHERE bot_id = ? AND chat_id = ? AND user_id = ?
              AND thread_id = ? AND business_connection_id = ? AND destiny = ?
            """,
            self._key_values(key),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if not row:
            return {}
        return dict(pickle.loads(row[0]))

    async def update_data(
        self,
        key: StorageKey,
        data: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            message = f"Data must be a dict or dict-like object, got {type(data).__name__}"
            raise DataNotDictLikeError(message)

        async with self._update_lock:
            current_data = await self.get_data(key)
            current_data.update(data)
            await self.set_data(key, current_data)
            return current_data.copy()

    async def close(self) -> None:
        async with self._init_lock:
            if self._connection is not None:
                await self._connection.close()
                self._connection = None
