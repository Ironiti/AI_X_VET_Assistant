import asyncio

from src.database.models import Database


def test_admin_blank_is_shared_with_analysis_and_can_be_updated(tmp_path):
    async def scenario():
        database = Database(str(tmp_path / "blanks.db"))
        blank_id = await database.add_blank_document(
            title="Направление на анализ крови",
            file_id="old-file-id",
            added_by=1,
        )

        blank = await database.find_blank_document_by_title("анализ крови")
        cached = await database.get_blank_file_id("Направление на анализ крови.pdf")
        assert blank["file_id"] == "old-file-id"
        assert cached["file_id"] == "old-file-id"

        assert await database.update_blank_document_file(blank_id, "new-file-id")

        blank = await database.get_blank_document(blank_id)
        cached = await database.get_blank_file_id("Направление на анализ крови.pdf")
        assert blank["file_id"] == "new-file-id"
        assert cached["file_id"] == "new-file-id"

    asyncio.run(scenario())
