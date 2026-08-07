"""Helpers for turning Telegram contact messages into storable feedback payloads."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import mimetypes
from pathlib import Path
import re
from typing import Any


MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
MAX_ATTACHMENT_COUNT = 5
MAX_TOTAL_ATTACHMENT_BYTES = 18 * 1024 * 1024


SUPPORTED_ATTACHMENT_HINT = (
    "Текст и файлы можно отправлять по очереди.\n"
    "Через 📎 можно добавить до 5 файлов: фото, PDF, Word, Excel, аудио или видео.\n"
    "Один файл — до 15 МБ, все файлы вместе — до 18 МБ."
)


@dataclass(frozen=True)
class EmailAttachment:
    """Downloaded user file ready to be added to an email."""

    data: bytes
    filename: str
    content_type: str


class AttachmentDownloadError(RuntimeError):
    """Telegram attachment could not be downloaded for email delivery."""


class AttachmentTooLargeError(AttachmentDownloadError):
    """Telegram attachment exceeds the configured email-safe size."""


def extract_message_text(message: Any) -> str:
    """Return user text or media caption without depending on a specific content type."""
    return (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()


def extract_media_info(message: Any) -> tuple[str | None, str | None, str]:
    """Extract a storable Telegram media reference for feedback/admin review."""
    if getattr(message, "photo", None):
        photo = message.photo[-1]
        return "photo", photo.file_id, "фото"
    if getattr(message, "document", None):
        document = message.document
        filename = getattr(document, "file_name", "") or "документ"
        return "document", document.file_id, f"документ: {filename}"
    if getattr(message, "voice", None):
        return "voice", message.voice.file_id, "голосовое сообщение"
    if getattr(message, "audio", None):
        return "audio", message.audio.file_id, "аудио"
    if getattr(message, "video", None):
        return "video", message.video.file_id, "видео"
    return None, None, ""


def _extract_media_object(message: Any) -> tuple[str | None, Any | None]:
    if getattr(message, "photo", None):
        return "photo", message.photo[-1]
    for media_type in ("document", "voice", "audio", "video"):
        media = getattr(message, media_type, None)
        if media is not None:
            return media_type, media
    return None, None


def _safe_filename(filename: str) -> str:
    filename = Path(filename).name.strip()
    filename = re.sub(r"[^\w.()\- ]+", "_", filename, flags=re.UNICODE)
    return filename[:180] or "attachment.bin"


def _attachment_metadata(media_type: str, media: Any) -> tuple[str, str]:
    default_names = {
        "photo": "photo.jpg",
        "document": "document.bin",
        "voice": "voice.ogg",
        "audio": "audio.mp3",
        "video": "video.mp4",
    }
    filename = _safe_filename(getattr(media, "file_name", None) or default_names[media_type])
    content_type = getattr(media, "mime_type", None)
    if not content_type:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return filename, content_type


def build_attachment_reference(message: Any) -> dict[str, Any] | None:
    """Build a small FSM-safe reference without downloading the Telegram file."""
    media_type, media = _extract_media_object(message)
    if media is None:
        return None

    declared_size = getattr(media, "file_size", None)
    if declared_size is not None and declared_size > MAX_ATTACHMENT_BYTES:
        raise AttachmentTooLargeError("Размер вложения превышает 15 МБ.")

    filename, content_type = _attachment_metadata(media_type, media)
    _, file_id, label = extract_media_info(message)
    return {
        "media_type": media_type,
        "file_id": file_id,
        "file_size": declared_size,
        "filename": filename,
        "content_type": content_type,
        "label": label,
    }


async def download_attachment_reference(bot: Any, reference: dict[str, Any]) -> EmailAttachment:
    """Download a previously collected Telegram attachment reference."""
    try:
        telegram_file = await bot.get_file(reference["file_id"])
        file_path = getattr(telegram_file, "file_path", None)
        if not file_path:
            raise AttachmentDownloadError("Telegram не вернул путь к файлу.")
        buffer = BytesIO()
        await bot.download_file(file_path, destination=buffer)
        data = buffer.getvalue()
    except AttachmentDownloadError:
        raise
    except Exception as exc:
        raise AttachmentDownloadError("Не удалось скачать вложение из Telegram.") from exc

    if len(data) > MAX_ATTACHMENT_BYTES:
        raise AttachmentTooLargeError("Размер вложения превышает 15 МБ.")
    if not data:
        raise AttachmentDownloadError("Telegram вернул пустой файл.")

    return EmailAttachment(
        data=data,
        filename=reference["filename"],
        content_type=reference["content_type"],
    )


async def download_message_attachment(message: Any) -> EmailAttachment | None:
    """Download the single supported Telegram attachment into memory."""
    reference = build_attachment_reference(message)
    if reference is None:
        return None

    bot = getattr(message, "bot", None)
    if bot is None:
        raise AttachmentDownloadError("Не удалось получить доступ к файлу Telegram.")
    return await download_attachment_reference(bot, reference)


def build_user_submission(message: Any) -> tuple[str, str | None, str | None, str]:
    text = extract_message_text(message)
    media_type, media_file_id, media_label = extract_media_info(message)
    if not text and media_label:
        text = f"Пользователь отправил {media_label} без текстового комментария."
    return text, media_type, media_file_id, media_label


def build_admin_message(text: str, media_label: str) -> str:
    if not media_label:
        return text
    return f"{text}\n\nВложение: {media_label} (файл прикреплён к письму)"
