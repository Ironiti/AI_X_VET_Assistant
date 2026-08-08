import asyncio
from types import SimpleNamespace

from bot.middleware.menu_refresh_middleware import MenuRefreshMiddleware


class FakeDatabase:
    def __init__(self, user=None, version=None):
        self.user = user
        self.version = version
        self.saved = []

    async def get_user(self, _user_id):
        return self.user

    async def get_user_menu_version(self, _user_id):
        return self.version

    async def set_user_menu_version(self, user_id, version):
        self.version = version
        self.saved.append((user_id, version))


class FakeState:
    def __init__(self, value=None):
        self.value = value

    async def get_state(self):
        return self.value


class FakeMessage:
    def __init__(self, text="тест", user_id=42):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id) if user_id is not None else None
        self.answers = []

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


async def passthrough(_event, _data):
    return "handled"


def test_refreshes_stale_menu_once_when_user_is_idle():
    database = FakeDatabase(user={"role": "user"})
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage()

    result = asyncio.run(middleware(passthrough, message, {"state": FakeState()}))

    assert result == "handled"
    assert message.answers[0][0] == "Меню обновлено."
    assert database.saved == [(42, "2")]

    asyncio.run(middleware(passthrough, message, {"state": FakeState()}))
    assert len(message.answers) == 1


def test_refresh_is_sent_before_the_requested_idle_action():
    database = FakeDatabase(user={"role": "user"})
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage("🖼️ Галерея пробирок")
    order = []

    original_answer = message.answer

    async def tracked_answer(text, reply_markup=None):
        order.append(text)
        await original_answer(text, reply_markup)

    async def open_gallery(_event, _data):
        order.append("Галерея открыта")

    message.answer = tracked_answer
    asyncio.run(middleware(open_gallery, message, {"state": FakeState()}))

    assert order == ["Меню обновлено.", "Галерея открыта"]


def test_does_not_replace_keyboard_during_active_form():
    database = FakeDatabase(user={"role": "user"})
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage()

    asyncio.run(middleware(passthrough, message, {"state": FakeState("form:phone")}))

    assert message.answers == []
    assert database.saved == []


def test_plain_start_marks_version_without_duplicate_message():
    database = FakeDatabase(user={"role": "admin"})
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage("/start")

    asyncio.run(middleware(passthrough, message, {"state": FakeState()}))

    assert message.answers == []
    assert database.saved == [(42, "2")]


def test_start_deep_link_sends_menu_instead_of_claiming_it_silently():
    database = FakeDatabase(user={"role": "user"})
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage("/start blank_17")

    asyncio.run(middleware(passthrough, message, {"state": FakeState()}))

    assert message.answers[0][0] == "Меню обновлено."
    assert database.saved == [(42, "2")]


def test_start_with_bot_username_does_not_duplicate_menu():
    database = FakeDatabase(user={"role": "user"})
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage("/start@VetUnionBot")

    asyncio.run(middleware(passthrough, message, {"state": FakeState()}))

    assert message.answers == []
    assert database.saved == [(42, "2")]


def test_return_to_main_menu_is_not_duplicated():
    database = FakeDatabase(user={"role": "user"})
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage("🔙 Вернуться в главное меню")

    asyncio.run(middleware(passthrough, message, {"state": FakeState()}))

    assert message.answers == []
    assert database.saved == [(42, "2")]


def test_return_button_is_not_duplicated_even_without_saved_fsm_state():
    database = FakeDatabase(user={"role": "user"})
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage("🏠 В главное меню")

    asyncio.run(middleware(passthrough, message, {"state": FakeState()}))

    assert message.answers == []
    assert database.saved == [(42, "2")]


def test_finish_dialog_is_not_duplicated():
    database = FakeDatabase(user={"role": "user"})
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage("❌ Завершить диалог")

    asyncio.run(middleware(passthrough, message, {"state": FakeState()}))

    assert message.answers == []
    assert database.saved == [(42, "2")]


def test_registration_completion_marks_menu_without_duplicate_message():
    database = FakeDatabase(user=None)
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage("готово")

    async def finish_registration(event, _data):
        database.user = {"role": "user"}
        await event.answer("Регистрация завершена.", reply_markup="main-menu")
        return "registered"

    result = asyncio.run(
        middleware(finish_registration, message, {"state": FakeState()})
    )

    assert result == "registered"
    assert message.answers == [("Регистрация завершена.", "main-menu")]
    assert database.saved == [(42, "2")]


def test_ignores_unregistered_user():
    database = FakeDatabase(user=None)
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage()

    asyncio.run(middleware(passthrough, message, {"state": FakeState()}))

    assert message.answers == []
    assert database.saved == []


def test_ignores_message_without_sender():
    database = FakeDatabase(user={"role": "user"})
    middleware = MenuRefreshMiddleware(database=database, menu_version="2")
    message = FakeMessage(user_id=None)

    result = asyncio.run(middleware(passthrough, message, {"state": FakeState()}))

    assert result == "handled"
    assert message.answers == []
    assert database.saved == []
