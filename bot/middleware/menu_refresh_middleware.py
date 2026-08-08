"""Refresh an outdated Telegram reply keyboard without interrupting a flow."""

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import get_menu_by_role
from config import MENU_VERSION
from src.database.db_init import db

logger = logging.getLogger(__name__)

MAIN_MENU_RETURN_TEXTS = {
    "🔙 Вернуться в главное меню",
    "🏠 В главное меню",
    "🏠 Главное меню",
    "❌ Завершить диалог",
}

_UNKNOWN_USER = object()


def _is_plain_start(text: str | None) -> bool:
    """Match /start without a deep-link argument, including /start@bot_name."""
    if not text:
        return False

    parts = text.strip().split(maxsplit=1)
    command = parts[0].split("@", maxsplit=1)[0].lower()
    return command == "/start" and len(parts) == 1


class MenuRefreshMiddleware(BaseMiddleware):
    """Show the current reply menu once without interrupting an active flow."""

    def __init__(self, database=None, menu_version: str = MENU_VERSION):
        super().__init__()
        self.database = database or db
        self.menu_version = menu_version

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        user_before = _UNKNOWN_USER
        delivered_before = None
        if event.from_user is not None:
            try:
                user_before = await self.database.get_user(event.from_user.id)
                state: FSMContext | None = data.get("state")
                state_before = await state.get_state() if state else None

                if user_before and state_before is None:
                    delivered_before = await self.database.get_user_menu_version(
                        event.from_user.id
                    )
                    handler_will_show_menu = (
                        _is_plain_start(event.text)
                        or event.text in MAIN_MENU_RETURN_TEXTS
                    )
                    if (
                        delivered_before != self.menu_version
                        and not handler_will_show_menu
                    ):
                        await event.answer(
                            "Меню обновлено.",
                            reply_markup=get_menu_by_role(
                                user_before.get("role", "user")
                            ),
                        )
                        await self.database.set_user_menu_version(
                            event.from_user.id,
                            self.menu_version,
                        )
            except Exception:
                # The user's action must run even if the refresh is unavailable.
                logger.exception(
                    "[MENU_REFRESH] Failed before handler for user %s",
                    event.from_user.id,
                )

        result = await handler(event, data)

        try:
            if event.from_user is None:
                return result

            user_id = event.from_user.id
            state: FSMContext | None = data.get("state")
            user = await self.database.get_user(user_id)
            if not user:
                return result

            # A dialogue, registration, form, or upload still owns the keyboard.
            current_state = await state.get_state() if state else None
            if current_state is not None:
                return result

            # The registration handler has just created the user and already
            # displayed the current main menu. Do not add a second message.
            if user_before is None:
                await self.database.set_user_menu_version(user_id, self.menu_version)
                return result

            delivered_version = await self.database.get_user_menu_version(user_id)
            if delivered_version == self.menu_version:
                return result

            # These handlers already returned the user to the current main menu.
            # A /start deep link is intentionally excluded: it may only send a
            # document or test card and leave the old keyboard untouched.
            if _is_plain_start(event.text) or event.text in MAIN_MENU_RETURN_TEXTS:
                await self.database.set_user_menu_version(user_id, self.menu_version)
                return result

            # Any other stale menu is refreshed on the next idle interaction,
            # before that interaction starts. Do not place a menu below content.
        except Exception:
            # A menu refresh must never break the user's original action.
            logger.exception("[MENU_REFRESH] Failed for user %s", getattr(event.from_user, "id", None))

        return result
