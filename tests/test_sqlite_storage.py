import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import StorageKey

from bot.storage.sqlite_storage import SQLiteStorage


def _key(**overrides):
    values = {
        "bot_id": 1,
        "chat_id": 2,
        "user_id": 3,
        "thread_id": None,
        "business_connection_id": None,
        "destiny": "default",
    }
    values.update(overrides)
    return StorageKey(**values)


def test_state_and_data_survive_storage_recreation():
    async def scenario(path: Path):
        first = SQLiteStorage(path)
        await first.set_state(_key(), "questions:waiting")
        await first.set_data(_key(), {"files": ["a.pdf"], "step": 2})
        await first.close()

        second = SQLiteStorage(path)
        assert await second.get_state(_key()) == "questions:waiting"
        assert await second.get_data(_key()) == {"files": ["a.pdf"], "step": 2}
        await second.close()

    with TemporaryDirectory() as directory:
        asyncio.run(scenario(Path(directory) / "fsm.db"))


def test_state_object_none_and_update_data():
    async def scenario(path: Path):
        storage = SQLiteStorage(path)
        key = _key()
        state = State("waiting")

        await storage.set_state(key, state)
        assert await storage.get_state(key) == state.state

        await storage.set_data(key, {"first": 1})
        updated = await storage.update_data(key, {"second": {"value": 2}})
        assert updated == {"first": 1, "second": {"value": 2}}
        assert await storage.get_data(key) == updated

        await storage.set_state(key, None)
        assert await storage.get_state(key) is None
        assert await storage.get_data(key) == updated
        await storage.close()

    with TemporaryDirectory() as directory:
        asyncio.run(scenario(Path(directory) / "fsm.db"))


def test_storage_keys_do_not_collide():
    async def scenario(path: Path):
        storage = SQLiteStorage(path)
        first = _key(thread_id=10, business_connection_id="a", destiny="one")
        second = _key(thread_id=11, business_connection_id="b", destiny="two")

        await storage.set_state(first, "first")
        await storage.set_state(second, "second")
        await storage.set_data(first, {"value": 1})
        await storage.set_data(second, {"value": 2})

        assert await storage.get_state(first) == "first"
        assert await storage.get_state(second) == "second"
        assert await storage.get_data(first) == {"value": 1}
        assert await storage.get_data(second) == {"value": 2}
        await storage.close()

    with TemporaryDirectory() as directory:
        asyncio.run(scenario(Path(directory) / "fsm.db"))
