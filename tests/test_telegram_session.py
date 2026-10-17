import asyncio
import logging
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientConnectionError, ClientResponseError, web
from aiohttp_socks import ProxyError
from aiogram import Bot
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter, TelegramUnauthorizedError,
)
from aiogram.methods import GetMe, GetUpdates, SendMessage

from bot.telegram_session import (
    ConnectionSession, FailoverSession, TransportFailure, create_telegram_session,
)


class FakeSession:
    def __init__(self, *, proxy=None, **kwargs):
        self.proxy = proxy
        self.responses = []
        self.requests = []
        self.chunks = [b"file"]
        self.closed = False

    async def make_request(self, bot, method, timeout=None):
        self.requests.append((method, timeout))
        result = self.responses.pop(0) if self.responses else "ok"
        if isinstance(result, Exception):
            raise result
        if asyncio.isfuture(result):
            return await result
        return result

    async def stream_content(self, *args, **kwargs):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    async def close(self):
        self.closed = True


class FailoverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 100
        self.session = FailoverSession(
            ["socks5://primary:8000", "socks5://reserve:8000"],
            session_factory=FakeSession, clock=lambda: self.now,
        )
        self.method = SendMessage(chat_id=42, text="answer")
        self.bot = SimpleNamespace(token="not-a-real-token")

    async def asyncTearDown(self):
        await self.session.close()

    def network_failure(self, *, started=False, method=None):
        return TransportFailure(method or self.method, TimeoutError(), request_started=started)

    async def test_same_send_retried_on_reserve_before_headers(self):
        self.session.routes[0].session.responses = [self.network_failure()]
        result = await self.session.make_request(self.bot, self.method, timeout=71)
        self.assertEqual(result, "ok")
        self.assertEqual(self.session.routes[1].session.requests, [(self.method, 71)])
        self.assertEqual(self.session._active, 1)

    async def test_all_proxies_fail_then_direct_succeeds(self):
        for route in self.session.routes[:2]:
            route.session.responses = [self.network_failure()]
        self.assertEqual(await self.session.make_request(self.bot, self.method), "ok")
        self.assertEqual(self.session._active, 2)

    async def test_successful_route_is_sticky_and_dead_route_skipped(self):
        self.session.routes[0].session.responses = [self.network_failure()]
        await self.session.make_request(self.bot, self.method)
        await self.session.make_request(self.bot, self.method)
        self.assertEqual(len(self.session.routes[0].session.requests), 1)
        self.assertEqual(len(self.session.routes[1].session.requests), 2)

    async def test_each_route_tried_once_and_all_cooling_only_one_probe(self):
        for route in self.session.routes:
            route.session.responses = [self.network_failure(), self.network_failure()]
        with self.assertRaises(TransportFailure):
            await self.session.make_request(self.bot, self.method)
        self.assertEqual([len(r.session.requests) for r in self.session.routes], [1, 1, 1])
        with self.assertRaises(TransportFailure):
            await self.session.make_request(self.bot, self.method)
        self.assertEqual(sum(len(r.session.requests) for r in self.session.routes), 4)

    async def test_cooldown_allows_recovered_route(self):
        for route in self.session.routes:
            route.session.responses = [self.network_failure()]
        with self.assertRaises(TransportFailure):
            await self.session.make_request(self.bot, self.method)
        self.now += 61
        self.assertEqual(await self.session.make_request(self.bot, self.method), "ok")

    async def test_uncertain_send_not_duplicated_but_next_call_uses_reserve(self):
        self.session.routes[0].session.responses = [self.network_failure(started=True)]
        with self.assertRaises(TransportFailure):
            await self.session.make_request(self.bot, self.method)
        self.assertEqual(len(self.session.routes[1].session.requests), 0)
        self.assertEqual(await self.session.make_request(self.bot, self.method), "ok")
        self.assertEqual(len(self.session.routes[1].session.requests), 1)

    async def test_read_timeout_can_retry_after_headers(self):
        method = GetUpdates(timeout=30)
        self.session.routes[0].session.responses = [self.network_failure(started=True, method=method)]
        self.assertEqual(await self.session.make_request(self.bot, method, timeout=90), "ok")
        self.assertEqual(self.session.routes[1].session.requests, [(method, 90)])

    async def test_api_errors_never_retried(self):
        errors = [
            TelegramBadRequest(method=self.method, message="bad request"),
            TelegramUnauthorizedError(method=self.method, message="unauthorized"),
            TelegramForbiddenError(method=self.method, message="forbidden"),
            TelegramRetryAfter(method=self.method, message="wait", retry_after=30),
        ]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                self.session.routes[0].session.responses = [error]
                with self.assertRaises(type(error)):
                    await self.session.make_request(self.bot, self.method)
                self.assertEqual(self.session._active, 0)
                self.assertEqual(self.session.routes[1].session.requests, [])

    async def test_cancelled_request_does_not_switch(self):
        future = asyncio.get_running_loop().create_future()
        future.cancel()
        self.session.routes[0].session.responses = [future]
        with self.assertRaises(asyncio.CancelledError):
            await self.session.make_request(self.bot, self.method)
        self.assertEqual(self.session._active, 0)

    async def test_stale_success_does_not_override_newer_failover(self):
        future = asyncio.get_running_loop().create_future()
        self.session.routes[0].session.responses = [future, self.network_failure()]
        old_call = asyncio.create_task(self.session.make_request(self.bot, self.method))
        await asyncio.sleep(0)
        await self.session.make_request(self.bot, self.method)
        future.set_result("old success")
        await old_call
        self.assertEqual(self.session._active, 1)

    async def test_download_fails_over_before_first_chunk(self):
        self.session.routes[0].session.chunks = [ClientConnectionError()]
        chunks = [chunk async for chunk in self.session.stream_content("https://example.invalid/file")]
        self.assertEqual(chunks, [b"file"])
        self.assertEqual(self.session._active, 1)

    async def test_partial_download_is_not_replayed(self):
        self.session.routes[0].session.chunks = [b"first", ClientConnectionError()]
        chunks = []
        with self.assertRaises(ConnectionError):
            async for chunk in self.session.stream_content("https://example.invalid/file"):
                chunks.append(chunk)
        self.assertEqual(chunks, [b"first"])

    async def test_proxy_auth_error_download_fails_over(self):
        self.session.routes[0].session.chunks = [ProxyError("credentials rejected")]
        chunks = [chunk async for chunk in self.session.stream_content("https://example.invalid/file")]
        self.assertEqual(chunks, [b"file"])

    async def test_download_error_does_not_include_sensitive_url(self):
        for route in self.session.routes:
            route.session.chunks = [ClientConnectionError("secret-token-in-url")]
        with self.assertRaises(ConnectionError) as error:
            async for _ in self.session.stream_content("https://example.invalid/file"):
                pass
        self.assertNotIn("secret-token", str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)

    async def test_download_http_error_not_retried(self):
        self.session.routes[0].session.chunks = [ValueError("invalid request")]
        with self.assertRaises(ValueError):
            async for _ in self.session.stream_content("bad url"):
                pass
        self.assertEqual(self.session._active, 0)

    async def test_download_http_404_is_sanitized_without_switching(self):
        self.session.routes[0].session.chunks = [ClientResponseError(
            SimpleNamespace(real_url="https://example.invalid/secret-token"), (), status=404,
        )]
        with self.assertRaisesRegex(ConnectionError, "HTTP error .404.") as error:
            async for _ in self.session.stream_content("unused"):
                pass
        self.assertNotIn("secret-token", str(error.exception))
        self.assertTrue(error.exception.__suppress_context__)
        self.assertEqual(self.session._active, 0)

    async def test_close_closes_every_route(self):
        await self.session.close()
        self.assertTrue(all(r.session.closed for r in self.session.routes))

    async def test_no_secrets_in_failover_logs(self):
        self.session.routes[0].session.responses = [self.network_failure()]
        with self.assertLogs("bot.telegram_session", level=logging.WARNING) as logs:
            await self.session.make_request(self.bot, self.method)
        output = " ".join(logs.output)
        self.assertNotIn(self.bot.token, output)
        self.assertNotIn("socks5://", output)

    async def test_base_session_request_middleware_preserved(self):
        calls = []
        async def middleware(make_request, bot, method):
            calls.append(method)
            return await make_request(bot, method)
        self.session.middleware.register(middleware)
        self.assertEqual(await self.session(self.bot, self.method), "ok")
        self.assertEqual(calls, [self.method])


class FactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_env_reserves_extras_deduplicated_and_direct_last(self):
        with patch.dict(os.environ, {
            "TELEGRAM_RESERVE_PROXY_URL": "socks5://reserve:8000",
            "TELEGRAM_EXTRA_PROXY_URLS": "socks5://extra:8000, socks5://reserve:8000\n",
        }, clear=True):
            session = create_telegram_session("socks5://primary:8000")
        self.assertEqual(len(session.routes), 4)
        self.assertEqual(session.routes[-1].name, "direct")
        await session.close()

    async def test_no_proxy_is_direct_only(self):
        session = FailoverSession([], session_factory=FakeSession)
        self.assertEqual([r.name for r in session.routes], ["direct"])
        await session.close()

    async def test_legacy_reserve_and_empty_entries(self):
        with patch.dict(os.environ, {"RESERVE_PROXY_URL": "socks5://legacy:8000"}, clear=True):
            session = create_telegram_session(None)
        self.assertEqual(len(session.routes), 2)
        await session.close()

    def test_connect_timeout_does_not_shorten_long_poll_or_upload(self):
        timeout = ConnectionSession.connection_timeout(90)
        self.assertEqual(timeout.total, 90)
        self.assertEqual(timeout.connect, 5)
        self.assertEqual(timeout.sock_connect, 5)
        self.assertIsNone(timeout.sock_read)


class RealTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.received = []
        self.abort = False
        async def endpoint(request):
            self.received.append(request.match_info["method"])
            if self.abort:
                request.transport.close()
                return web.Response()
            method = request.match_info["method"]
            result = {"id": 123, "is_bot": True, "first_name": "Test", "username": "testbot"}
            if method == "sendMessage":
                result = {"message_id": 1, "date": 1, "chat": {"id": 42, "type": "private"}, "text": "answer"}
            return web.json_response({"ok": True, "result": result})
        app = web.Application()
        app.router.add_post("/bot{token}/{method}", endpoint)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        api = TelegramAPIServer.from_base(f"http://127.0.0.1:{port}")
        self.session = FailoverSession(["socks5://127.0.0.1:1"], api=api)
        self.bot = Bot(token="123456:TEST_TOKEN", session=self.session)

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()

    async def test_actual_dead_socks_proxy_fails_over_and_send_is_delivered_once(self):
        message = await self.bot.send_message(42, "answer")
        self.assertEqual(message.message_id, 1)
        self.assertEqual(self.received, ["sendMessage"])
        self.assertEqual(self.session._active, 1)
        self.assertTrue((await self.bot.get_me()).is_bot)

    async def test_response_lost_after_headers_does_not_duplicate_send(self):
        self.abort = True
        self.session._active = 1
        with self.assertRaises(TransportFailure) as error:
            await self.bot.send_message(42, "answer")
        self.assertTrue(error.exception.request_started)
        self.assertEqual(self.received, ["sendMessage"])

    async def test_proxy_auth_error_uses_direct_connection(self):
        http = SimpleNamespace(post=Mock(side_effect=ProxyError("credentials rejected")))
        with patch.object(self.session.routes[0].session, "create_session", AsyncMock(return_value=http)):
            self.assertTrue((await self.bot.get_me()).is_bot)
        self.assertEqual(self.received, ["getMe"])

    @unittest.skipIf(sys.platform == "win32", "Stalled SOCKS teardown uses the production Linux event loop")
    async def test_stalled_socks_handshake_is_bounded_not_sixty_seconds(self):
        clients = []
        server = await asyncio.start_server(lambda reader, writer: clients.append(writer), "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        session = FailoverSession([f"socks5://127.0.0.1:{port}"], api=self.session.api)
        bot = Bot(token="123456:TEST_TOKEN", session=session)
        try:
            self.assertTrue((await asyncio.wait_for(bot.get_me(), timeout=8)).is_bot)
            self.assertEqual(session._active, 1)
        finally:
            await session.close()
            server.close()
            await server.wait_closed()
            for writer in clients:
                writer.transport.abort()


if __name__ == "__main__":
    unittest.main()
