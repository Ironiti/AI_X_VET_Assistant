import unittest
from types import SimpleNamespace

from bot.feedback_payload import (
    AttachmentTooLargeError,
    build_attachment_reference,
    build_admin_message,
    build_user_submission,
    download_message_attachment,
    extract_media_info,
    extract_message_text,
    MAX_ATTACHMENT_BYTES,
)


class FeedbackSubmissionTests(unittest.TestCase):
    def test_extract_message_text_prefers_text(self):
        message = SimpleNamespace(text="  вопрос по анализу  ", caption="caption")

        self.assertEqual(extract_message_text(message), "вопрос по анализу")

    def test_extract_message_text_uses_caption_for_media(self):
        message = SimpleNamespace(text=None, caption="  фото пробирки  ")

        self.assertEqual(extract_message_text(message), "фото пробирки")

    def test_extract_media_info_supports_document(self):
        message = SimpleNamespace(
            text=None,
            caption=None,
            photo=None,
            document=SimpleNamespace(file_id="doc-file-id", file_name="request.xlsx"),
            voice=None,
            audio=None,
            video=None,
        )

        media_type, media_file_id, media_label = extract_media_info(message)

        self.assertEqual(media_type, "document")
        self.assertEqual(media_file_id, "doc-file-id")
        self.assertIn("request.xlsx", media_label)

    def test_attachment_reference_is_safe_to_store_in_fsm(self):
        message = SimpleNamespace(
            photo=None,
            document=SimpleNamespace(
                file_id="doc-file-id",
                file_name="result.pdf",
                file_size=1024,
                mime_type="application/pdf",
            ),
            voice=None,
            audio=None,
            video=None,
        )

        reference = build_attachment_reference(message)

        self.assertEqual(reference["file_id"], "doc-file-id")
        self.assertEqual(reference["filename"], "result.pdf")
        self.assertEqual(reference["file_size"], 1024)
        self.assertTrue(all(
            value is None or isinstance(value, (str, int))
            for value in reference.values()
        ))

    def test_build_user_submission_accepts_voice_without_text(self):
        message = SimpleNamespace(
            text=None,
            caption=None,
            photo=None,
            document=None,
            voice=SimpleNamespace(file_id="voice-file-id"),
            audio=None,
            video=None,
        )

        text, media_type, media_file_id, media_label = build_user_submission(message)

        self.assertIn("голосовое сообщение", text)
        self.assertEqual(media_type, "voice")
        self.assertEqual(media_file_id, "voice-file-id")
        self.assertEqual(media_label, "голосовое сообщение")

    def test_file_caption_is_used_as_request_text(self):
        message = SimpleNamespace(
            text=None,
            caption="  Проверьте показатель АЛТ  ",
            photo=None,
            document=SimpleNamespace(file_id="doc-file-id", file_name="result.pdf"),
            voice=None,
            audio=None,
            video=None,
        )

        text, media_type, media_file_id, media_label = build_user_submission(message)

        self.assertEqual(text, "Проверьте показатель АЛТ")
        self.assertEqual(media_type, "document")
        self.assertEqual(media_file_id, "doc-file-id")
        self.assertIn("result.pdf", media_label)

    def test_build_admin_message_includes_attachment_reference(self):
        text = build_admin_message("Нужен звонок", "документ: request.xlsx")

        self.assertIn("Нужен звонок", text)
        self.assertIn("Вложение: документ: request.xlsx", text)
        self.assertIn("файл прикреплён к письму", text)
        self.assertNotIn("file-id", text)


class AttachmentDownloadTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _message(media_type, media):
        fields = {
            "photo": None,
            "document": None,
            "voice": None,
            "audio": None,
            "video": None,
        }
        fields[media_type] = [media] if media_type == "photo" else media

        class Bot:
            async def get_file(self, file_id):
                self.requested_file_id = file_id
                return SimpleNamespace(file_path="telegram/path")

            async def download_file(self, file_path, destination):
                self.downloaded_path = file_path
                destination.write(b"real-file-bytes")

        return SimpleNamespace(bot=Bot(), **fields)

    async def test_downloads_real_bytes_and_preserves_metadata_for_supported_media(self):
        cases = (
            ("photo", SimpleNamespace(file_id="p", file_size=10), "photo.jpg", "image/jpeg"),
            ("document", SimpleNamespace(file_id="d", file_size=10, file_name="report.pdf", mime_type="application/pdf"), "report.pdf", "application/pdf"),
            ("document", SimpleNamespace(file_id="w", file_size=10, file_name="request.docx", mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"), "request.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("document", SimpleNamespace(file_id="e", file_size=10, file_name="data.xlsx", mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"), "data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("voice", SimpleNamespace(file_id="v", file_size=10, mime_type="audio/ogg"), "voice.ogg", "audio/ogg"),
            ("audio", SimpleNamespace(file_id="a", file_size=10, file_name="note.mp3", mime_type="audio/mpeg"), "note.mp3", "audio/mpeg"),
            ("video", SimpleNamespace(file_id="x", file_size=10, file_name="tube.mp4", mime_type="video/mp4"), "tube.mp4", "video/mp4"),
        )
        for media_type, media, expected_name, expected_type in cases:
            with self.subTest(media_type=media_type):
                attachment = await download_message_attachment(self._message(media_type, media))
                self.assertEqual(attachment.data, b"real-file-bytes")
                self.assertEqual(attachment.filename, expected_name)
                self.assertEqual(attachment.content_type, expected_type)

    async def test_rejects_declared_file_over_application_limit_before_download(self):
        media = SimpleNamespace(file_id="big", file_size=MAX_ATTACHMENT_BYTES + 1, file_name="big.pdf")
        with self.assertRaises(AttachmentTooLargeError):
            await download_message_attachment(self._message("document", media))


if __name__ == "__main__":
    unittest.main()
