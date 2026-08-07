import asyncio
import sqlite3

from src.database.feature_usage import (
    FeatureUsageTracker,
    get_main_menu_feature,
)


def _create_users_table(db_path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE users (
                telegram_id INTEGER PRIMARY KEY,
                role TEXT DEFAULT 'user'
            )
            """
        )
        connection.executemany(
            "INSERT INTO users (telegram_id, role) VALUES (?, ?)",
            [(101, "user"), (202, "admin")],
        )


def test_main_menu_button_mapping_is_exact():
    assert get_main_menu_feature("🔬 Задать вопрос") == "question"
    assert get_main_menu_feature("📋 Стоп-лист") == "stoplist"
    assert get_main_menu_feature("🖼️ Галерея пробирок") == "gallery"
    assert get_main_menu_feature("📄 Скачать бланки") == "blanks"
    assert (
        get_main_menu_feature("📞 Связь с лабораторией")
        == "laboratory_contact"
    )
    assert get_main_menu_feature("💡 Предложение") == "feedback"
    assert get_main_menu_feature("⚠️ Жалоба") == "feedback"
    assert get_main_menu_feature("произвольный текст") is None
    assert get_main_menu_feature(None) is None


def test_tracker_records_users_but_not_admins(tmp_path):
    db_path = tmp_path / "metrics.db"
    _create_users_table(db_path)
    tracker = FeatureUsageTracker(str(db_path))

    async def scenario():
        assert await tracker.log_main_menu_selection(
            101, "question", "🔬 Задать вопрос"
        )
        assert await tracker.log_main_menu_selection(
            101, "question", "🔬 Задать вопрос"
        )
        assert await tracker.log_main_menu_selection(
            101, "gallery", "🖼️ Галерея пробирок"
        )
        assert not await tracker.log_main_menu_selection(
            202, "stoplist", "📋 Стоп-лист"
        )
        assert not await tracker.log_main_menu_selection(
            999, "blanks", "📄 Скачать бланки"
        )
        return await tracker.get_summary()

    summary = asyncio.run(scenario())

    assert [
        (
            row["feature_key"],
            row["usage_count"],
            row["unique_users"],
            row["share_percent"],
        )
        for row in summary
    ] == [
        ("question", 2, 1, 66.67),
        ("gallery", 1, 1, 33.33),
    ]
    assert all(row["first_used_at"] for row in summary)
    assert all(row["last_used_at"] for row in summary)

    with sqlite3.connect(db_path) as connection:
        event_count = connection.execute(
            "SELECT COUNT(*) FROM feature_usage_events"
        ).fetchone()[0]
    assert event_count == 3
