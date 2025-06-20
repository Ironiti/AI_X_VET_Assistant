import aiosqlite
from datetime import datetime

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        print(f"[INFO] Initialized Database with path: {self.db_path}")
    
    async def create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Create users table with extended metadata
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language_code TEXT,
                    is_bot BOOLEAN,
                    chat_type TEXT,
                    client_code TEXT UNIQUE,
                    pet_name TEXT,
                    pet_type TEXT,
                    registration_date TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            print("[INFO] users table ensured")

            # Create request_statistics table
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
            print("[INFO] request_statistics table ensured")

            await db.commit()
            print("[INFO] Database schema created/updated successfully")

    async def add_user(self,
                       telegram_id: int,
                       username: str,
                       first_name: str,
                       last_name: str,
                       language_code: str,
                       is_bot: bool,
                       chat_type: str,
                       client_code: str = None,
                       pet_name: str = None,
                       pet_type: str = None):
        print(f"[INFO] Attempting to add user {telegram_id} to database")
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT OR IGNORE INTO users 
                    (telegram_id, username, first_name, last_name, language_code, is_bot, chat_type, client_code, pet_name, pet_type, registration_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    telegram_id,
                    username,
                    first_name,
                    last_name,
                    language_code,
                    is_bot,
                    chat_type,
                    client_code,
                    pet_name,
                    pet_type,
                    datetime.now()
                ))
                await db.commit()
                print(f"[INFO] User {telegram_id} added or already exists")
                return True
            except aiosqlite.IntegrityError as e:
                print(f"[ERROR] IntegrityError adding user {telegram_id}: {e}")
                return False

    async def get_user(self, telegram_id: int):
        print(f"[INFO] Fetching user {telegram_id} from database")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM users WHERE telegram_id = ?',
                (telegram_id,)
            )
            row = await cursor.fetchone()
            print(f"[INFO] Retrieved user: {dict(row) if row else None}")
            return row

    async def user_exists(self, telegram_id: int):
        exists = await self.get_user(telegram_id) is not None
        print(f"[INFO] user_exists({telegram_id}) -> {exists}")
        return exists

    async def add_request_stat(self, user_id: int, request_type: str, request_text: str):
        print(f"[INFO] Logging request stat for user {user_id}: {request_type} - {request_text}")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO request_statistics (user_id, request_type, request_text, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, request_type, request_text, datetime.now()))
            await db.commit()
            print(f"[INFO] Request stat logged for user {user_id}")
