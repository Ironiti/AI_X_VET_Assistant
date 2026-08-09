"""Utilities for Telegram rich-message broadcasts."""

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
