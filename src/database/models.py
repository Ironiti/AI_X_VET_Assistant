import json
from typing import Optional
import aiosqlite
from datetime import datetime, timedelta
import re

from src.data_vectorization import DataProcessor

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.test_processor = DataProcessor()
        
    async def get_unique_container_types(self) -> list[str]:
        """Получает уникальные типы контейнеров из базы тестов (из обоих полей)"""
        try:
            if not self.test_processor.vector_store:
                self.test_processor.load_vector_store()
            
            all_tests = self.test_processor.search_test(query="", top_k=2000)
            
            container_types = set()
            
            for doc, _ in all_tests:
                # Получаем типы контейнеров из ОБОИХ полей
                container_fields = [
                    doc.metadata.get('primary_container_type', '').strip(),  # ПРИОРИТЕТ
                    doc.metadata.get('container_type', '').strip()
                ]
                
                for container_type_raw in container_fields:
                    if not container_type_raw or container_type_raw.lower() in ['не указан', 'нет', '-', '', 'none', 'null']:
                        continue
                    
                    # Убираем переносы строк, лишние пробелы и кавычки
                    container_type_raw = container_type_raw.replace('"', '').replace('\n', ' ')
                    container_type_raw = ' '.join(container_type_raw.split())
                    
                    # Разбиваем по *I* если есть несколько контейнеров
                    if '*I*' in container_type_raw:
                        parts = container_type_raw.split('*I*')
                    else:
                        parts = [container_type_raw]
                    
                    for part in parts:
                        container_type = part.strip()
                        if container_type:
                            # ВАЖНО: Нормализуем - первая буква каждого слова заглавная
                            normalized = ' '.join(word.capitalize() for word in container_type.split())
                            container_types.add(normalized)
            
            # Возвращаем отсортированный список уникальных типов
            return sorted(list(container_types))
            
        except Exception as e:
            print(f"[ERROR] Failed to get container types: {e}")
            return []
        
    async def log_chat_interaction(
        self, 
        user_id: int, 
        user_name: str, 
        question: str, 
        bot_response: str, 
        request_type: str = 'question',
        search_success: bool = True,
        found_test_code: str = None
    ):
        """
        Сохраняет взаимодействие пользователя с ботом
        
        Args:
            user_id: Telegram ID пользователя
            user_name: Имя пользователя
            question: Вопрос пользователя
            bot_response: Ответ бота
            request_type: Тип запроса (question/code_search/name_search/general)
            search_success: Успешность поиска
            found_test_code: Найденный код теста (если применимо)
        """
        try:
            # Обрезаем слишком длинные ответы
            if len(bot_response) > 5000:
                bot_response = bot_response[:4997] + "..."
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO chat_history 
                    (user_id, user_name, question, bot_response, request_type, 
                    search_success, found_test_code, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id, 
                    user_name, 
                    question, 
                    bot_response, 
                    request_type,
                    search_success,
                    found_test_code,
                    datetime.now()
                ))
                
                await db.commit()
                return True
        except Exception as e:
            print(f"[ERROR] Failed to log chat interaction: {e}")
            return False
        
    async def update_poll_media(self, poll_id, media_file_id, media_type):
        """Добавление благодарственного медиа к опросу"""
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем, существует ли колонка, если нет - создаем
            cursor = await db.execute("PRAGMA table_info(polls)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'thank_you_media' not in column_names:
                await db.execute('ALTER TABLE polls ADD COLUMN thank_you_media TEXT')
            if 'thank_you_media_type' not in column_names:
                await db.execute('ALTER TABLE polls ADD COLUMN thank_you_media_type TEXT')
            
            await db.execute(
                "UPDATE polls SET thank_you_media = ?, thank_you_media_type = ? WHERE id = ?",
                (media_file_id, media_type, poll_id)
            )
            await db.commit()

    async def get_poll_info(self, poll_id):
        """Получение информации об опросе"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM polls WHERE id = ?",
                (poll_id,)
            )
            row = await cursor.fetchone()
            if row:
                result = dict(row)
                # Для обратной совместимости
                if result.get('thank_you_media'):
                    result['thank_you_video'] = result['thank_you_media']
                return result
            return None
        
    async def update_poll_video(self, poll_id, video_file_id):
        """Добавление благодарственного видео к опросу"""
        async with aiosqlite.connect(self.db_path) as db:
            # Добавляем колонку если её нет
            await db.execute('''
                ALTER TABLE polls ADD COLUMN thank_you_video TEXT
            ''')
            
            await db.execute(
                "UPDATE polls SET thank_you_video = ? WHERE id = ?",
                (video_file_id, poll_id)
            )
            await db.commit()
        
    async def create_poll(self, title, description, questions, created_by):
        """Создание нового опроса"""
        async with aiosqlite.connect(self.db_path) as db:
            # Создаем таблицы для опросов если их нет
            await db.execute('''
                CREATE TABLE IF NOT EXISTS polls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    created_by INTEGER,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS poll_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    poll_id INTEGER,
                    question_text TEXT NOT NULL,
                    question_type TEXT NOT NULL,
                    options TEXT,
                    question_order INTEGER,
                    FOREIGN KEY (poll_id) REFERENCES polls (id)
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS poll_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    poll_id INTEGER,
                    question_id INTEGER,
                    user_id INTEGER,
                    answer TEXT,
                    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (poll_id) REFERENCES polls (id),
                    FOREIGN KEY (question_id) REFERENCES poll_questions (id)
                )
            ''')
            
            # Вставляем опрос
            cursor = await db.execute(
                "INSERT INTO polls (title, description, created_by) VALUES (?, ?, ?)",
                (title, description, created_by)
            )
            poll_id = cursor.lastrowid
            
            # Вставляем вопросы
            for idx, question in enumerate(questions):
                options_json = json.dumps(question.get('options')) if question.get('options') else None
                await db.execute(
                    "INSERT INTO poll_questions (poll_id, question_text, question_type, options, question_order) VALUES (?, ?, ?, ?, ?)",
                    (poll_id, question['text'], question['type'], options_json, idx + 1)
                )
            
            await db.commit()
            return poll_id

    async def check_user_poll_participation(self, user_id, poll_id):
        """Проверка участия пользователя в опросе"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM poll_responses WHERE user_id = ? AND poll_id = ?",
                (user_id, poll_id)
            )
            count = await cursor.fetchone()
            return count[0] > 0

    async def get_poll_questions(self, poll_id):
        """Получение вопросов опроса"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id, question_text, question_type, options
                FROM poll_questions
                WHERE poll_id = ?
                ORDER BY question_order
            ''', (poll_id,))
            
            rows = await cursor.fetchall()
            questions = []
            for row in rows:
                questions.append({
                    'id': row[0],
                    'text': row[1],
                    'type': row[2],
                    'options': json.loads(row[3]) if row[3] else None
                })
            return questions
        
    async def get_container_photo(self, container_type: str):
        """Получает фото контейнера по типу"""
        try:
            await self.ensure_container_photos_table()
            # Нормализуем тип контейнера при поиске
            normalized_type = ' '.join(word.capitalize() for word in container_type.split())
            
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    'SELECT file_id, description FROM container_photos WHERE container_type = ?',
                    (normalized_type,)
                )
                row = await cursor.fetchone()
                
                # Если не нашли точное совпадение, пробуем без учета регистра
                if not row:
                    cursor = await db.execute(
                        'SELECT file_id, description FROM container_photos WHERE LOWER(container_type) = LOWER(?)',
                        (container_type.strip(),)
                    )
                    row = await cursor.fetchone()
                
                if row:
                    return {'file_id': row[0], 'description': row[1]}
                
                # Для отладки
                print(f"[DEBUG] No photo found for container type: '{normalized_type}'")
                return None
        except Exception as e:
            print(f"[ERROR] Failed to get container photo: {e}")
            return None

    async def delete_container_photo(self, container_type: str):
        """Удаляет фото контейнера по типу"""
        try:
            await self.ensure_container_photos_table()
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    'DELETE FROM container_photos WHERE container_type = ?', 
                    (container_type,)
                )
                deleted = cursor.rowcount > 0
                await db.commit()
                return deleted
        except Exception as e:
            print(f"[ERROR] Failed to delete container photo: {e}")
            return False

    async def save_poll_response(self, poll_id, question_id, user_id, answer):
        """Сохранение ответа пользователя на вопрос опроса"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO poll_responses (poll_id, question_id, user_id, answer) VALUES (?, ?, ?, ?)",
                (poll_id, question_id, user_id, answer)
            )
            await db.commit()

    async def get_active_polls(self):
        """Получение активных опросов"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT 
                    p.id,
                    p.title,
                    p.description,
                    p.created_at,
                    COUNT(DISTINCT pq.id) as questions_count,
                    COUNT(DISTINCT pr.user_id) as responses_count
                FROM polls p
                LEFT JOIN poll_questions pq ON p.id = pq.poll_id
                LEFT JOIN poll_responses pr ON p.id = pr.poll_id
                WHERE p.is_active = 1
                GROUP BY p.id
                ORDER BY p.created_at DESC
            ''')
            
            rows = await cursor.fetchall()
            polls = []
            for row in rows:
                polls.append({
                    'id': row[0],
                    'title': row[1],
                    'description': row[2],
                    'created_at': row[3],
                    'questions_count': row[4],
                    'responses_count': row[5]
                })
            return polls

    async def get_polls_with_results(self):
        """Получение опросов с результатами"""
        async with aiosqlite.connect(self.db_path) as db:
            # Получаем все опросы
            cursor = await db.execute('''
                SELECT 
                    p.id,
                    p.title,
                    COUNT(DISTINCT pr.user_id) as total_responses
                FROM polls p
                LEFT JOIN poll_responses pr ON p.id = pr.poll_id
                GROUP BY p.id
                HAVING total_responses > 0
                ORDER BY p.created_at DESC
            ''')
            
            polls_data = await cursor.fetchall()
            polls = []
            
            for poll_row in polls_data:
                poll_id = poll_row[0]
                
                # Получаем вопросы для каждого опроса
                q_cursor = await db.execute('''
                    SELECT id, question_text, question_type, options
                    FROM poll_questions
                    WHERE poll_id = ?
                    ORDER BY question_order
                ''', (poll_id,))
                
                questions_data = await q_cursor.fetchall()
                questions = []
                
                for q_row in questions_data:
                    question_id = q_row[0]
                    question = {
                        'text': q_row[1],
                        'type': q_row[2]
                    }
                    
                    if q_row[2] == 'rating':
                        # Для рейтинга считаем среднее
                        avg_cursor = await db.execute('''
                            SELECT AVG(CAST(answer as REAL))
                            FROM poll_responses
                            WHERE question_id = ? AND answer IS NOT NULL
                        ''', (question_id,))
                        avg_row = await avg_cursor.fetchone()
                        question['avg_rating'] = avg_row[0] if avg_row[0] else 0
                        
                    elif q_row[2] in ['single', 'multiple']:
                        # Для вариантов считаем самый популярный
                        top_cursor = await db.execute('''
                            SELECT answer, COUNT(*) as cnt
                            FROM poll_responses
                            WHERE question_id = ?
                            GROUP BY answer
                            ORDER BY cnt DESC
                            LIMIT 1
                        ''', (question_id,))
                        top_row = await top_cursor.fetchone()
                        question['top_answer'] = top_row[0] if top_row else 'Нет ответов'
                        
                    else:  # text
                        # Для текстовых просто считаем количество
                        count_cursor = await db.execute('''
                            SELECT COUNT(*)
                            FROM poll_responses
                            WHERE question_id = ?
                        ''', (question_id,))
                        count_row = await count_cursor.fetchone()
                        question['answer_count'] = count_row[0]
                    
                    questions.append(question)
                
                polls.append({
                    'title': poll_row[1],
                    'total_responses': poll_row[2],
                    'questions': questions
                })
            
            return polls

    async def get_full_poll_results(self):
        """Получение полных результатов опросов для выгрузки"""
        async with aiosqlite.connect(self.db_path) as db:
            # Получаем все опросы
            cursor = await db.execute('''
                SELECT 
                    p.id,
                    p.title,
                    p.description,
                    p.is_active,
                    p.created_at,
                    COUNT(DISTINCT pr.user_id) as total_responses
                FROM polls p
                LEFT JOIN poll_responses pr ON p.id = pr.poll_id
                GROUP BY p.id
                ORDER BY p.created_at DESC
            ''')
            
            polls_data = await cursor.fetchall()
            polls = []
            
            for poll_row in polls_data:
                poll_id = poll_row[0]
                
                # Получаем вопросы
                q_cursor = await db.execute('''
                    SELECT id, question_text, question_type, options
                    FROM poll_questions
                    WHERE poll_id = ?
                    ORDER BY question_order
                ''', (poll_id,))
                
                questions_data = await q_cursor.fetchall()
                questions = []
                
                for q_row in questions_data:
                    question_id = q_row[0]
                    question_type = q_row[2]
                    options = json.loads(q_row[3]) if q_row[3] else None
                    
                    question = {
                        'text': q_row[1],
                        'type': question_type
                    }
                    
                    if question_type == 'rating':
                        # Получаем все оценки с информацией о пользователях
                        rating_cursor = await db.execute('''
                            SELECT pr.answer, COUNT(*) as cnt
                            FROM poll_responses pr
                            WHERE pr.question_id = ?
                            GROUP BY pr.answer
                        ''', (question_id,))
                        ratings = await rating_cursor.fetchall()
                        
                        total = sum(r[1] for r in ratings)
                        sum_rating = sum(int(r[0]) * r[1] for r in ratings if r[0])
                        question['avg_rating'] = sum_rating / total if total > 0 else 0
                        
                        # Добавляем детальную информацию
                        detail_cursor = await db.execute('''
                            SELECT pr.answer, u.name, u.telegram_id
                            FROM poll_responses pr
                            LEFT JOIN users u ON pr.user_id = u.telegram_id
                            WHERE pr.question_id = ?
                        ''', (question_id,))
                        details = await detail_cursor.fetchall()
                        question['detailed_answers'] = [
                            {
                                'answer': d[0],
                                'user_name': d[1] or f'ID: {d[2]}',
                                'user_id': d[2]
                            }
                            for d in details
                        ]
                        
                    elif question_type in ['single', 'multiple']:
                        # Статистика по вариантам
                        question['options_stats'] = []
                        if options:
                            for option in options:
                                count_cursor = await db.execute('''
                                    SELECT COUNT(*)
                                    FROM poll_responses
                                    WHERE question_id = ? AND answer LIKE ?
                                ''', (question_id, f'%{option}%'))
                                count = (await count_cursor.fetchone())[0]
                                
                                total_cursor = await db.execute('''
                                    SELECT COUNT(DISTINCT user_id)
                                    FROM poll_responses
                                    WHERE question_id = ?
                                ''', (question_id,))
                                total = (await total_cursor.fetchone())[0]
                                
                                percentage = (count / total * 100) if total > 0 else 0
                                question['options_stats'].append({
                                    'text': option,
                                    'count': count,
                                    'percentage': percentage
                                })
                        
                        # Добавляем детальную информацию
                        detail_cursor = await db.execute('''
                            SELECT pr.answer, u.name, u.telegram_id, u.client_code
                            FROM poll_responses pr
                            LEFT JOIN users u ON pr.user_id = u.telegram_id
                            WHERE pr.question_id = ?
                        ''', (question_id,))
                        details = await detail_cursor.fetchall()
                        question['detailed_answers'] = [
                            {
                                'answer': d[0],
                                'user_name': d[1] or f'ID: {d[2]}',
                                'user_id': d[2],
                                'client_code': d[3]
                            }
                            for d in details
                        ]
                        
                    else:  # text
                        # Получаем все текстовые ответы с информацией о пользователях
                        text_cursor = await db.execute('''
                            SELECT 
                                pr.answer,
                                u.name,
                                u.telegram_id,
                                u.client_code,
                                u.user_type,
                                pr.answered_at
                            FROM poll_responses pr
                            LEFT JOIN users u ON pr.user_id = u.telegram_id
                            WHERE pr.question_id = ? AND pr.answer IS NOT NULL
                            ORDER BY pr.answered_at DESC
                        ''', (question_id,))
                        text_answers = await text_cursor.fetchall()
                        
                        question['text_answers'] = [a[0] for a in text_answers]
                        question['text_answers_detailed'] = [
                            {
                                'answer': a[0],
                                'user_name': a[1] or f'ID: {a[2]}',
                                'user_id': a[2],
                                'client_code': a[3],
                                'user_type': a[4],
                                'answered_at': a[5]
                            }
                            for a in text_answers
                        ]
                    
                    questions.append(question)
                
                polls.append({
                    'id': poll_row[0],
                    'title': poll_row[1],
                    'description': poll_row[2],
                    'is_active': poll_row[3],
                    'created_at': poll_row[4],
                    'total_responses': poll_row[5],
                    'questions': questions
                })
            
            return polls       
        
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
        
    async def ensure_container_photos_table(self):
        """Создает таблицу container_photos если её нет"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS container_photos (
                    container_type TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    description TEXT,
                    uploaded_by INTEGER,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (uploaded_by) REFERENCES users(telegram_id)
                )
            ''')
            await db.commit()
            
    async def add_container_photo(self, container_type: str, file_id: str, uploaded_by: int, description: str = None):
        """Добавляет или обновляет фото для типа контейнера"""
        try:
            await self.ensure_container_photos_table()
            # Нормализуем тип контейнера при сохранении (каждое слово с заглавной буквы)
            normalized_type = ' '.join(word.capitalize() for word in container_type.split())
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR REPLACE INTO container_photos 
                    (container_type, file_id, uploaded_by, description, upload_date)
                    VALUES (?, ?, ?, ?, ?)
                ''', (normalized_type, file_id, uploaded_by, description, datetime.now()))
                
                await db.commit()
                print(f"[INFO] Saved photo for container: '{normalized_type}'")
                return True
        except Exception as e:
            print(f"[ERROR] Failed to add container photo: {e}")
            return False

    async def get_container_photo(self, container_type: str):
        """Получает фото контейнера по типу"""
        try:
            await self.ensure_container_photos_table()
            # Нормализуем тип контейнера при поиске
            normalized_type = ' '.join(word.capitalize() for word in container_type.split())
            
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    'SELECT file_id, description FROM container_photos WHERE container_type = ?',
                    (normalized_type,)
                )
                row = await cursor.fetchone()
                
                # Если не нашли точное совпадение, пробуем без учета регистра
                if not row:
                    cursor = await db.execute(
                        'SELECT file_id, description FROM container_photos WHERE LOWER(container_type) = LOWER(?)',
                        (container_type.strip(),)
                    )
                    row = await cursor.fetchone()
                
                if row:
                    return {'file_id': row[0], 'description': row[1]}
                
                # Для отладки
                print(f"[DEBUG] No photo found for container type: '{normalized_type}'")
                return None
        except Exception as e:
            print(f"[ERROR] Failed to get container photo: {e}")
            return None

    async def delete_container_photo(self, container_type: str):
        """Удаляет фото контейнера по типу"""
        try:
            await self.ensure_container_photos_table()
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    'DELETE FROM container_photos WHERE container_type = ?', 
                    (container_type,)
                )
                deleted = cursor.rowcount > 0
                await db.commit()
                return deleted
        except Exception as e:
            print(f"[ERROR] Failed to delete container photo: {e}")
            return False

    async def get_test_by_code(self, code: str) -> Optional[dict]:
        """
        Find test by exact code match using ChromaDB.
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
                
            doc = results[0][0] if isinstance(results[0], tuple) else results[0]
            return {
                'test_code': doc.metadata['test_code'],
                'test_name': doc.metadata['test_name'],
                'container_type': doc.metadata.get('container_type', ''),
                'primary_container_type': doc.metadata.get('primary_container_type', ''),  # ВАЖНО!
                'preanalytics': doc.metadata.get('preanalytics', ''),
                'storage_temp': doc.metadata.get('storage_temp', ''),
                'department': doc.metadata.get('department', '')
            }
        except Exception as e:
            print(f"[ERROR] Failed to search test by code: {e}")
            return None 
        
    async def get_all_container_photos(self):
        """Получает все фото контейнеров"""
        try:
            await self.ensure_container_photos_table()
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute('''
                    SELECT container_type, file_id, upload_date, description, uploaded_by
                    FROM container_photos 
                    ORDER BY container_type
                ''')
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            print(f"[ERROR] Failed to get all container photos: {e}")
            return []
        
    async def initialize(self):
        """Initialize database and vector store"""
        await self.create_tables()
        self.test_processor.load_vector_store()
    
    async def create_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            # ПРАВИЛЬНАЯ версия таблицы container_photos
            await db.execute('''
                CREATE TABLE IF NOT EXISTS container_photos (
                    container_type TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    description TEXT,
                    uploaded_by INTEGER,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (uploaded_by) REFERENCES users(telegram_id)
                )
            ''')
            
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
            
            # Обновленная таблица пользователей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    user_type TEXT CHECK(user_type IN ('client', 'employee')),
                    
                    -- Общие поля
                    name TEXT,  -- Для клиентов - полное имя
                    country TEXT DEFAULT 'BY',
                    registration_date TIMESTAMP,
                    role TEXT DEFAULT 'user',
                    is_active BOOLEAN DEFAULT TRUE,
                    
                    -- Поля для клиентов (ветеринарные клиники)
                    client_code TEXT,
                    specialization TEXT,
                    
                    -- Поля для сотрудников
                    first_name TEXT,  -- Имя сотрудника
                    last_name TEXT,   -- Фамилия сотрудника
                    region TEXT,
                    department_function TEXT CHECK(department_function IN ('laboratory', 'sales', 'support', NULL))
                )
            ''')
        
            # Таблица для жалоб и предложений с поддержкой медиа
            await db.execute('''
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    feedback_type TEXT,
                    message TEXT,
                    media_type TEXT,
                    media_file_id TEXT,
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
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    user_name TEXT,
                    question TEXT NOT NULL,
                    bot_response TEXT,
                    request_type TEXT DEFAULT 'question',
                    search_success BOOLEAN DEFAULT TRUE,
                    found_test_code TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (telegram_id)
                )
            ''')
            
            # Индекс для ускорения запросов к истории
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_chat_history_user_time 
                ON chat_history(user_id, timestamp DESC)
            ''')
            # ============================================================
            # КОНЕЦ ДОБАВЛЕНИЯ
            # ============================================================
            
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
    
    async def add_employee(self, telegram_id: int, first_name: str, last_name: str, region: str, department_function: str, country: str = 'BY'):
        """Добавление сотрудника с отдельными полями для имени и фамилии"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Создаем полное имя для совместимости
                full_name = f"{last_name} {first_name}"
                
                await db.execute('''
                    INSERT INTO users (telegram_id, user_type, name, first_name, last_name,
                                    region, department_function, country, registration_date, role)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (telegram_id, 'employee', full_name, first_name, last_name, 
                    region, department_function, country, datetime.now(), 'user'))
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
            row = await cursor.fetchone()
            # Преобразуем Row в словарь для удобства
            if row:
                return dict(row)
            return None
    
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
    
    async def get_user_greeting_name(self, telegram_id: int) -> str:
        """Получает имя пользователя для обращения"""
        user = await self.get_user(telegram_id)
        if not user:
            return "пользователь"
        
        if user['user_type'] == 'employee' and user.get('first_name'):
            # Для сотрудников используем только имя
            return user['first_name']
        elif user.get('name'):
            # Для клиентов используем полное имя или только первое слово
            name_parts = user['name'].split()
            return name_parts[0] if name_parts else user['name']
        
        return "пользователь"
    
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
    
    async def add_faq_history(self, user_id: int, faq_id: int, question: str):
            try:
                query = """
                    INSERT INTO faq_history (user_id, faq_id, question, viewed_at)
                    VALUES ($1, $2, $3, NOW())
                """
                await self.pool.execute(query, user_id, faq_id, question)
            except Exception as e:
                print(f"Ошибка сохранения истории FAQ: {e}")

    async def add_request_stat(self, user_id: int, request_type: str, request_text: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO request_statistics (user_id, request_type, 
                                              request_text, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, request_type, request_text, datetime.now()))
            await db.commit()
    
    async def add_feedback(self, user_id: int, feedback_type: str, message: str, 
                          media_type: str = None, media_file_id: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO feedback (user_id, feedback_type, message, 
                                    media_type, media_file_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, feedback_type, message, media_type, 
                 media_file_id, datetime.now()))
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
                'primary_container_type': doc.metadata.get('primary_container_type', ''),
                'preanalytics': doc.metadata['preanalytics'],
                'storage_temp': doc.metadata['storage_temp'],
                'department': doc.metadata['department']
            }
        except Exception as e:
            print(f"[ERROR] Failed to search test by code: {e}")
            return None
    
        