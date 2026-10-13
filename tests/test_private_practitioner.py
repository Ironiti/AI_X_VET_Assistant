"""Exercise CPV handlers and SQLite migrations without network or production data."""
import ast
from contextlib import closing
from datetime import datetime
from pathlib import Path
import re
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import aiosqlite
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOTS = ([PROJECT_ROOT] if (PROJECT_ROOT / 'bot').is_dir() else
         [Path('E:/AI_VET_Assistant-2'), Path('E:/AI_VET_Assistant_VK'), Path('E:/AI_X_VET_Assistant')])


def load_functions(path, names, namespace):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            node.decorator_list = []
            selected.append(node)
    assert {node.name for node in selected} == set(names), path
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


class State:
    def __init__(self, vk=False):
        self.vk = vk
        self.data = {}
        self.current = None

    async def update_data(self, **data):
        self.data.update(data)

    async def get_data(self):
        return self.data.copy()

    async def set_state(self, current):
        self.current = current

    set = set_state

    async def clear(self):
        self.current = None
        self.data.clear()

    delete = clear


def registration_namespace(root):
    vk = root.name.endswith('_VK')
    states = SimpleNamespace()
    for suffix in ('user_type', 'specialization', 'custom_specialization', 'practitioner_name', 'practitioner_region', 'country', 'guest_code', 'client_code'):
        name = 'WAITING_FOR_' + suffix.upper() if vk else 'waiting_for_' + suffix
        setattr(states, name, suffix)
    db = SimpleNamespace(add_private_practitioner=AsyncMock(return_value=True), add_client=AsyncMock(return_value=True))
    ns = dict(Message=object, FSMContext=object, StateManager=object, RegistrationStates=states,
              db=db, ReplyKeyboardRemove=lambda: 'remove-keyboard', _reg_sessions={},
              get_specialization_kb=lambda: 'specialties', get_main_menu_kb=lambda: 'main-menu',
              get_country_kb=lambda: 'countries', get_user_type_kb=lambda: 'roles',
              _process_test_request=AsyncMock(), finish_registration=AsyncMock())
    names = ['valid_practitioner_name', 'process_user_type', 'process_specialization',
             'process_custom_specialization', 'process_practitioner_name', 'process_practitioner_region']
    if vk:
        names += ['_ask_practitioner_name', '_complete_client_registration']
    else:
        names += ['ask_practitioner_name']
    return load_functions(root / 'bot/handlers/registration.py', names, ns)


def message(text):
    return SimpleNamespace(text=text, from_user=SimpleNamespace(id=123), from_id=123, answer=AsyncMock())


class RegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_flow_all_bots(self):
        for root in ROOTS:
            for specialty in ('Хирургия', 'Своя специальность'):
                with self.subTest(project=root.name, specialty=specialty):
                    ns = registration_namespace(root)
                    state = State()
                    await ns['process_user_type'](message('Частнопрактикующий врач'), state)
                    self.assertEqual(state.current, 'specialization')
                    data = ns['_reg_sessions'][123] if root.name.endswith('_VK') else state.data
                    self.assertEqual(data['user_type'], 'private_practitioner')
                    if specialty == 'Хирургия':
                        await ns['process_specialization'](message(specialty), state)
                    else:
                        await ns['process_specialization'](message('✏️ Ввести свою специализацию'), state)
                        self.assertEqual(state.current, 'custom_specialization')
                        await ns['process_custom_specialization'](message(specialty), state)
                    self.assertEqual(state.current, 'practitioner_name')
                    for invalid in (None, '', 'Иван', 'Иванов 123', '--- ---'):
                        await ns['process_practitioner_name'](message(invalid), state)
                        self.assertEqual(state.current, 'practitioner_name')
                    await ns['process_practitioner_name'](message('  Иванов   Иван  '), state)
                    self.assertEqual(state.current, 'practitioner_region')
                    for invalid in (None, ' ', 'Я', 'x' * 101):
                        await ns['process_practitioner_region'](message(invalid), state)
                        ns['db'].add_private_practitioner.assert_not_awaited()
                    last = message(' Московская область ')
                    await ns['process_practitioner_region'](last, state)
                    ns['db'].add_private_practitioner.assert_awaited_once_with(
                        telegram_id=123, name='Иванов Иван', specialization=specialty, region='Московская область')
                    ns['db'].add_client.assert_not_awaited()
                    kwargs = last.answer.call_args.kwargs
                    self.assertEqual(kwargs.get('keyboard', kwargs.get('reply_markup')), 'main-menu')
                    self.assertIn('Частнопрактикующий врач', last.answer.call_args.args[0])

    async def test_invalid_specialty_and_failed_save(self):
        for root in ROOTS:
            with self.subTest(project=root.name):
                ns = registration_namespace(root)
                state = State()
                await ns['process_user_type'](message('Частнопрактикующий врач'), state)
                await ns['process_specialization'](message('Несуществующая кнопка'), state)
                self.assertEqual(state.current, 'specialization')
                await ns['process_specialization'](message('✏️ Ввести свою специализацию'), state)
                for text in (None, ' ', 'x', 'x' * 101):
                    await ns['process_custom_specialization'](message(text), state)
                    self.assertEqual(state.current, 'custom_specialization')
                await ns['process_custom_specialization'](message('Терапия'), state)
                await ns['process_practitioner_name'](message('Петрова Анна'), state)
                ns['db'].add_private_practitioner.return_value = False
                last = message('Минск')
                await ns['process_practitioner_region'](last, state)
                self.assertEqual(state.current, 'practitioner_region')
                self.assertNotIn('main-menu', last.answer.call_args.kwargs.values())

    async def test_existing_client_flow(self):
        for root in ROOTS:
            with self.subTest(project=root.name):
                ns = registration_namespace(root)
                state = State()
                first = message('👨‍⚕️ Ветеринарный врач клиники-партнера')
                await ns['process_user_type'](first, state)
                if root.name == 'AI_X_VET_Assistant':
                    self.assertEqual(state.current, 'client_code')
                    self.assertIn('код клиники', first.answer.call_args.args[0])
                else:
                    self.assertEqual(state.current, 'country')
                data = dict(user_type='client', name='Иван', client_code='В+ТЕСТ', country='RU')
                if root.name.endswith('_VK'):
                    ns['_reg_sessions'][123] = data
                else:
                    state.data = data
                await ns['process_specialization'](message('Хирургия'), state)
                ns['db'].add_client.assert_awaited_once()
                ns['db'].add_private_practitioner.assert_not_awaited()

    async def test_pending_test_preserved(self):
        for root in ROOTS:
            with self.subTest(project=root.name):
                ns = registration_namespace(root)
                state = State()
                await ns['process_user_type'](message('Частнопрактикующий врач'), state)
                await ns['process_specialization'](message('Терапия'), state)
                await ns['process_practitioner_name'](message('Петров Иван'), state)
                if root.name.endswith('_VK'):
                    ns['_reg_sessions'][123]['pending_test_code'] = 'AN116'
                else:
                    state.data['pending_test_code'] = 'AN116'
                    load_functions(root / 'bot/handlers/registration.py', ['finish_registration'], ns)
                    ns['process_test_request'] = AsyncMock()
                await ns['process_practitioner_region'](message('Москва'), state)
                target = ns['_process_test_request'] if root.name.endswith('_VK') else ns['process_test_request']
                self.assertEqual(target.await_args.args[2], 'AN116')


    async def test_cpv_button_alias_and_message_style(self):
        for root in ROOTS:
            for button in ('👨‍⚕️ Частнопрактикующий врач', 'Частнопрактикующий врач'):
                with self.subTest(project=root.name, button=button):
                    ns = registration_namespace(root)
                    state = State()
                    first = message(button)
                    await ns['process_user_type'](first, state)
                    self.assertEqual(state.current, 'specialization')
                    self.assertEqual(first.answer.call_args.args[0], 'Выберите вашу специализацию:')
                    self.assertEqual(first.answer.call_args.kwargs.get(
                        'keyboard', first.answer.call_args.kwargs.get('reply_markup')), 'specialties')
                    name_prompt = message('Хирургия')
                    await ns['process_specialization'](name_prompt, state)
                    self.assertEqual(name_prompt.answer.call_args.args[0],
                                     '📋 Специализация: Хирургия\n\nВведите ваши фамилию и имя:')
                    region_prompt = message('Иванов Иван')
                    await ns['process_practitioner_name'](region_prompt, state)
                    self.assertEqual(region_prompt.answer.call_args.args[0],
                                     '👤 Фамилия и имя: Иванов Иван\n\nВведите ваш регион:')
                    if not root.name.endswith('_VK'):
                        for prompt in (name_prompt, region_prompt):
                            self.assertEqual(prompt.answer.call_args.kwargs['reply_markup'], 'remove-keyboard')
                            self.assertIsNone(prompt.answer.call_args.kwargs['parse_mode'])
                    last = message('Минск')
                    await ns['process_practitioner_region'](last, state)
                    self.assertEqual(last.answer.call_args.args[0],
                                     '✅ Регистрация завершена успешно!\n\n'
                                     '👨‍⚕️ Частнопрактикующий врач\n'
                                     '👤 Фамилия и имя: Иванов Иван\n'
                                     '📋 Специализация: Хирургия\n'
                                     '📍 Регион: Минск\n\n'
                                     'Теперь вы можете пользоваться всеми функциями бота!')

    async def test_role_keyboard_and_prompts_follow_existing_style(self):
        for root in ROOTS:
            source = (root / 'bot/keyboards.py').read_text(encoding='utf-8-sig')
            tree = ast.parse(source)
            for function in ('get_user_type_kb', 'get_registration_type_kb'):
                node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
                labels = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant)
                          and isinstance(n.value, str) and ('врач' in n.value or 'Сотрудник' in n.value)]
                self.assertEqual(labels[1], '👨‍⚕️ Частнопрактикующий врач')
                calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
                if root.name.endswith('_VK'):
                    keyboard = next(n for n in calls if isinstance(n.func, ast.Name) and n.func.id == 'Keyboard')
                    kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in keyboard.keywords}
                    self.assertFalse(kwargs['inline'])
                    self.assertTrue(kwargs['one_time'])
                else:
                    keyboard = next(n for n in calls if isinstance(n.func, ast.Name) and n.func.id == 'ReplyKeyboardMarkup')
                    self.assertTrue(next(ast.literal_eval(kw.value) for kw in keyboard.keywords if kw.arg == 'resize_keyboard'))
            source = (root / 'bot/handlers/registration.py').read_text(encoding='utf-8-sig')
            self.assertIn('👤 Выберите удобный вариант:', source)
            self.assertIn('👤 Отлично. Выберите, кто вы:', source)
            self.assertIn('👤 Выберите, кто вы:', source)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def load_database(root, path):
        tree = ast.parse((root / 'src/database/models.py').read_text(encoding='utf-8-sig'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Database')
        methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in {'ensure_private_practitioner_type', 'add_private_practitioner'}]
        cls.body = methods
        ns = dict(aiosqlite=aiosqlite, datetime=datetime, re=re)
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(root), 'exec'), ns)
        database = ns['Database']()
        database.db_path = str(path)
        database.clear_user_cache = lambda user_id: None
        return database

    async def test_migration_and_registration(self):
        for root in ROOTS:
            with self.subTest(project=root.name), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'test.db'
                database = self.load_database(root, path)
                with sqlite3.connect(path) as conn:
                    conn.executescript('''
                        PRAGMA foreign_keys=ON;
                        CREATE TABLE users (
                          telegram_id INTEGER PRIMARY KEY,
                          user_type TEXT CHECK(user_type IN ('client', 'employee')),
                          name TEXT, specialization TEXT, region TEXT, country TEXT,
                          registration_date TEXT, role TEXT, client_code TEXT,
                          custom_column TEXT DEFAULT 'keep');
                        INSERT INTO users VALUES (1, 'client', 'Старый пользователь', 'Терапия', NULL,
                          'RU', '2026-01-01', 'admin', 'В+КЛИНИКА', 'keep-original');
                        CREATE TABLE history (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(telegram_id) ON DELETE CASCADE);
                        INSERT INTO history VALUES (1, 1);
                        CREATE INDEX users_name_idx ON users(name);
                        CREATE TABLE audit (user_id INTEGER);
                        CREATE TRIGGER users_audit AFTER INSERT ON users BEGIN INSERT INTO audit VALUES (NEW.telegram_id); END;
                        CREATE VIEW users_view AS SELECT name FROM users;
                    ''')
                    original = conn.execute('SELECT * FROM users').fetchall()
                conn.close()
                await database.ensure_private_practitioner_type()
                with closing(sqlite3.connect(path)) as conn:
                    self.assertEqual(conn.execute('SELECT * FROM users').fetchall(), original)
                    self.assertEqual(conn.execute('SELECT * FROM history').fetchall(), [(1, 1)])
                    self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
                    self.assertEqual(conn.execute('SELECT * FROM users_view').fetchall(), [('Старый пользователь',)])
                    self.assertIn('users_name_idx', [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")])
                self.assertTrue(await database.add_private_practitioner(2, 'Иванов Иван', 'Хирургия', 'Москва'))
                self.assertFalse(await database.add_private_practitioner(2, 'Иванов Иван', 'Хирургия', 'Москва'))
                with closing(sqlite3.connect(path)) as conn:
                    self.assertEqual(conn.execute('SELECT user_type, name, specialization, region, client_code FROM users WHERE telegram_id=2').fetchone(), ('private_practitioner', 'Иванов Иван', 'Хирургия', 'Москва', None))
                    self.assertEqual(conn.execute('SELECT * FROM audit').fetchall(), [(2,)])
                await database.ensure_private_practitioner_type()
                backups = list((Path(tmp) / 'backups').glob('*.db'))
                self.assertEqual(len(backups), 1)
                with closing(sqlite3.connect(backups[0])) as conn:
                    self.assertEqual(conn.execute('SELECT * FROM users').fetchall(), original)

    async def test_new_database_schema(self):
        for root in ROOTS:
            with self.subTest(project=root.name), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'new.db'
                database = self.load_database(root, path)
                await database.ensure_private_practitioner_type()
                tree = ast.parse((root / 'src/database/models.py').read_text(encoding='utf-8-sig'))
                sql = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and 'CREATE TABLE IF NOT EXISTS users (' in n.value)
                with closing(sqlite3.connect(path)) as conn:
                    conn.execute(sql)
                    conn.commit()
                await database.ensure_private_practitioner_type()
                self.assertTrue(await database.add_private_practitioner(123, 'Иванов Иван', 'Терапия', 'Минск'))
                self.assertFalse((Path(tmp) / 'backups').exists())

    async def test_failed_migration_rolls_back(self):
        for root in ROOTS:
            with self.subTest(project=root.name), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'failed.db'
                database = self.load_database(root, path)
                with closing(sqlite3.connect(path)) as conn:
                    conn.executescript("CREATE TABLE users (telegram_id INTEGER PRIMARY KEY, user_type TEXT CHECK(user_type IN ('client', 'employee'))); INSERT INTO users VALUES (1, 'client'); CREATE TABLE users_cpv_migration (x);")
                with self.assertRaises(sqlite3.OperationalError):
                    await database.ensure_private_practitioner_type()
                with closing(sqlite3.connect(path)) as conn:
                    self.assertEqual(conn.execute('SELECT * FROM users').fetchall(), [(1, 'client')])


class SourceTests(unittest.TestCase):
    def test_second_button_and_syntax(self):
        for root in ROOTS:
            with self.subTest(project=root.name):
                tree = ast.parse((root / 'bot/keyboards.py').read_text(encoding='utf-8-sig'))
                for function in ('get_user_type_kb', 'get_registration_type_kb'):
                    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
                    labels = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str) and ('клиники-партнера' in n.value or 'Частнопрактикующий' in n.value or 'Сотрудник' in n.value or 'гость' in n.value)]
                    self.assertEqual(labels[1], '👨‍⚕️ Частнопрактикующий врач')
                for file in ('bot/keyboards.py', 'bot/handlers/registration.py', 'src/database/models.py', 'utils/excel_exporter.py', 'utils/poll_exporter.py', 'utils/email_sender.py', 'bot/handlers/admin.py'):
                    ast.parse((root / file).read_text(encoding='utf-8-sig'), filename=str(root / file))


if __name__ == '__main__':
    unittest.main(verbosity=2)
