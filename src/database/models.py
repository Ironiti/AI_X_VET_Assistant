# src/database/models.py
import aiosqlite
from datetime import datetime

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Обновленная таблица пользователей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    user_type TEXT CHECK(user_type IN ('client', 'employee')),
                    
                    -- Общие поля
                    name TEXT,
                    registration_date TIMESTAMP,
                    role TEXT DEFAULT 'user',
                    is_active BOOLEAN DEFAULT TRUE,
                    
                    -- Поля для клиентов (ветеринарные клиники)
                    client_code TEXT UNIQUE,
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
            await self._migrate_database(db)
    
    async def _migrate_database(self, db):
        """Миграция старой структуры БД на новую"""
        try:
            # Проверяем существование старой таблицы
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if await cursor.fetchone():
                # Создаем временную таблицу с новой структурой
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS users_new (
                        telegram_id INTEGER PRIMARY KEY,
                        user_type TEXT CHECK(user_type IN ('client', 'employee')),
                        name TEXT,
                        registration_date TIMESTAMP,
                        role TEXT DEFAULT 'user',
                        is_active BOOLEAN DEFAULT TRUE,
                        client_code TEXT UNIQUE,
                        specialization TEXT,
                        region TEXT,
                        department_function TEXT CHECK(department_function IN ('laboratory', 'sales', 'support', NULL))
                    )
                ''')
                
                # Мигрируем данные
                await db.execute('''
                    INSERT OR IGNORE INTO users_new (telegram_id, user_type, name, registration_date, role, is_active, client_code)
                    SELECT telegram_id, 'client', username, registration_date, 
                           CASE WHEN role IN ('staff', 'moderator', 'vip') THEN 'user' ELSE role END, 
                           is_active, client_code
                    FROM users
                ''')
                
                # Удаляем старую таблицу и переименовываем новую
                await db.execute("DROP TABLE users")
                await db.execute("ALTER TABLE users_new RENAME TO users")
            
            await db.commit()
        except Exception as e:
            print(f"Migration error: {e}")
    
    async def add_client(self, telegram_id: int, name: str, client_code: str, specialization: str):
        """Добавление клиента (ветеринарной клиники)"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO users (telegram_id, user_type, name, client_code, 
                                     specialization, registration_date, role)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (telegram_id, 'client', name, client_code, specialization, 
                     datetime.now(), 'user'))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
    
    async def add_employee(self, telegram_id: int, name: str, region: str, department_function: str):
        """Добавление сотрудника"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO users (telegram_id, user_type, name, region, 
                                     department_function, registration_date, role)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (telegram_id, 'employee', name, region, department_function, 
                     datetime.now(), 'user'))
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
    
    async def check_client_code_exists(self, client_code: str):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT telegram_id FROM users WHERE client_code = ?', 
                (client_code,)
            )
            result = await cursor.fetchone()
            return result is not None
    
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