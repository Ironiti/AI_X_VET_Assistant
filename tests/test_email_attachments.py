import importlib.util
from email.mime.multipart import MIMEMultipart
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest


fake_config = ModuleType("config")
fake_config.EMAIL_HOST = "smtp.example.test"
fake_config.EMAIL_PORT = 587
fake_config.EMAIL_LOGIN = "bot@example.test"
fake_config.EMAIL_PASSWORD = "password"
fake_config.EMAIL_TO = "lab@example.test"
fake_aiosmtplib = ModuleType("aiosmtplib")
fake_aiosmtplib.SMTPException = RuntimeError
original_config = sys.modules.get("config")
original_aiosmtplib = sys.modules.get("aiosmtplib")
sys.modules["config"] = fake_config
sys.modules["aiosmtplib"] = fake_aiosmtplib
try:
    module_path = Path(__file__).resolve().parents[1] / "utils" / "email_sender.py"
    spec = importlib.util.spec_from_file_location("tg_email_sender_test", module_path)
    email_sender = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(email_sender)
finally:
    if original_config is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = original_config
    if original_aiosmtplib is None:
        sys.modules.pop("aiosmtplib", None)
    else:
        sys.modules["aiosmtplib"] = original_aiosmtplib


class EmailAttachmentTests(unittest.TestCase):
    def test_actual_file_bytes_are_added_as_mime_attachment(self):
        message = MIMEMultipart("mixed")
        attachment = SimpleNamespace(
            data=b"\x00actual-user-file\xff",
            filename="результат.pdf",
            content_type="application/pdf",
        )

        email_sender._attach_email_file(message, attachment)

        self.assertEqual(len(message.get_payload()), 1)
        part = message.get_payload()[0]
        self.assertEqual(part.get_content_type(), "application/pdf")
        self.assertEqual(part.get_filename(), "результат.pdf")
        self.assertEqual(part.get_payload(decode=True), attachment.data)
        self.assertEqual(part.get_content_disposition(), "attachment")


if __name__ == "__main__":
    unittest.main()
