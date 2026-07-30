"""Безопасное формирование Telegram-сообщений с динамическим текстом."""

from html import escape
from typing import Any


CALLBACK_MESSAGE_PREVIEW_LIMIT = 3500


def escape_telegram_html(value: Any) -> str:
    """Экранирует динамическое значение для Telegram HTML parse mode."""
    if value is None:
        return ""
    return escape(str(value), quote=False)


def _escape_telegram_html_with_limit(value: Any, max_length: int) -> str:
    """Экранирует текст, не разрезая HTML-сущность на границе лимита."""
    raw_value = "" if value is None else str(value)
    escaped_parts: list[str] = []
    escaped_length = 0

    for character in raw_value:
        escaped_character = escape(character, quote=False)
        if escaped_length + len(escaped_character) > max_length - 1:
            escaped_parts.append("…")
            break
        escaped_parts.append(escaped_character)
        escaped_length += len(escaped_character)

    return "".join(escaped_parts)


def build_callback_confirmation_html(phone: Any, message_text: Any) -> str:
    """Формирует безопасное подтверждение заявки на обратный звонок."""
    safe_message = _escape_telegram_html_with_limit(
        message_text,
        CALLBACK_MESSAGE_PREVIEW_LIMIT,
    )

    return (
        "✅ Ваша заявка на обратный звонок успешно отправлена!\n\n"
        f"📞 Телефон: {escape_telegram_html(phone)}\n"
        f"💬 Сообщение: {safe_message}\n\n"
        "Наш специалист свяжется с вами в ближайшее время."
    )
