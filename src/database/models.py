from typing import Optional
import aiosqlite
from datetime import datetime, timedelta

from src.data_vectorization import DataProcessor

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.test_processor = DataProcessor()
        
    async def add_search_history(self, user_id: int, search_query: str, 
                           found_test_code: str = None, search_type: str = 'text', 
                           success: bool = True):
        """Добавляет запись в историю поиска"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO search_history (user_id, search_query, found_test_code, 
                                        search_type, success, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, search_query, found_test_code, search_type, success, datetime.now()))
            await db.commit()

    async def update_user_frequent_test(self, user_id: int, test_code: str, test_name: str):
        """Обновляет частоту использования теста пользователем"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO user_frequent_tests (user_id, test_code, test_name, frequency, last_accessed)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(user_id, test_code) DO UPDATE SET
                    frequency = frequency + 1,
                    test_name = excluded.test_name,
                    last_accessed = excluded.last_accessed
            ''', (user_id, test_code, test_name, datetime.now()))
            await db.commit()

    async def get_user_frequent_tests(self, user_id: int, limit: int = 10) -> list:
        """Получает частые тесты пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT test_code, test_name, frequency, last_accessed
                FROM user_frequent_tests
                WHERE user_id = ?
                ORDER BY frequency DESC, last_accessed DESC
                LIMIT ?
            ''', (user_id, limit))
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_recent_searches(self, user_id: int, limit: int = 10) -> list:
        """Получает последние поиски пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT search_query, found_test_code, search_type, success, created_at
                FROM search_history
                WHERE user_id = ? AND success = TRUE
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))
            
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_related_tests(self, user_id: int, test_code_1: str, test_code_2: str):
        """Обновляет корреляцию между тестами для пользователя"""
        # Всегда сохраняем в алфавитном порядке для консистентности
        if test_code_1 > test_code_2:
            test_code_1, test_code_2 = test_code_2, test_code_1
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO related_tests (user_id, test_code_1, test_code_2, 
                                        correlation_count, last_correlation)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(user_id, test_code_1, test_code_2) DO UPDATE SET
                    correlation_count = correlation_count + 1,
                    last_correlation = excluded.last_correlation
            ''', (user_id, test_code_1, test_code_2, datetime.now()))
            await db.commit()

    async def get_user_related_tests(self, user_id: int, test_code: str, limit: int = 5) -> list:
        """Получает тесты, которые пользователь часто ищет вместе с данным"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT 
                    CASE 
                        WHEN test_code_1 = ? THEN test_code_2 
                        ELSE test_code_1 
                    END as related_code,
                    correlation_count
                FROM related_tests
                WHERE user_id = ? AND (test_code_1 = ? OR test_code_2 = ?)
                ORDER BY correlation_count DESC, last_correlation DESC
                LIMIT ?
            ''', (test_code, user_id, test_code, test_code, limit))
            
            rows = await cursor.fetchall()
            related_codes = [dict(row) for row in rows]
            
            # Получаем полную информацию о связанных тестах
            result = []
            for item in related_codes:
                test_info = await self.get_test_by_code(item['related_code'])
                if test_info:
                    test_info['correlation_count'] = item['correlation_count']
                    result.append(test_info)
            
            return result

    async def get_search_suggestions(self, user_id: int, query: str = "") -> list:
        """Получает персонализированные подсказки для поиска"""
        suggestions = []
        
        # 1. Частые тесты пользователя
        frequent_tests = await self.get_user_frequent_tests(user_id, limit=20)
        
        # 2. Недавние успешные поиски
        recent_searches = await self.get_recent_searches(user_id, limit=10)
        
        # Фильтруем по запросу если он есть
        if query:
            query_upper = query.upper()
            query_lower = query.lower()
            
            # Фильтруем частые тесты
            for test in frequent_tests:
                if (query_upper in test['test_code'] or 
                    query_lower in test['test_name'].lower()):
                    suggestions.append({
                        'type': 'frequent',
                        'code': test['test_code'],
                        'name': test['test_name'],
                        'frequency': test['frequency']
                    })
            
            # Фильтруем недавние поиски
            seen_codes = {s['code'] for s in suggestions}
            for search in recent_searches:
                if search['found_test_code'] and search['found_test_code'] not in seen_codes:
                    if query_lower in search['search_query'].lower():
                        # Получаем информацию о тесте
                        test_info = await self.get_test_by_code(search['found_test_code'])
                        if test_info:
                            suggestions.append({
                                'type': 'recent',
                                'code': test_info['test_code'],
                                'name': test_info['test_name'],
                                'original_query': search['search_query']
                            })
        else:
            # Без запроса показываем топ частых
            for test in frequent_tests[:3]:
                suggestions.append({
                    'type': 'frequent',
                    'code': test['test_code'],
                    'name': test['test_name'],
                    'frequency': test['frequency']
                })
            
            # Добавляем недавние поиски
            seen_codes = {s['code'] for s in suggestions}
            for search in recent_searches[:2]:
                if search['found_test_code'] and search['found_test_code'] not in seen_codes:
                    # Получаем информацию о тесте
                    test_info = await self.get_test_by_code(search['found_test_code'])
                    if test_info:
                        suggestions.append({
                            'type': 'recent',
                            'code': test_info['test_code'],
                            'name': test_info['test_name'],
                            'original_query': search['search_query']
                        })
                        seen_codes.add(test_info['test_code'])
        
        return suggestions[:10]  # Максимум 10 подсказок

    async def get_user_search_stats(self, user_id: int) -> dict:
        """Получает статистику поисков пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            # Общее количество поисков
            cursor = await db.execute('''
                SELECT COUNT(*) as total,
                    SUM(CASE WHEN success = TRUE THEN 1 ELSE 0 END) as successful,
                    COUNT(DISTINCT found_test_code) as unique_tests
                FROM search_history
                WHERE user_id = ?
            ''', (user_id,))
            
            stats = await cursor.fetchone()
            
            # Самый частый тест
            cursor = await db.execute('''
                SELECT test_code, test_name, frequency
                FROM user_frequent_tests
                WHERE user_id = ?
                ORDER BY frequency DESC
                LIMIT 1
            ''', (user_id,))
            
            most_frequent = await cursor.fetchone()
            
            return {
                'total_searches': stats[0] or 0,
                'successful_searches': stats[1] or 0,
                'unique_tests': stats[2] or 0,
                'success_rate': (stats[1] / stats[0] * 100) if stats[0] else 0,
                'most_frequent_test': dict(most_frequent) if most_frequent else None
            }

    async def cleanup_old_search_history(self, days: int = 90):
        """Удаляет старую историю поисков"""
        async with aiosqlite.connect(self.db_path) as db:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            cursor = await db.execute('''
                DELETE FROM search_history
                WHERE created_at < ?
            ''', (cutoff_date,))
            
            deleted = cursor.rowcount
            await db.commit()
            
            return deleted
        
    async def initialize(self):
        """Initialize database and vector store"""
        await self.create_tables()
        self.test_processor.load_vector_store()
    
    async def create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    search_query TEXT,
                    found_test_code TEXT,
                    search_type TEXT CHECK(search_type IN ('code', 'text', 'voice')),
                    success BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            ''')
            
            # Таблица частых тестов пользователя
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_frequent_tests (
                    user_id INTEGER,
                    test_code TEXT,
                    test_name TEXT,
                    frequency INTEGER DEFAULT 1,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, test_code),
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            ''')
            
            # Таблица для связанных тестов (часто ищутся вместе)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS related_tests (
                    user_id INTEGER,
                    test_code_1 TEXT,
                    test_code_2 TEXT,
                    correlation_count INTEGER DEFAULT 1,
                    last_correlation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, test_code_1, test_code_2),
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id)
                )
            ''')
            
            await db.commit()
            # Обновленная таблица пользователей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    user_type TEXT CHECK(user_type IN ('client', 'employee')),
                    
                    -- Общие поля
                    name TEXT,
                    country TEXT DEFAULT 'BY',
                    registration_date TIMESTAMP,
                    role TEXT DEFAULT 'user',
                    is_active BOOLEAN DEFAULT TRUE,
                    
                    -- Поля для клиентов (ветеринарные клиники)
                    client_code TEXT,  -- Убрали UNIQUE, так как в одной клинике может быть много врачей
                    specialization TEXT,
                    
                    -- Поля для сотрудников
                    region TEXT,
                    department_function TEXT CHECK(department_function IN ('laboratory', 'sales', 'support', NULL))
                )
            ''')
        
            # Таблица для жалоб и предложений
            await db.execute('''
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    feedback_type TEXT,
                    message TEXT,
                    timestamp TIMESTAMP,
                    status TEXT DEFAULT 'new',
                    FOREIGN KEY (user_id) REFERENCES users (telegram_id)
                )
            ''')
            
            # Упрощенная таблица для кодов активации (только для админов)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS activation_codes (
                    code TEXT PRIMARY KEY,
                    role TEXT DEFAULT 'admin',
                    is_used BOOLEAN DEFAULT FALSE,
                    used_by INTEGER,
                    used_at TIMESTAMP,
                    created_at TIMESTAMP
                )
            ''')
            
            # Таблица для статистики запросов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS request_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    request_type TEXT,
                    request_text TEXT,
                    timestamp TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (telegram_id)
                )
            ''')
            
            # Таблица для памяти разговоров
            await db.execute('''
                CREATE TABLE IF NOT EXISTS conversation_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT CHECK(type IN ('buffer','summary')),
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()
    
    async def add_client(self, telegram_id: int, name: str, client_code: str, 
                        specialization: str, country: str = 'BY'):
        """Добавление клиента (ветеринарной клиники)"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO users (telegram_id, user_type, name, client_code, 
                                     specialization, country, registration_date, role)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (telegram_id, 'client', name, client_code, specialization, 
                     country, datetime.now(), 'user'))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
    
    async def add_employee(self, telegram_id: int, name: str, region: str, 
                          department_function: str, country: str = 'BY'):
        """Добавление сотрудника"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO users (telegram_id, user_type, name, region, 
                                     department_function, country, registration_date, role)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (telegram_id, 'employee', name, region, department_function, 
                     country, datetime.now(), 'user'))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
    
    async def get_user(self, telegram_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM users WHERE telegram_id = ?', 
                (telegram_id,)
            )
            return await cursor.fetchone()
    
    async def get_user_role(self, telegram_id: int):
        user = await self.get_user(telegram_id)
        return user['role'] if user else None
    
    async def update_user_role(self, telegram_id: int, role: str):
        """Обновление роли пользователя (только для админа)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE users SET role = ? WHERE telegram_id = ?',
                (role, telegram_id)
            )
            await db.commit()
    
    async def check_activation_code(self, code: str):
        """Проверка кода активации администратора"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM activation_codes 
                WHERE code = ? AND is_used = FALSE
            ''', (code.upper(),))
            return await cursor.fetchone()
    
    async def use_activation_code(self, code: str, user_id: int):
        """Использование кода активации"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE activation_codes 
                SET is_used = TRUE, used_by = ?, used_at = ?
                WHERE code = ?
            ''', (user_id, datetime.now(), code.upper()))
            await db.commit()
    
    async def create_admin_code(self, code: str):
        """Создание одноразового кода активации администратора"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO activation_codes (code, role, created_at)
                    VALUES (?, 'admin', ?)
                ''', (code.upper(), datetime.now()))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
    
    async def user_exists(self, telegram_id: int):
        user = await self.get_user(telegram_id)
        return user is not None
    
    async def add_request_stat(self, user_id: int, request_type: str, request_text: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO request_statistics (user_id, request_type, 
                                              request_text, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, request_type, request_text, datetime.now()))
            await db.commit()
    
    async def add_feedback(self, user_id: int, feedback_type: str, message: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO feedback (user_id, feedback_type, message, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, feedback_type, message, datetime.now()))
            await db.commit()

    async def get_statistics(self):
        """Получение статистики для администратора"""
        async with aiosqlite.connect(self.db_path) as db:
            # Статистика пользователей
            cursor = await db.execute("SELECT user_type, COUNT(*) FROM users GROUP BY user_type")
            type_stats = await cursor.fetchall()

            stats = {'total_users': 0, 'clients': 0, 'employees': 0, 'admins': 0}
            for user_type, count in type_stats:
                stats['total_users'] += count
                if user_type == 'client':
                    stats['clients'] = count
                elif user_type == 'employee':
                    stats['employees'] = count

            # Считаем админов отдельно
            cursor = await db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            admin_count = await cursor.fetchone()
            stats['admins'] = admin_count[0] if admin_count else 0

            # Статистика запросов
            cursor = await db.execute("SELECT request_type, COUNT(*) FROM request_statistics GROUP BY request_type")
            request_stats = await cursor.fetchall()

            stats['total_requests'] = 0
            stats['questions'] = 0
            stats['callbacks'] = 0
            for req_type, count in request_stats:
                stats['total_requests'] += count
                if req_type == 'question':
                    stats['questions'] = count
                elif req_type == 'callback_request':
                    stats['callbacks'] = count

            # Статистика обратной связи
            cursor = await db.execute("SELECT feedback_type, COUNT(*) FROM feedback GROUP BY feedback_type")
            feedback_stats = await cursor.fetchall()

            stats['suggestions'] = 0
            stats['complaints'] = 0
            for fb_type, count in feedback_stats:
                if fb_type == 'suggestion':
                    stats['suggestions'] = count
                elif fb_type == 'complaint':
                    stats['complaints'] = count

            return stats
        
    async def add_memory(self, user_id: int, type: str, content: str):
        """Сохранение памяти разговора"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO conversation_memory (user_id, type, content)
                VALUES (?, ?, ?)
            ''', (user_id, type, content))
            await db.commit()

    async def get_buffer(self, user_id: int) -> list[str]:
        """Получение буфера сообщений"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT content FROM conversation_memory
                WHERE user_id = ? AND type = 'buffer'
                ORDER BY timestamp
            ''', (user_id,))
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

    async def clear_buffer(self, user_id: int):
        """Очистка буфера сообщений"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                DELETE FROM conversation_memory
                WHERE user_id = ? AND type = 'buffer'
            ''', (user_id,))
            await db.commit()

    async def get_latest_summary(self, user_id: int) -> str | None:
        """Получение последней сводки разговора"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT content FROM conversation_memory
                WHERE user_id = ? AND type = 'summary'
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (user_id,))
            row = await cursor.fetchone()
            return row[0] if row else None

    # Новые методы для администраторов
    async def get_broadcast_recipients(self, broadcast_type: str) -> list:
        """Получить список ID получателей для рассылки"""
        async with aiosqlite.connect(self.db_path) as db:
            if broadcast_type == 'all':
                query = "SELECT telegram_id FROM users WHERE is_active = TRUE"
            elif broadcast_type == 'clients':
                query = "SELECT telegram_id FROM users WHERE user_type = 'client' AND is_active = TRUE"
            elif broadcast_type == 'employees':
                query = "SELECT telegram_id FROM users WHERE user_type = 'employee' AND is_active = TRUE"
            else:
                return []
            
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def get_recent_users(self, limit: int = 10) -> list:
        """Получить последних зарегистрированных пользователей"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM users 
                ORDER BY registration_date DESC 
                LIMIT ?
            ''', (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_recent_feedback(self, limit: int = 5) -> list:
        """Получить последние обращения"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT f.*, u.name as user_name 
                FROM feedback f
                LEFT JOIN users u ON f.user_id = u.telegram_id
                ORDER BY f.timestamp DESC 
                LIMIT ?
            ''', (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def clear_old_logs(self, days: int = 30) -> int:
        """Очистить старые записи логов"""
        async with aiosqlite.connect(self.db_path) as db:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            cursor = await db.execute('''
                DELETE FROM conversation_memory 
                WHERE timestamp < ?
            ''', (cutoff_date,))
            
            deleted_count = cursor.rowcount
            
            cursor = await db.execute('''
                DELETE FROM request_statistics 
                WHERE timestamp < ?
            ''', (cutoff_date,))
            
            deleted_count += cursor.rowcount
            
            await db.commit()
            return deleted_count

    async def get_uptime(self) -> str:
        """Получить время работы системы"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT MIN(registration_date) FROM users
            ''')
            first_registration = await cursor.fetchone()
            
            if first_registration and first_registration[0]:
                first_date = datetime.fromisoformat(first_registration[0])
                uptime = datetime.now() - first_date
                
                days = uptime.days
                hours = uptime.seconds // 3600
                minutes = (uptime.seconds % 3600) // 60
                
                return f"{days} дней, {hours} часов, {minutes} минут"
            
            return "Нет данных"
        
    async def get_test_by_code(self, code: str) -> Optional[dict]:
        """
        Find test by exact code match using ChromaDB.
        
        Args:
            code: Test code to search for (case insensitive)
            
        Returns:
            Dictionary with test data or None if not found
        """
        try:
            # Search in ChromaDB with test code filter
            results = self.test_processor.search_test(
                query="",
                filter_dict={"test_code": code.upper()},
                top_k=1
            )
            
            if not results:
                return None
                
            doc = results[0][0]
            return {
                'test_code': doc.metadata['test_code'],
                'test_name': doc.metadata['test_name'],
                'container_type': doc.metadata['container_type'],
                'preanalytics': doc.metadata['preanalytics'],
                'storage_temp': doc.metadata['storage_temp'],
                'department': doc.metadata['department']
            }
        except Exception as e:
            print(f"[ERROR] Failed to search test by code: {e}")
            return None
