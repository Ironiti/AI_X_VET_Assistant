import aiosqlite
from datetime import datetime

class Database:
    def __init__(self, db_path: str):
        """Initialize Database class with provided database path"""
        self.db_path = db_path
        print(f"[INFO] Initialized Database with path: {self.db_path}")

    async def create_tables(self):
        """Create all necessary tables in the database if they do not exist"""
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

            # Create feedback table for complaints and suggestions
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
            print("[INFO] feedback table ensured")

            # Create activation_codes table (simplified without expiration date)
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
            print("[INFO] activation_codes table ensured")
            
            # Create request_statistics table for logging user requests
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

            # New table for conversation memory (buffer + summaries)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS conversation_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT CHECK(type IN ('buffer','summary')),
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            print("[INFO] conversation_memory table ensured")

            await db.commit()
            print("[INFO] Database schema created/updated successfully")

    async def add_user(self, telegram_id: int, username: str, first_name: str, last_name: str,
                       language_code: str, is_bot: bool, chat_type: str,
                       client_code: str = None, pet_name: str = None, pet_type: str = None):
        """Add a user to the database, or ignore if user already exists"""
        print(f"[INFO] Attempting to add user {telegram_id} to database")
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT OR IGNORE INTO users 
                    (telegram_id, username, first_name, last_name, language_code, is_bot, chat_type, client_code, pet_name, pet_type, registration_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    telegram_id, username, first_name, last_name,
                    language_code, is_bot, chat_type,
                    client_code, pet_name, pet_type, datetime.now()
                ))
                await db.commit()
                print(f"[INFO] User {telegram_id} added or already exists")
                return True
            except aiosqlite.IntegrityError as e:
                print(f"[ERROR] IntegrityError adding user {telegram_id}: {e}")
                return False

    async def get_user(self, telegram_id: int):
        """Retrieve a user record from the database by telegram_id"""
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
        """Check if a user exists in the database by telegram_id"""
        exists = await self.get_user(telegram_id) is not None
        print(f"[INFO] user_exists({telegram_id}) -> {exists}")
        return exists

    async def check_client_code_exists(self, client_code: str):
        """Check if a client code already exists in the database"""
        print(f"[INFO] Checking if client code exists: {client_code}")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT telegram_id FROM users WHERE client_code = ?', 
                (client_code,)
            )
            result = await cursor.fetchone()
            exists = result is not None
            print(f"[INFO] client_code_exists({client_code}) -> {exists}")
            return exists

    async def get_user_role(self, telegram_id: int):
        """Retrieve user's role from the database by telegram_id"""
        print(f"[INFO] Fetching role for user {telegram_id}")
        user = await self.get_user(telegram_id)
        role = user['role'] if user else None
        print(f"[INFO] Role for user {telegram_id}: {role}")
        return role

    async def update_user_role(self, telegram_id: int, role: str):
        """Update user's role permanently"""
        print(f"[INFO] Updating role for user {telegram_id} to {role}")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE users SET role = ? WHERE telegram_id = ?',
                (role, telegram_id)
            )
            await db.commit()
            print(f"[INFO] Role updated for user {telegram_id}")

    async def check_activation_code(self, code: str):
        """Check if an activation code is valid and unused"""
        print(f"[INFO] Checking activation code: {code}")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM activation_codes 
                WHERE code = ? AND is_used = FALSE
            ''', (code.upper(),))
            result = await cursor.fetchone()
            print(f"[INFO] Activation code {code} valid: {bool(result)}")
            return result

    async def use_activation_code(self, code: str, user_id: int):
        """Mark an activation code as used by a specific user"""
        print(f"[INFO] Using activation code {code} for user {user_id}")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE activation_codes 
                SET is_used = TRUE, used_by = ?, used_at = ?
                WHERE code = ?
            ''', (user_id, datetime.now(), code.upper()))
            await db.commit()
            print(f"[INFO] Activation code {code} marked as used by user {user_id}")

    async def create_activation_code(self, code: str, role: str):
        """Create a new one-time activation code for a specific role"""
        print(f"[INFO] Creating activation code {code} for role {role}")
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO activation_codes (code, role, created_at)
                    VALUES (?, ?, ?)
                ''', (code.upper(), role, datetime.now()))
                await db.commit()
                print(f"[INFO] Activation code {code} created for role {role}")
                return True
            except aiosqlite.IntegrityError as e:
                print(f"[ERROR] Failed to create activation code {code}: {e}")
                return False

    async def add_request_stat(self, user_id: int, request_type: str, request_text: str):
        """Log a user request statistic to the database"""
        print(f"[INFO] Logging request stat for user {user_id}: {request_type} - {request_text}")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO request_statistics (user_id, request_type, request_text, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, request_type, request_text, datetime.now()))
            await db.commit()
            print(f"[INFO] Request stat logged for user {user_id}")

    async def add_feedback(self, user_id: int, feedback_type: str, message: str):
        """Add feedback (suggestion or complaint) from user"""
        print(f"[INFO] Adding feedback from user {user_id}: {feedback_type}")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO feedback (user_id, feedback_type, message, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, feedback_type, message, datetime.now()))
            await db.commit()
            print(f"[INFO] Feedback added for user {user_id}")

    async def get_statistics(self):
        """Retrieve overall statistics for admin dashboard"""
        print("[INFO] Fetching system statistics")
        async with aiosqlite.connect(self.db_path) as db:
            # Users statistics
            cursor = await db.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
            role_stats = await cursor.fetchall()

            stats = {'total_users': 0, 'clients': 0, 'staff': 0, 'admins': 0}
            for role, count in role_stats:
                stats['total_users'] += count
                if role == 'client':
                    stats['clients'] = count
                elif role == 'staff':
                    stats['staff'] = count
                elif role == 'admin':
                    stats['admins'] = count

            # Request statistics
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

            # Feedback statistics
            cursor = await db.execute("SELECT feedback_type, COUNT(*) FROM feedback GROUP BY feedback_type")
            feedback_stats = await cursor.fetchall()

            stats['suggestions'] = 0
            stats['complaints'] = 0
            for fb_type, count in feedback_stats:
                if fb_type == 'suggestion':
                    stats['suggestions'] = count
                elif fb_type == 'complaint':
                    stats['complaints'] = count

            print(f"[INFO] Statistics fetched: {stats}")
            return stats
        
    async def add_memory(self, user_id: int, type: str, content: str):
        """Store one memory item (either 'buffer' or 'summary') for a user."""
        print(f"[INFO] Adding memory [{type}] for user {user_id}")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO conversation_memory (user_id, type, content)
                VALUES (?, ?, ?)
            ''', (user_id, type, content))
            await db.commit()
            print(f"[INFO] Memory [{type}] saved for user {user_id}")

    async def get_buffer(self, user_id: int) -> list[str]:
        """Return all 'buffer' entries for a user, ordered by insertion."""
        print(f"[INFO] Retrieving buffer for user {user_id}")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT content FROM conversation_memory
                WHERE user_id = ? AND type = 'buffer'
                ORDER BY timestamp
            ''', (user_id,))
            rows = await cursor.fetchall()
            buffer = [r[0] for r in rows]
            print(f"[INFO] Retrieved {len(buffer)} buffer items for user {user_id}")
            return buffer

    async def clear_buffer(self, user_id: int):
        """Delete all 'buffer' entries for a user (leaving summaries intact)."""
        print(f"[INFO] Clearing buffer for user {user_id}")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                DELETE FROM conversation_memory
                WHERE user_id = ? AND type = 'buffer'
            ''', (user_id,))
            await db.commit()
            print(f"[INFO] Buffer cleared for user {user_id}")

    async def get_latest_summary(self, user_id: int) -> str | None:
        """Return the most recent 'summary' for a user, or None if none exists."""
        print(f"[INFO] Retrieving latest summary for user {user_id}")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT content FROM conversation_memory
                WHERE user_id = ? AND type = 'summary'
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (user_id,))
            row = await cursor.fetchone()
            summary = row[0] if row else None
            print(f"[INFO] Latest summary for user {user_id}: {bool(summary)}")
            return summary
