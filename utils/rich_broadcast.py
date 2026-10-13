"""Utilities for Telegram rich-message broadcasts."""

from aiogram.types import (
    InputMediaAnimation,
    InputMediaAudio,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaVoiceNote,
    InputRichMessage,
    InputRichMessageMedia,
)

RICH_MARKDOWN_MAX_CHARS = 32_768
RICH_BROADCAST_HEADER = "**📢 Сообщение от группы техподдержки**"


def is_markdown_filename(file_name: str | None) -> bool:
    """Return True only for files with the .md extension."""
    return bool(file_name and file_name.lower().endswith(".md"))


def build_rich_broadcast_markdown(markdown: str) -> str:
    """Add the standard broadcast header and enforce Telegram limits."""
    content = markdown.strip()
    if not content:
        raise ValueError("Markdown-файл пуст.")

    result = f"{RICH_BROADCAST_HEADER}\n\n{content}"
    if len(result) > RICH_MARKDOWN_MAX_CHARS:
        raise ValueError(
            f"Сообщение слишком длинное. Максимум — {RICH_MARKDOWN_MAX_CHARS} символов."
        )
    return result


def decode_markdown_file(raw_content: bytes) -> str:
    """Decode a UTF-8 Markdown file and validate its resulting rich message."""
    try:
        markdown = raw_content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Файл должен быть сохранён в кодировке UTF-8.") from exc

    markdown = markdown.strip()
    build_rich_broadcast_markdown(markdown)
    return markdown


def build_rich_broadcast_message(
    markdown: str | None,
    media_items: list[dict] | None = None,
) -> InputRichMessage:
    """Build one Telegram rich message with media above the Markdown text."""
    content = (markdown or "").strip()
    body = build_rich_broadcast_markdown(content) if content else RICH_BROADCAST_HEADER
    items = media_items or []

    rich_media: list[InputRichMessageMedia] = []
    media_blocks: list[str] = []
    for index, item in enumerate(items):
        media_id = f"broadcast_media_{index}"
        media_type = item.get("type")
        file_id = item.get("file_id")
        if media_type == "photo":
            media = InputMediaPhoto(media=file_id)
            link_type = "photo"
        elif media_type == "video":
            media = InputMediaVideo(media=file_id)
            link_type = "video"
        elif media_type == "animation":
            media = InputMediaAnimation(media=file_id)
            link_type = "video"
        elif media_type == "audio":
            media = InputMediaAudio(media=file_id)
            link_type = "audio"
        elif media_type == "voice":
            media = InputMediaVoiceNote(media=file_id)
            link_type = "audio"
        else:
            raise ValueError(f"Неподдерживаемый тип медиа: {media_type}")

        rich_media.append(InputRichMessageMedia(id=media_id, media=media))
        media_blocks.append(f"![](tg://{link_type}?id={media_id})")

    if not media_blocks:
        return InputRichMessage(markdown=body)

    media_markdown = "\n\n".join(media_blocks)

    return InputRichMessage(
        markdown=f"{media_markdown}\n\n{body}",
        media=rich_media,
    )
