import sqlite3
from datetime import datetime

def add_user(user_id: int, username: str = None, full_name: str = None):
    """Добавление нового пользователя"""
    try:
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        
        cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
        """, (user_id, username, full_name))
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Ошибка добавления пользователя: {e}")
        return False

def get_user(user_id: int):
    """Получение информации о пользователе"""
    try:
        conn = sqlite3.connect("bot_database.db")
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        conn.close()
        return user
    except sqlite3.Error as e:
        print(f"Ошибка получения пользователя: {e}")
        return None