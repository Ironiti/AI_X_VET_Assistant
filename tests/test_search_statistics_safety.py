"""Statistics failures must not interrupt a user response."""
import ast
import asyncio
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite


METHODS = {
    'add_request_stat': (101, 'code_search', 'AN118FOL'),
    'add_search_history': (101, 'AN118FOL', 'AN118FOL', 'code', True),
    'update_user_frequent_test': (101, 'AN118FOL', 'Test name'),
    'update_related_tests': (101, 'AN118FOL', 'AN116'),
}


def load_database_methods():
    path = Path(__file__).resolve().parents[1] / 'src/database/models.py'
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    database = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Database')
    methods = [n for n in database.body if isinstance(n, ast.AsyncFunctionDef) and n.name in METHODS]
    assert len(methods) == len(METHODS)
    namespace = dict(aiosqlite=aiosqlite, datetime=datetime)
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), 'exec'), namespace)
    return {name: namespace[name] for name in METHODS}


SCHEMA = '''
CREATE TABLE request_statistics (user_id, request_type, request_text, timestamp);
CREATE TABLE search_history (user_id, search_query, found_test_code, search_type, success, created_at);
CREATE TABLE user_frequent_tests (user_id, test_code, test_name, frequency, last_accessed,
                                UNIQUE(user_id, test_code));
CREATE TABLE related_tests (user_id, test_code_1, test_code_2, correlation_count, last_correlation,
                           UNIQUE(user_id, test_code_1, test_code_2));
'''


class SearchStatisticsSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'stats.db'
        self.database = SimpleNamespace(db_path=str(self.path))
        self.methods = load_database_methods()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executescript(SCHEMA)

    async def test_successful_statistics_are_preserved(self):
        for name, args in METHODS.items():
            with self.subTest(method=name):
                await self.methods[name](self.database, *args)
        with closing(sqlite3.connect(self.path)) as connection:
            for table in ['request_statistics', 'search_history', 'user_frequent_tests', 'related_tests']:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT request_text FROM request_statistics').fetchone()[0], 'AN118FOL')
            self.assertEqual(connection.execute('SELECT test_code_1, test_code_2 FROM related_tests').fetchone(), ('AN116', 'AN118FOL'))

    async def test_repeated_statistics_keep_counter_and_update_name(self):
        await self.methods['update_user_frequent_test'](self.database, 101, 'AN118FOL', 'Old name')
        await self.methods['update_user_frequent_test'](self.database, 101, 'AN118FOL', 'New name')
        await self.methods['update_related_tests'](self.database, 101, 'AN118FOL', 'AN116')
        await self.methods['update_related_tests'](self.database, 101, 'AN116', 'AN118FOL')
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT frequency, test_name FROM user_frequent_tests').fetchone(), (2, 'New name'))
            self.assertEqual(connection.execute('SELECT correlation_count FROM related_tests').fetchone()[0], 2)

    async def test_locked_statistics_still_allow_answer(self):
        with closing(sqlite3.connect(self.path)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            for name, args in METHODS.items():
                with self.subTest(method=name):
                    answer = AsyncMock()
                    started = asyncio.get_running_loop().time()
                    await self.methods[name](self.database, *args)
                    await answer('User response')
                    answer.assert_awaited_once_with('User response')
                    self.assertLess(asyncio.get_running_loop().time() - started, 2.0)
            blocker.rollback()

    async def test_statistics_resume_after_lock_is_released(self):
        with closing(sqlite3.connect(self.path)) as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            await self.methods['add_request_stat'](self.database, *METHODS['add_request_stat'])
            blocker.rollback()
        await self.methods['add_request_stat'](self.database, *METHODS['add_request_stat'])
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM request_statistics').fetchone()[0], 1)

    async def test_unavailable_database_does_not_interrupt_answer(self):
        for name, args in METHODS.items():
            with self.subTest(method=name):
                with patch.object(aiosqlite, 'connect', side_effect=aiosqlite.OperationalError('unable to open database file')):
                    await self.methods[name](self.database, *args)

    async def test_failed_commit_does_not_interrupt_answer(self):
        for name, args in METHODS.items():
            with self.subTest(method=name):
                connection = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock(side_effect=aiosqlite.OperationalError('disk I/O error')))
                context = MagicMock()
                context.__aenter__ = AsyncMock(return_value=connection)
                context.__aexit__ = AsyncMock(return_value=False)
                with patch.object(aiosqlite, 'connect', return_value=context):
                    await self.methods[name](self.database, *args)

    async def test_cancellation_and_programming_errors_are_not_hidden(self):
        for name, args in METHODS.items():
            for error in [asyncio.CancelledError(), ValueError('programming error')]:
                with self.subTest(method=name, error=type(error).__name__):
                    with patch.object(aiosqlite, 'connect', side_effect=error):
                        with self.assertRaises(type(error)):
                            await self.methods[name](self.database, *args)


if __name__ == '__main__':
    unittest.main()
