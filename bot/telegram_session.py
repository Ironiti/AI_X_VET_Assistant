"""Bounded runtime failover for Telegram, without replaying uncertain sends."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass

from aiohttp import ClientConnectionError, ClientError, ClientResponseError, ClientSession, ClientTimeout, TraceConfig
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramNetworkError

logger = logging.getLogger(__name__)
NETWORK_ERRORS = (ClientConnectionError, ProxyConnectionError, ProxyError, ProxyTimeoutError, asyncio.TimeoutError)
# Read-only calls can be repeated even if their response was lost. Sends cannot.
READ_METHODS = {"getMe", "getUpdates", "getFile", "getChat", "getChatMember", "getWebhookInfo"}


class TransportFailure(TelegramNetworkError):
    def __init__(self, method, error, *, request_started=False):
        super().__init__(method=method, message=f"Connection failed ({type(error).__name__})")
        self.request_started = request_started


class ConnectionSession(AiohttpSession):
    """Keep normal upload/long-poll timeouts, but bound connection establishment."""

    async def create_session(self):
        if self._should_reset_connector:
            await self.close()
        if self._session is None or self._session.closed:
            trace = TraceConfig()

            async def headers_sent(session, context, params):
                context.trace_request_ctx["started"] = True

            trace.on_request_headers_sent.append(headers_sent)
            self._session = ClientSession(
                connector=self._connector_type(**self._connector_init),
                trace_configs=[trace],
            )
            self._should_reset_connector = False
        return self._session

    @staticmethod
    def connection_timeout(total):
        return ClientTimeout(total=total, connect=5, sock_connect=5)

    async def make_request(self, bot, method, timeout=None):
        session = await self.create_session()
        url = self.api.api_url(token=bot.token, method=method.__api_method__)
        # Rebuild multipart data on each attempt, including fresh InputFile readers.
        form = self.build_form_data(bot=bot, method=method)
        trace = {"started": False}
        try:
            async with session.post(
                url,
                data=form,
                timeout=self.connection_timeout(self.timeout if timeout is None else timeout),
                trace_request_ctx=trace,
            ) as response:
                content = await response.text()
        except (ClientError, ProxyConnectionError, ProxyError, ProxyTimeoutError, asyncio.TimeoutError) as error:
            raise TransportFailure(method, error, request_started=trace["started"]) from None
        result = self.check_response(
            bot=bot, method=method, status_code=response.status, content=content,
        )
        return result.result

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        session = await self.create_session()
        async with session.get(
            url, headers=headers or {}, timeout=self.connection_timeout(timeout),
            raise_for_status=raise_for_status, trace_request_ctx={"started": False},
        ) as response:
            async for chunk in response.content.iter_chunked(chunk_size):
                yield chunk


@dataclass
class Route:
    name: str
    session: ConnectionSession
    retry_at: float = 0


class FailoverSession(BaseSession):
    def __init__(self, proxy_urls, *, session_factory=ConnectionSession, clock=time.monotonic, **kwargs):
        super().__init__(**kwargs)
        self._clock = clock
        self._active = 0
        self._generation = 0
        unique = list(dict.fromkeys(url.strip() for url in proxy_urls if url and url.strip()))
        self.routes = [
            Route(f"proxy-{index + 1}", session_factory(proxy=url, api=self.api, timeout=self.timeout))
            for index, url in enumerate(unique)
        ]
        self.routes.append(Route("direct", session_factory(api=self.api, timeout=self.timeout)))

    def _order(self):
        now = self._clock()
        order = [self._active] + [i for i in range(len(self.routes)) if i != self._active]
        ready = [i for i in order if self.routes[i].retry_at <= now]
        # If every path is cooling down, probe only the earliest one, not all again.
        return ready or [min(order, key=lambda i: self.routes[i].retry_at)]

    def _failed(self, index):
        self.routes[index].retry_at = self._clock() + 60
        self._generation += 1
        if self._active == index:
            alternatives = [i for i in self._order() if i != index]
            if alternatives:
                self._active = alternatives[0]
        logger.warning("[TG FAILOVER] %s unavailable; selecting another connection", self.routes[index].name)

    def _succeeded(self, index, generation):
        # Do not overwrite a newer failure reported by another concurrent request.
        if generation == self._generation:
            self.routes[index].retry_at = 0
            if self._active != index:
                logger.info("[TG FAILOVER] Active connection: %s", self.routes[index].name)
            self._active = index

    async def make_request(self, bot, method, timeout=None):
        last_error = None
        for index in self._order():
            if self.routes[index].retry_at > self._clock() and last_error is not None:
                continue
            generation = self._generation
            try:
                result = await self.routes[index].session.make_request(bot, method, timeout=timeout)
            except TransportFailure as error:
                self._failed(index)
                if error.request_started and method.__api_method__ not in READ_METHODS:
                    # Telegram may have accepted this send. Do not duplicate it.
                    raise
                last_error = error
                continue
            self._succeeded(index, generation)
            return result
        raise last_error

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        last_error = None
        for index in self._order():
            if self.routes[index].retry_at > self._clock() and last_error is not None:
                continue
            generation = self._generation
            emitted = False
            try:
                async for chunk in self.routes[index].session.stream_content(
                    url, headers=headers, timeout=timeout, chunk_size=chunk_size,
                    raise_for_status=raise_for_status,
                ):
                    emitted = True
                    yield chunk
            except ClientResponseError as error:
                # The original error includes the download URL and its bot token.
                raise ConnectionError(f"Telegram download HTTP error ({error.status})") from None
            except NETWORK_ERRORS as error:
                self._failed(index)
                if emitted:
                    # Restarting from byte zero here would corrupt the caller's file.
                    raise ConnectionError("Telegram download interrupted after partial data") from None
                last_error = error
                continue
            self._succeeded(index, generation)
            return
        # Avoid exposing URLs containing a bot token in download errors.
        raise ConnectionError("Telegram download failed on all available connections") from None

    async def close(self):
        await asyncio.gather(*(route.session.close() for route in self.routes))


def create_telegram_session(primary_proxy_url):
    """Use existing proxies, additional ENV-only proxies, then a direct connection."""
    return FailoverSession([
        primary_proxy_url,
        os.getenv("TELEGRAM_RESERVE_PROXY_URL") or os.getenv("RESERVE_PROXY_URL"),
        *os.getenv("TELEGRAM_EXTRA_PROXY_URLS", "").replace("\n", ",").split(","),
    ])
