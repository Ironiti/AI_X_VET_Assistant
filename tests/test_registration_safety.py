"""Regression checks for late specialty replies and busy registration saves."""
import asyncio
import gc
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import AsyncMock

from test_private_practitioner import State, message, registration_namespace


ROOT = Path(__file__).resolve().parents[1]


class SpecialtySafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = registration_namespace(ROOT)
        states = self.ns['RegistrationStates']
        states.waiting_for_client_name = 'client_name'
        self.ns['get_registration_type_kb'] = lambda: 'registration-roles'
        self.ns['get_admin_menu_kb'] = lambda: 'admin-menu'
        self.state = State()
        self.state.current = 'specialization'
        self.data = dict(user_type='client', name='Иван', client_code='В+ТЕСТ',
                         country='RU', pending_test_code='AN116')
        self.state.data = self.data.copy()

    async def call_choice(self, custom=False, text=None):
        text = text or ('Кардиология' if custom else 'Хирургия')
        msg = message(text)
        function = 'process_custom_specialization' if custom else 'process_specialization'
        await self.ns[function](msg, self.state)
        return msg

    async def test_late_reply_returns_existing_menu_without_saving(self):
        for custom in (False, True):
            for role in ('user', 'admin'):
                self.ns['db'].get_user.return_value = {'name': 'Иван', 'role': role}
                self.state.data = {}
                msg = await self.call_choice(custom)
                self.ns['db'].add_client.assert_not_awaited()
                self.assertEqual(msg.answer.call_args.kwargs['reply_markup'],
                                 'admin-menu' if role == 'admin' else 'main-menu')
                self.assertIsNone(self.state.current)

    async def test_late_custom_button_does_not_start_registration(self):
        self.ns['db'].get_user.return_value = {'name': 'Иван', 'role': 'user'}
        await self.call_choice(text='✏️ Ввести свою специализацию')
        self.assertIsNone(self.state.current)
        self.ns['db'].add_client.assert_not_awaited()

    async def test_missing_data_recovers_step_and_preserves_other_fields(self):
        for missing, expected in (('name', 'client_name'), ('client_code', 'client_code'),
                                  ('user_type', 'user_type')):
            for custom in (False, True):
                self.state.data = self.data.copy()
                del self.state.data[missing]
                remaining = self.state.data.copy()
                await self.call_choice(custom)
                self.assertEqual(self.state.current, expected)
                self.assertEqual(self.state.data, remaining)
                self.ns['db'].add_client.assert_not_awaited()

    async def test_busy_save_preserves_form_and_can_retry(self):
        for custom in (False, True):
            for failure in ('database is locked', 'database table is locked', 'database is busy'):
                self.state.current = 'custom_specialization' if custom else 'specialization'
                self.state.data = self.data.copy()
                self.ns['db'].add_client.reset_mock()
                self.ns['db'].add_client.side_effect = [sqlite3.OperationalError(failure), True]
                msg = await self.call_choice(custom)
                self.assertEqual(self.state.data, self.data)
                self.assertEqual(self.state.current,
                                 'custom_specialization' if custom else 'specialization')
                self.assertIn('Не удалось сохранить', msg.answer.call_args.args[0])
                self.assertNotIn('успешно', msg.answer.call_args.args[0])
                self.assertEqual(msg.answer.call_args.kwargs['reply_markup'],
                                 'remove-keyboard' if custom else 'specialties')
                await self.call_choice(custom)
                self.assertIsNone(self.state.current)
                self.assertEqual(self.ns['db'].add_client.await_count, 2)

    async def test_failed_insert_preserves_form(self):
        self.ns['db'].add_client.return_value = False
        for custom in (False, True):
            await self.call_choice(custom)
            self.assertEqual(self.state.data, self.data)
            self.assertEqual(self.state.current, 'specialization')

    async def test_locked_profile_lookup_preserves_form(self):
        self.ns['db'].get_user.side_effect = sqlite3.OperationalError('database is locked')
        await self.call_choice()
        self.assertEqual(self.state.data, self.data)
        self.ns['db'].add_client.assert_not_awaited()

    async def test_existing_country_default_is_preserved(self):
        del self.state.data['country']
        await self.call_choice()
        self.assertEqual(self.ns['db'].add_client.await_args.kwargs['country'], 'RU')

    async def test_unrelated_db_errors_and_cancellation_propagate(self):
        for error in (sqlite3.OperationalError('no such table: users'), asyncio.CancelledError()):
            self.ns['db'].add_client.side_effect = error
            with self.assertRaises(type(error)):
                await self.call_choice()
            self.assertEqual(self.state.data, self.data)

    async def test_concurrent_choices_create_only_one_profile(self):
        saved = None

        async def read_user(_):
            return saved

        async def insert(**values):
            nonlocal saved
            await asyncio.sleep(0)
            saved = dict(values, role='user')
            return True

        self.ns['db'].get_user.side_effect = read_user
        self.ns['db'].add_client.side_effect = insert
        await asyncio.gather(self.call_choice(text='Хирургия'), self.call_choice(text='Офтальмология'))
        self.ns['db'].add_client.assert_awaited_once()
        self.assertEqual(saved['specialization'], 'Хирургия')
        self.assertIsNone(self.state.current)
        gc.collect()
        self.assertEqual(len(self.ns['_specialization_locks']), 0)

    async def test_different_users_are_not_serialized(self):
        first_started = asyncio.Event()
        second_started = asyncio.Event()

        async def insert(**values):
            if values['telegram_id'] == 123:
                first_started.set()
                await asyncio.wait_for(second_started.wait(), 1)
            else:
                second_started.set()
            return True

        self.ns['db'].add_client.side_effect = insert
        other_state = State()
        other_state.data = self.data.copy()
        other = message('Терапия')
        other.from_user.id = 456
        first = asyncio.create_task(self.call_choice())
        await first_started.wait()
        await self.ns['process_specialization'](other, other_state)
        await first
        self.assertEqual(self.ns['db'].add_client.await_count, 2)


if __name__ == '__main__':
    unittest.main()
