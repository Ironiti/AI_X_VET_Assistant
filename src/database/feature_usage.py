"""Хранение событий использования функций главного меню Telegram-бота."""

from datetime import datetime, timedelta
from typing import Optional

import aiosqlite


MAIN_MENU_FEATURES = {
    "🔬 Задать вопрос": "question",
    "📋 Стоп-лист": "stoplist",
    "🖼️ Галерея пробирок": "gallery",
    "📄 Скачать бланки": "blanks",
    "📞 Связь с лабораторией": "laboratory_contact",
}


def get_main_menu_feature(button_text: Optional[str]) -> Optional[str]:
    """Возвращает стабильный ключ функции для точного текста кнопки."""
    if not button_text:
        return None
    return MAIN_MENU_FEATURES.get(button_text)


class FeatureUsageTracker:
    """Записывает и агрегирует нажатия функций главного меню."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._schema_ready = False

    async def ensure_schema(self) -> None:
        """Создаёт таблицу событий и индексы при первом обращении."""
        if self._schema_ready:
            return

        async with aiosqlite.connect(self.db_path, timeout=10) as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feature_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    feature_key TEXT NOT NULL,
                    button_text TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'telegram_main_menu',
                    timestamp TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
                """
            )
            await connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feature_usage_feature_time
                ON feature_usage_events(feature_key, timestamp)
                """
            )
            await connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_feature_usage_user_time
                ON feature_usage_events(user_id, timestamp)
                """
            )
            await connection.commit()

        self._schema_ready = True

    async def log_main_menu_selection(
        self,
        user_id: int,
        feature_key: str,
        button_text: str,
    ) -> bool:
        """
        Записывает одно нажатие.

        События неизвестных пользователей и администраторов не попадают
        в продуктовую статистику.
        """
        await self.ensure_schema()
        timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")

        async with aiosqlite.connect(self.db_path, timeout=10) as connection:
            await connection.execute(
                """
                INSERT INTO feature_usage_events (
                    user_id,
                    feature_key,
                    button_text,
                    source,
                    timestamp
                )
                SELECT ?, ?, ?, 'telegram_main_menu', ?
                WHERE EXISTS (
                    SELECT 1
                    FROM users
                    WHERE telegram_id = ?
                      AND COALESCE(role, 'user') != 'admin'
                )
                """,
                (user_id, feature_key, button_text, timestamp, user_id),
            )
            cursor = await connection.execute("SELECT changes()")
            row = await cursor.fetchone()
            await connection.commit()
            return bool(row and row[0])

    async def get_summary(self, days: Optional[int] = None) -> list[dict]:
        """Возвращает количество использований и уникальных пользователей."""
        await self.ensure_schema()

        where_clause = ""
        parameters: list[str] = []
        if days is not None:
            since = datetime.now() - timedelta(days=days)
            where_clause = "WHERE events.timestamp >= ?"
            parameters.append(since.isoformat(sep=" ", timespec="seconds"))

        query = f"""
            SELECT
                events.feature_key,
                COUNT(*) AS usage_count,
                COUNT(DISTINCT events.user_id) AS unique_users,
                MIN(events.timestamp) AS first_used_at,
                MAX(events.timestamp) AS last_used_at
            FROM feature_usage_events AS events
            {where_clause}
            GROUP BY events.feature_key
            ORDER BY usage_count DESC, events.feature_key ASC
        """

        async with aiosqlite.connect(self.db_path, timeout=10) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(query, parameters)
            rows = [dict(row) for row in await cursor.fetchall()]

        total = sum(row["usage_count"] for row in rows)
        for row in rows:
            row["share_percent"] = (
                round(row["usage_count"] * 100 / total, 2) if total else 0.0
            )
        return rows
