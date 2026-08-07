from bot.keyboards import (
    CALLBACK_BUTTON,
    CURRENT_STOPLIST_BUTTON,
    FEEDBACK_BUTTON,
    PREANALYTICS_QUESTION_BUTTON,
    RESULTS_REQUEST_BUTTON,
    SEND_SUBMISSION_BUTTON,
    TUBE_GALLERY_BUTTON,
    DOWNLOAD_FORMS_BUTTON,
    get_main_menu_kb,
    get_submission_kb,
)
from src.database.feature_usage import get_main_menu_feature


def _button_rows(markup):
    return [[button.text for button in row] for row in markup.keyboard]


def test_main_menu_contains_all_seven_user_functions():
    assert _button_rows(get_main_menu_kb()) == [
        [PREANALYTICS_QUESTION_BUTTON, RESULTS_REQUEST_BUTTON],
        [TUBE_GALLERY_BUTTON, DOWNLOAD_FORMS_BUTTON],
        [CALLBACK_BUTTON, FEEDBACK_BUTTON],
        [CURRENT_STOPLIST_BUTTON],
    ]


def test_submission_menu_has_explicit_send_and_draft_controls():
    rows = _button_rows(get_submission_kb())
    assert rows[0] == [SEND_SUBMISSION_BUTTON]
    assert rows[1] == ["↩️ Удалить файл", "🗑 Очистить"]
    assert rows[2] == ["🔙 Вернуться в главное меню"]


def test_old_and_new_button_names_are_counted_together():
    expected = {
        "🔬 Задать вопрос": "question",
        "🔬 Вопрос по преаналитике": "question",
        "🧪 Запрос по результатам": "results_request",
        "🖼️ Галерея пробирок": "gallery",
        "📄 Скачать бланки": "blanks",
        "📞 Связь с лабораторией": "laboratory_contact",
        "📞 Заказать звонок": "laboratory_contact",
        "💡 Предложение/жалоба": "feedback",
        "💡 Предложение": "feedback",
        "⚠️ Жалоба": "feedback",
        "💬 Жалобы и предложения": "feedback",
        "📋 Стоп-лист": "stoplist",
        "📋 Актуальный стоп-лист": "stoplist",
    }
    assert {text: get_main_menu_feature(text) for text in expected} == expected
