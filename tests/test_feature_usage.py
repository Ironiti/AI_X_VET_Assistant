import asyncio
import io
import sqlite3
import zipfile
from datetime import datetime, timedelta

import xlsxwriter

from src.database.feature_usage import (
    FEATURE_USAGE_COLUMNS,
    FeatureUsageTracker,
    get_main_menu_feature,
)
from utils.metrics_exporter import MetricsExporter


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


def test_tracker_returns_monthly_history(tmp_path):
    db_path = tmp_path / "metrics.db"
    _create_users_table(db_path)
    tracker = FeatureUsageTracker(str(db_path))

    async def scenario():
        await tracker.log_main_menu_selection(101, "question", "🔬 Задать вопрос")
        await tracker.log_main_menu_selection(101, "gallery", "🖼️ Галерея пробирок")

    asyncio.run(scenario())
    old_date = datetime.now() - timedelta(days=40)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE feature_usage_events SET timestamp = ? WHERE feature_key = 'gallery'",
            (old_date.isoformat(sep=" ", timespec="seconds"),),
        )

    monthly = asyncio.run(tracker.get_monthly())
    by_month = {item["month"]: item for item in monthly}

    assert by_month[datetime.now().strftime("%Y-%m")]["question"] == 1
    assert by_month[old_date.strftime("%Y-%m")]["gallery"] == 1


def test_client_sheet_contains_monthly_feature_chart(tmp_path):
    db_path = tmp_path / "metrics.db"
    _create_users_table(db_path)
    tracker = FeatureUsageTracker(str(db_path))
    asyncio.run(
        tracker.log_main_menu_selection(101, "results_request", "🧪 Запрос по результатам")
    )

    class FakeDatabase:
        def __init__(self, path):
            self.db_path = str(path)

        async def get_dau_metrics(self, _days):
            return []

        async def get_valid_requests_by_day(self, _days):
            return {}

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    exporter = MetricsExporter(FakeDatabase(db_path))
    formats = exporter._create_formats(workbook)
    asyncio.run(exporter._create_client_metrics_sheet(workbook, formats, 30))
    workbook.close()

    with zipfile.ZipFile(io.BytesIO(output.getvalue())) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        shared_strings = archive.read("xl/sharedStrings.xml").decode("utf-8")
        chart_xml = archive.read("xl/charts/chart1.xml").decode("utf-8")

    assert "👥 Клиенты" in workbook_xml
    assert "Использование функций по месяцам" in shared_strings
    assert "Запрос по результатам" in chart_xml
