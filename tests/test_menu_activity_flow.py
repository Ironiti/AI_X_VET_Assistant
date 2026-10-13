"""Load the actual candidate middleware without importing running bots."""
import argparse
import ast
import logging
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict
import unittest

ROOT = Path(__file__).resolve().parents[1] if '__file__' in globals() else Path.cwd()
CANDIDATE = None
PLATFORM = 'telegram'


class Message:
    def __init__(self):
        self.from_user = SimpleNamespace(id=101, is_bot=False)
        self.from_id = 101
        self.text = 'Статистика'
        self.payload = None
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class Base:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, event=None, view=None):
        self.event = event


class Store:
    def __init__(self, inactive=False, version='current', role='admin'):
        self.inactive = inactive
        self.version = version
        self.role = role
        self.calls = []
        self.fail = False
        self.state = None

    async def register_user_menu_activity(self, user, days):
        self.calls.append(('activity', user))
        if self.fail:
            raise RuntimeError('simulated recording failure')
        previous, self.inactive = self.inactive, False
        return previous

    async def touch_user_menu_activity(self, user):
        self.calls.append(('callback', user))

    async def get_user(self, user):
        return {'role': self.role}

    async def get_user_menu_version(self, user):
        return self.version

    async def set_user_menu_version(self, user, version):
        self.version = version

    async def get(self, user):
        return self.state


class State:
    def __init__(self, value=None):
        self.value = value

    async def get_state(self):
        return self.value


def read_source(path):
    if CANDIDATE:
        return subprocess.check_output(['git', '-C', str(ROOT), 'show', CANDIDATE + ':' + path], text=True)
    return (ROOT / path).read_text()


if 'RawMenuActivityMiddleware' in read_source('bot/middleware/menu_refresh_middleware.py'):
    PLATFORM = 'vk'


def middleware_classes():
    source = read_source('bot/middleware/menu_refresh_middleware.py')
    tree = ast.parse(source)
    body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    namespace = dict(BaseMiddleware=Base, Message=Message, FSMContext=State,
                     Any=Any, Awaitable=Awaitable, Callable=Callable, Dict=Dict,
                     logging=logging, json=__import__('json'), db=None,
                     get_menu_by_role=lambda role: 'keyboard-' + role,
                     MENU_VERSION='current', MENU_REFRESH_INACTIVITY_DAYS=30)
    exec(compile(ast.Module(body=body, type_ignores=[]), 'candidate-menu-middleware', 'exec'), namespace)
    return namespace


class ActivityFlowTests(unittest.IsolatedAsyncioTestCase):
    async def event(self, store, state=None, fail_handler=False):
        module = middleware_classes()
        event = Message()
        calls = []

        async def handler(e, data):
            self.assertTrue(store.calls, 'Activity must already be saved before the handler')
            calls.append('handler')
            if fail_handler:
                raise ValueError('downstream handler failed')
            return 'handled'

        if PLATFORM == 'vk':
            store.state = state
            middleware = module['MenuRefreshMiddleware'](event, database=store, state_dispenser=store)
            await middleware.pre()
            await handler(event, {})
            await middleware.post()
        else:
            refresh = module['MenuRefreshMiddleware'](database=store)
            collector = module['MenuActivityMiddleware'](database=store)

            async def inner(e, data):
                return await refresh(handler, e, data)

            await collector(inner, event, {'state': State(state)})
        return event, calls

    async def test_active_admin_receives_no_absence_message(self):
        store = Store(inactive=False, role='admin')
        event, calls = await self.event(store)
        self.assertEqual(event.answers, [])
        self.assertEqual(calls, ['handler'])
        self.assertEqual(store.calls, [('activity', 101)])

    async def test_known_long_absence_only_once(self):
        store = Store(inactive=True)
        event, _ = await self.event(store)
        self.assertEqual(len(event.answers), 1)
        self.assertIn('Вы давно', event.answers[0][0])
        second, _ = await self.event(store)
        self.assertEqual(second.answers, [])

    async def test_unknown_activity_stale_version_gets_only_generic_refresh(self):
        event, _ = await self.event(Store(inactive=False, version='old'))
        self.assertEqual(len(event.answers), 1)
        self.assertEqual(event.answers[0][0], 'Меню обновлено.')

    async def test_dialogue_records_activity_without_interrupting_keyboard(self):
        store = Store(inactive=True)
        event, _ = await self.event(store, state='registration')
        self.assertEqual(event.answers, [])
        self.assertFalse(store.inactive)

    async def test_failure_of_original_handler_keeps_recorded_activity(self):
        store = Store(inactive=False)
        with self.assertRaises(ValueError):
            await self.event(store, fail_handler=True)
        self.assertEqual(store.calls, [('activity', 101)])

    async def test_recording_failure_never_blocks_handler_or_claims_absence(self):
        store = Store(inactive=True)
        store.fail = True
        event, calls = await self.event(store)
        self.assertEqual(calls, ['handler'])
        self.assertEqual(event.answers, [])

    async def test_callback_records_actor_without_sending_menu(self):
        module = middleware_classes()
        store = Store(inactive=True)
        if PLATFORM == 'vk':
            raw = {'type': 'message_event', 'object': {'user_id': 101, 'peer_id': 555, 'payload': {}}}
            await module['RawMenuActivityMiddleware'](raw, database=store).pre()
            self.assertEqual(store.calls, [('callback', 101)])
            raw['type'] = 'group_join'
            await module['RawMenuActivityMiddleware'](raw, database=store).pre()
            self.assertEqual(len(store.calls), 1)
        else:
            callback = SimpleNamespace(from_user=SimpleNamespace(id=101, is_bot=False))
            called = []

            async def handler(e, data):
                called.append('callback')
                self.assertEqual(store.calls, [('activity', 101)])

            data = {}
            await module['MenuActivityMiddleware'](database=store)(handler, callback, data)
            self.assertEqual(called, ['callback'])
            self.assertNotIn('_menu_activity_was_inactive', data)

    async def test_callback_recording_failure_is_not_propagated(self):
        module = middleware_classes()
        store = Store()
        if PLATFORM == 'vk':
            async def failing_touch(user):
                raise RuntimeError('recording failed')
            store.touch_user_menu_activity = failing_touch
            raw = {'type': 'message_event', 'object': {'user_id': 101}}
            await module['RawMenuActivityMiddleware'](raw, database=store).pre()
        else:
            store.fail = True
            callback = SimpleNamespace(from_user=SimpleNamespace(id=101, is_bot=False))
            called = []

            async def handler(e, data):
                called.append(True)

            await module['MenuActivityMiddleware'](database=store)(handler, callback, {})
            self.assertEqual(called, [True])

    async def test_real_framework_wiring_covers_callbacks(self):
        path = 'bot/__init__.py' if PLATFORM == 'vk' else 'bot/handlers/__init__.py'
        source = read_source(path)
        if PLATFORM == 'vk':
            self.assertIn('bot.labeler.raw_event_view.register_middleware(RawMenuActivityMiddleware)', source)
        else:
            self.assertIn('dp.message.outer_middleware(MenuActivityMiddleware())', source)
            self.assertIn('dp.callback_query.outer_middleware(MenuActivityMiddleware())', source)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--candidate')
    parser.add_argument('--platform', choices=['telegram', 'vk', 'xlab'], required=True)
    args = parser.parse_args()
    ROOT, CANDIDATE, PLATFORM = args.root, args.candidate, args.platform
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ActivityFlowTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
