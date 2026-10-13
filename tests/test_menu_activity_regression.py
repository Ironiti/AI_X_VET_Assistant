"""DB-only menu inactivity regression tests; loads methods without bot imports."""
import argparse
import ast
import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
import io
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import aiosqlite

PROJECT_ROOT = Path(__file__).resolve().parents[1] if '__file__' in globals() else Path.cwd()
SOURCE = PROJECT_ROOT / 'src/database/models.py'
METHOD_NAMES = {'is_user_menu_inactive', 'register_user_menu_activity',
                'touch_user_menu_activity', 'set_user_menu_version'}
SCHEMA = '''
CREATE TABLE user_menu_versions (
    user_id INTEGER PRIMARY KEY,
    menu_version TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_user_activity_at TIMESTAMP
);
'''


class GitSource:
    def __init__(self, root, candidate):
        self.root = root
        self.candidate = candidate

    def __str__(self):
        return str(self.root) + '@' + self.candidate + ':src/database/models.py'

    def read_text(self, encoding='utf-8-sig'):
        result = subprocess.run(
            ['git', '-c', 'safe.directory=' + self.root.resolve().as_posix(), '-C', str(self.root),
             'show', self.candidate + ':src/database/models.py'],
            capture_output=True, env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace'))
        return result.stdout.decode(encoding)


def database_class(source):
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Database')
    methods = [n for n in original.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in METHOD_NAMES]
    for method in methods:
        method.decorator_list = []
    namespace = dict(aiosqlite=aiosqlite, asyncio=asyncio, sqlite3=sqlite3,
                     datetime=datetime, timedelta=timedelta, timezone=timezone,
                     logging=logging, logger=logging.getLogger('activity-regression'))
    lightweight = ast.parse('class Database:\n    def __init__(self, db_path):\n        self.db_path = db_path\n').body[0]
    lightweight.body.extend(methods)
    exec(compile(ast.Module(body=[lightweight], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['Database']


def menu_schema_migration(source):
    """Execute only the real menu-table CREATE and its column migrations."""
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    create_tables = next(n for n in ast.walk(tree)
                         if isinstance(n, ast.AsyncFunctionDef) and n.name == 'create_tables')
    calls = [n for n in ast.walk(create_tables)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == 'execute' and n.args
             and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
             and 'CREATE TABLE IF NOT EXISTS user_menu_versions' in n.args[0].value]
    assert len(calls) == 1, 'Expected exactly one real menu-table CREATE'
    migrations = [n for n in ast.walk(create_tables)
                  if isinstance(n, ast.If) and 'menu_columns' in ast.dump(n.test)
                  and any(isinstance(value, ast.Constant) and value.value in
                          ('last_seen_at', 'last_user_activity_at') for value in ast.walk(n.test))]
    wrapper = ast.parse('''async def migrate(db_path):
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute('PRAGMA table_info(user_menu_versions)')
        menu_columns = {row[1] for row in await cursor.fetchall()}
        await db.commit()
''')
    body = wrapper.body[0].body[0].body
    body.insert(0, ast.Expr(value=ast.Await(value=calls[0])))
    body[-1:-1] = migrations
    namespace = dict(aiosqlite=aiosqlite)
    exec(compile(ast.fix_missing_locations(wrapper), str(source) + ':menu-schema', 'exec'), namespace)
    return namespace['migrate']


class MenuActivityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ram = '/dev/shm' if Path('/dev/shm').is_dir() else None
        self.temporary = tempfile.TemporaryDirectory(prefix='menu-activity-', dir=ram)
        self.addCleanup(self.temporary.cleanup)
        self.path = str(Path(self.temporary.name) / 'activity.sqlite')
        self.database = database_class(SOURCE)(self.path)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executescript(SCHEMA)

    def insert(self, user_id=101, activity=None, last_seen='2000-01-01 00:00:00',
               version='version-before', updated='2020-02-02 02:02:02'):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('INSERT INTO user_menu_versions VALUES (?, ?, ?, ?, ?)',
                               (user_id, version, updated, last_seen, activity))
            connection.commit()

    def row(self, user_id=101):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute('SELECT * FROM user_menu_versions WHERE user_id=?', (user_id,)).fetchone()
            return dict(row) if row else None

    def utc_time(self, modifier):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute("SELECT datetime('now', ?)", (modifier,)).fetchone()[0]

    async def test_legacy_old_timestamp_without_trusted_activity_is_not_inactive(self):
        self.insert(activity=None, last_seen='2000-01-01 00:00:00')
        self.assertFalse(await self.database.is_user_menu_inactive(101, 30),
                         'Legacy last_seen_at must never be treated as trusted user activity')
        self.assertIsNone(self.row()['last_user_activity_at'])

    async def test_yesterday_is_active_despite_old_legacy_timestamp(self):
        self.insert(activity=self.utc_time('-1 day'))
        self.assertFalse(await self.database.is_user_menu_inactive(101, 30))

    async def test_thirty_one_days_is_inactive_despite_recent_legacy_timestamp(self):
        self.insert(activity=self.utc_time('-31 days'), last_seen=self.utc_time('0 days'))
        self.assertTrue(await self.database.is_user_menu_inactive(101, 30))

    async def test_threshold_is_inclusive_and_uses_requested_days(self):
        self.insert(activity=self.utc_time('-30 days'))
        self.assertTrue(await self.database.is_user_menu_inactive(101, 30))
        self.assertFalse(await self.database.is_user_menu_inactive(101, 31))
        self.insert(user_id=102, activity=self.utc_time('-29 days'))
        self.assertFalse(await self.database.is_user_menu_inactive(102, 30))

    async def test_utc_iso_timestamp_is_compared_as_date_not_lexical_text(self):
        yesterday = self.utc_time('-1 day').replace(' ', 'T') + 'Z'
        month_ago = self.utc_time('-31 days').replace(' ', 'T') + 'Z'
        self.insert(user_id=101, activity=yesterday)
        self.insert(user_id=102, activity=month_ago)
        self.assertFalse(await self.database.is_user_menu_inactive(101, 30))
        self.assertTrue(await self.database.is_user_menu_inactive(102, 30))

    async def test_unknown_and_invalid_activity_are_not_inactive(self):
        self.assertFalse(await self.database.is_user_menu_inactive(999, 30))
        for user_id, value in enumerate([None, '', 'not-a-date', '0000-invalid'], 101):
            self.insert(user_id=user_id, activity=value)
            self.assertFalse(await self.database.is_user_menu_inactive(user_id, 30))

    async def test_menu_version_change_never_initializes_trusted_activity(self):
        self.insert(activity=None)
        await self.database.set_user_menu_version(101, 'new-version')
        self.assertEqual(self.row()['menu_version'], 'new-version')
        self.assertIsNone(self.row()['last_user_activity_at'])
        await self.database.set_user_menu_version(102, 'new-user-menu')
        self.assertIsNone(self.row(102)['last_user_activity_at'])

    async def test_menu_version_change_preserves_existing_trusted_activity(self):
        prior = self.utc_time('-31 days')
        self.insert(activity=prior)
        await self.database.set_user_menu_version(101, 'new-version')
        self.assertEqual(self.row()['last_user_activity_at'], prior)
        self.assertTrue(await self.database.is_user_menu_inactive(101, 30))

    async def test_new_actor_is_recorded_without_delivering_a_menu(self):
        self.assertFalse(await self.database.register_user_menu_activity(101, 30))
        row = self.row()
        self.assertIsNotNone(row)
        self.assertEqual(row['menu_version'], '')
        self.assertIsNotNone(row['last_user_activity_at'])
        self.assertFalse(await self.database.is_user_menu_inactive(101, 30))

    async def test_actual_activity_preserves_existing_menu_and_other_fields(self):
        self.insert(activity=self.utc_time('-31 days'))
        old = self.row()
        self.assertTrue(await self.database.register_user_menu_activity(101, 30))
        new = self.row()
        for column in ['user_id', 'menu_version', 'updated_at', 'last_seen_at']:
            self.assertEqual(new[column], old[column], column)
        self.assertNotEqual(new['last_user_activity_at'], old['last_user_activity_at'])
        self.assertFalse(await self.database.register_user_menu_activity(101, 30))

    async def test_touch_tracks_unknown_and_existing_users(self):
        self.assertIsNone(await self.database.touch_user_menu_activity(101))
        self.assertIsNotNone(self.row()['last_user_activity_at'])
        self.insert(user_id=102, activity=self.utc_time('-31 days'))
        old = self.row(102)
        self.assertIsNone(await self.database.touch_user_menu_activity(102))
        for column in ['menu_version', 'updated_at', 'last_seen_at']:
            self.assertEqual(self.row(102)[column], old[column])
        self.assertFalse(await self.database.is_user_menu_inactive(102, 30))

    async def test_activity_is_already_saved_if_downstream_handler_fails(self):
        self.insert(activity=self.utc_time('-31 days'))
        self.assertTrue(await self.database.register_user_menu_activity(101, 30))
        try:
            raise RuntimeError('simulated handler failure after recording event')
        except RuntimeError:
            pass
        self.assertFalse(await self.database.register_user_menu_activity(101, 30))

    async def test_concurrent_events_only_first_reports_inactive(self):
        self.insert(activity=self.utc_time('-31 days'))
        replies = await asyncio.gather(*[
            self.database.register_user_menu_activity(101, 30) for _ in range(12)])
        self.assertEqual(sum(value is True for value in replies), 1)
        self.assertEqual(len(replies), 12)
        self.assertFalse(await self.database.is_user_menu_inactive(101, 30))

    async def test_busy_database_is_best_effort_and_does_not_guess_inactivity(self):
        self.insert(activity=self.utc_time('-31 days'))
        with closing(sqlite3.connect(self.path)) as blocker:
            blocker.execute('BEGIN EXCLUSIVE')
            for function, args in [
                (self.database.is_user_menu_inactive, (101, 30)),
                (self.database.register_user_menu_activity, (101, 30)),
                (self.database.touch_user_menu_activity, (101,))]:
                started = asyncio.get_running_loop().time()
                returned = await function(*args)
                if function == self.database.touch_user_menu_activity:
                    self.assertIsNone(returned)
                else:
                    self.assertIs(returned, False)
                self.assertLess(asyncio.get_running_loop().time() - started, 2.5)
            blocker.rollback()
        self.assertTrue(await self.database.register_user_menu_activity(101, 30))

    async def test_missing_table_does_not_raise_or_report_inactive(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('DROP TABLE user_menu_versions')
            connection.commit()
        self.assertFalse(await self.database.is_user_menu_inactive(101, 30))
        self.assertFalse(await self.database.register_user_menu_activity(101, 30))
        self.assertIsNone(await self.database.touch_user_menu_activity(101))

    async def test_cancellation_is_not_hidden(self):
        for name, args in [('is_user_menu_inactive', (101, 30)),
                           ('register_user_menu_activity', (101, 30)),
                           ('touch_user_menu_activity', (101,))]:
            with patch.object(aiosqlite, 'connect', side_effect=asyncio.CancelledError()):
                with self.assertRaises(asyncio.CancelledError):
                    await getattr(self.database, name)(*args)

    async def test_schema_upgrade_from_updated_only_does_not_seed_activity(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('DROP TABLE user_menu_versions')
            connection.execute('''CREATE TABLE user_menu_versions (
                user_id INTEGER PRIMARY KEY, menu_version TEXT NOT NULL, updated_at TIMESTAMP)''')
            connection.execute('INSERT INTO user_menu_versions VALUES (?, ?, ?)',
                               (101, 'legacy-version', '2000-01-01 00:00:00'))
            connection.commit()
        migrate = menu_schema_migration(SOURCE)
        await migrate(self.path)
        await migrate(self.path)
        row = self.row()
        self.assertEqual(row['menu_version'], 'legacy-version')
        self.assertEqual(row['updated_at'], '2000-01-01 00:00:00')
        self.assertIn('last_seen_at', row)
        self.assertIsNone(row['last_seen_at'])
        self.assertIn('last_user_activity_at', row)
        self.assertIsNone(row['last_user_activity_at'])
        self.assertFalse(await self.database.is_user_menu_inactive(101, 30))

    async def test_schema_upgrade_from_last_seen_preserves_legacy_without_seeding(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('DROP TABLE user_menu_versions')
            connection.execute('''CREATE TABLE user_menu_versions (
                user_id INTEGER PRIMARY KEY, menu_version TEXT NOT NULL,
                updated_at TIMESTAMP, last_seen_at TIMESTAMP)''')
            connection.execute('INSERT INTO user_menu_versions VALUES (?, ?, ?, ?)',
                               (101, 'legacy-version', '2001-02-03 04:05:06', '2000-01-01 00:00:00'))
            connection.commit()
        migrate = menu_schema_migration(SOURCE)
        await migrate(self.path)
        await migrate(self.path)
        row = self.row()
        self.assertEqual(row['menu_version'], 'legacy-version')
        self.assertEqual(row['updated_at'], '2001-02-03 04:05:06')
        self.assertEqual(row['last_seen_at'], '2000-01-01 00:00:00')
        self.assertIn('last_user_activity_at', row)
        self.assertIsNone(row['last_user_activity_at'])
        self.assertFalse(await self.database.is_user_menu_inactive(101, 30))


def main():
    global SOURCE
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--candidate')
    parser.add_argument('--legacy-proof', action='store_true')
    args = parser.parse_args()
    if args.candidate:
        if args.root is None:
            parser.error('--root is required with --candidate')
        SOURCE = GitSource(args.root, args.candidate)
    else:
        SOURCE = args.source
    if args.legacy_proof:
        suite = unittest.TestSuite([MenuActivityTests(
            'test_legacy_old_timestamp_without_trusted_activity_is_not_inactive')])
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        print(stream.getvalue())
        assert len(result.failures) == 1 and not result.errors, 'Expected legacy false-positive was not reproduced'
        print('LEGACY FALSE-POSITIVE REPRODUCED: one targeted regression failed on old code')
    else:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(MenuActivityTests))
        if not result.wasSuccessful():
            sys.exit(1)


if __name__ == '__main__':
    main()
