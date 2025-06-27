import aiosqlite
from datetime import datetime

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    client_code TEXT UNIQUE,
                    pet_name TEXT,
                    pet_type TEXT,
                    country TEXT DEFAULT 'RU',
                    registration_date TIMESTAMP,
                    role TEXT DEFAULT 'client',
                    is_active BOOLEAN DEFAULT TRUE
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
            
            # Упрощенная таблица для кодов активации (без срока действия)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS activation_codes (
                    code TEXT PRIMARY KEY,
                    role TEXT,
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
            
            await db.commit()
            await self._migrate_database(db)
    
    async def _migrate_database(self, db):
        """Проверка и обновление структуры БД"""
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # Миграция старых ролей на новые
        if 'role' in column_names:
            await db.execute("UPDATE users SET role = 'client' WHERE role = 'user'")
            await db.execute("UPDATE users SET role = 'staff' WHERE role IN ('moderator', 'vip')")
        
        if 'country' not in column_names:
            await db.execute("ALTER TABLE users ADD COLUMN country TEXT DEFAULT 'RU'")
            
        await db.commit()
    
    async def add_user(self, telegram_id: int, username: str, 
                      client_code: str, pet_name: str, pet_type: str, country: str = 'RU'):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO users (telegram_id, username, client_code, 
                                     pet_name, pet_type, country, registration_date, role)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (telegram_id, username, client_code, pet_name, 
                     pet_type, country, datetime.now(), 'client'))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False
            except Exception as e:
                print(f"Error adding user: {e}")
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
        """Обновление роли пользователя (навсегда)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE users SET role = ? WHERE telegram_id = ?',
                (role, telegram_id)
            )
            await db.commit()
    
    async def check_activation_code(self, code: str):
        """Проверка кода активации"""
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
    
    async def create_activation_code(self, code: str, role: str):
        """Создание одноразового кода активации"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO activation_codes (code, role, created_at)
                    VALUES (?, ?, ?)
                ''', (code.upper(), role, datetime.now()))
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
    
    async def add_request_stat(self, user_id: int, request_type: str, 
                              request_text: str):
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
        """Получение статистики для администраторов"""
        async with aiosqlite.connect(self.db_path) as db:
             # Статистика пользователей
            cursor = await db.execute(
                "SELECT role, COUNT(*) FROM users GROUP BY role"
            )
            role_stats = await cursor.fetchall()
        
            stats = {
                'total_users': 0,
                'clients': 0,
                'staff': 0,
                'admins': 0
            }
        
            for role, count in role_stats:
                stats['total_users'] += count
                if role == 'client':
                    stats['clients'] = count
                elif role == 'staff':
                    stats['staff'] = count
                elif role == 'admin':
                    stats['admins'] = count
        
            # Статистика обращений
            cursor = await db.execute(
                "SELECT request_type, COUNT(*) FROM request_statistics GROUP BY request_type"
            )
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
        
            # Статистика feedback
            cursor = await db.execute(
                "SELECT feedback_type, COUNT(*) FROM feedback GROUP BY feedback_type"
            )
            feedback_stats = await cursor.fetchall()
        
            stats['suggestions'] = 0
            stats['complaints'] = 0
        
            for fb_type, count in feedback_stats:
                if fb_type == 'suggestion':
                    stats['suggestions'] = count
                elif fb_type == 'complaint':
                    stats['complaints'] = count
        
            return stats