import asyncio
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.filters import StateFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, User
from aiogram.types import Update

from bot.middleware.state_recovery_middleware import StateRecoveryMiddleware


class FakeDatabase:
    def __init__(self, user=None):
        self.user = user
        self.calls = 0

    async def get_user(self, _user_id):
        self.calls += 1
        return self.user


class FakeState:
    def __init__(self, value=None):
        self.value = value
        self.set_values = []

    async def get_state(self):
        return self.value

    async def set_state(self, value):
        self.value = value
        self.set_values.append(value)


def _message(text="AN116"):
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=42, type="private"),
        from_user=User(id=42, is_bot=False, first_name="Антон"),
        text=text,
    )


def test_missing_legacy_state_is_restored_without_a_prompt():
    async def scenario():
        database = FakeDatabase(user={"id": 42})
        state = FakeState()
        middleware = StateRecoveryMiddleware(
            database=database,
            recovery_state="questions:waiting_for_search_type",
        )
        observed = []

        async def handler(_event, _data):
            observed.append(state.value)
            return "handled"

        result = await middleware(handler, _message(), {"state": state})
        assert result == "handled"
        assert observed == ["questions:waiting_for_search_type"]
        assert state.set_values == ["questions:waiting_for_search_type"]
        assert database.calls == 1

    asyncio.run(scenario())


def test_persisted_state_passes_through_unchanged():
    async def scenario():
        database = FakeDatabase(user={"id": 42})
        state = FakeState("feedback:waiting_for_files")
        middleware = StateRecoveryMiddleware(
            database=database,
            recovery_state="questions:waiting_for_search_type",
        )

        async def handler(_event, _data):
            return "handled"

        result = await middleware(handler, _message(), {"state": state})
        assert result == "handled"
        assert state.set_values == []
        assert database.calls == 0

    asyncio.run(scenario())


def test_commands_menu_buttons_and_unregistered_users_are_not_changed():
    async def scenario():
        for text in ("/start", "🔙 Вернуться в главное меню", "✅ Отправить"):
            database = FakeDatabase(user={"id": 42})
            state = FakeState()
            middleware = StateRecoveryMiddleware(
                database=database,
                recovery_state="questions:waiting_for_search_type",
            )

            async def handler(_event, _data):
                return "handled"

            assert await middleware(handler, _message(text), {"state": state}) == "handled"
            assert state.set_values == []
            assert database.calls == 0

        database = FakeDatabase(user=None)
        state = FakeState()
        middleware = StateRecoveryMiddleware(
            database=database,
            recovery_state="questions:waiting_for_search_type",
        )
        assert await middleware(handler, _message(), {"state": state}) == "handled"
        assert state.set_values == []
        assert database.calls == 1

    asyncio.run(scenario())


def test_outer_middleware_restores_state_before_router_filters():
    async def scenario():
        dispatcher = Dispatcher(storage=MemoryStorage())
        dispatcher.message.outer_middleware(
            StateRecoveryMiddleware(
                database=FakeDatabase(user={"id": 42}),
                recovery_state="questions:waiting_for_search_type",
            )
        )
        handled = []

        async def search_handler(message: Message):
            handled.append(message.text)

        dispatcher.message.register(
            search_handler,
            StateFilter("questions:waiting_for_search_type"),
        )

        bot = Bot(token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
        try:
            await dispatcher.feed_update(
                bot,
                Update(update_id=1, message=_message("AN116")),
            )
        finally:
            await dispatcher.storage.close()
            await bot.session.close()

        assert handled == ["AN116"]

    asyncio.run(scenario())
