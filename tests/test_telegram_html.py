from bot.telegram_html import (
    CALLBACK_MESSAGE_PREVIEW_LIMIT,
    build_callback_confirmation_html,
    escape_telegram_html,
)


def test_escape_telegram_html_handles_laboratory_comparison():
    text = "Staphylococcus epidermidis, <=10*3 КОЕ/мл & контроль >5"

    assert escape_telegram_html(text) == (
        "Staphylococcus epidermidis, &lt;=10*3 КОЕ/мл "
        "&amp; контроль &gt;5"
    )


def test_callback_confirmation_escapes_all_dynamic_values():
    confirmation = build_callback_confirmation_html(
        "+375 <29>",
        "Результат <=10*3 КОЕ/мл, <b>не тег</b> & повторить посев",
    )

    assert "📞 Телефон: +375 &lt;29&gt;" in confirmation
    assert "Результат &lt;=10*3 КОЕ/мл" in confirmation
    assert "&lt;b&gt;не тег&lt;/b&gt;" in confirmation
    assert "&amp; повторить посев" in confirmation
    assert "<=10*3" not in confirmation
    assert "<b>" not in confirmation


def test_callback_confirmation_limits_long_preview():
    confirmation = build_callback_confirmation_html(
        "+375291234567",
        "<" * (CALLBACK_MESSAGE_PREVIEW_LIMIT + 1000),
    )

    assert len(confirmation) < 4096
    assert confirmation.count("&lt;") < CALLBACK_MESSAGE_PREVIEW_LIMIT
    assert "&l…" not in confirmation
    assert "…" in confirmation
