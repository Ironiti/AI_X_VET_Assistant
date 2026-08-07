import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from utils.heartbeat import default_heartbeat_path, heartbeat_loop, write_heartbeat


class HeartbeatTests(unittest.TestCase):
    def test_write_heartbeat_creates_atomic_json_payload(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "telegram.json"

            write_heartbeat("Telegram", path, timestamp=1000.5, pid=42)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["bot"], "Telegram")
            self.assertEqual(payload["pid"], 42)
            self.assertEqual(payload["timestamp"], 1000.5)
            self.assertEqual(payload["status"], "running")
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_environment_overrides_default_path(self):
        with patch.dict("os.environ", {"BOT_HEARTBEAT_FILE": "custom/heartbeat.json"}):
            self.assertEqual(default_heartbeat_path("ignored.json"), Path("custom/heartbeat.json"))


class HeartbeatLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_loop_writes_immediately_and_stops(self):
        stop_event = asyncio.Event()
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {"BOT_HEARTBEAT_FILE": str(Path(temp_dir) / "bot.json")},
        ):
            task = asyncio.create_task(
                heartbeat_loop("Test Bot", "ignored.json", stop_event=stop_event, interval_seconds=5)
            )
            await asyncio.sleep(0)
            stop_event.set()
            await asyncio.wait_for(task, timeout=1)

            payload = json.loads((Path(temp_dir) / "bot.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["bot"], "Test Bot")


if __name__ == "__main__":
    unittest.main()
