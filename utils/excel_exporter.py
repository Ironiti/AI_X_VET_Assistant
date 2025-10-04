import pandas as pd
from datetime import datetime
from pathlib import Path
import aiosqlite
from typing import Optional
import io

class ExcelExporter:
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def export_all_data(self) -> bytes:
        """Экспорт всех данных в Excel (БЕЗ администраторов)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            output = io.BytesIO()
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # Экспорт пользователей
                users_df = await self._get_users_dataframe(db)
                users_df.to_excel(writer, sheet_name='Пользователи', index=False)
                
                # Экспорт вопросов
                questions_df = await self._get_questions_dataframe(db)
                questions_df.to_excel(writer, sheet_name='Вопросы', index=False)
                
                # Экспорт запросов на звонок
                callbacks_df = await self._get_callbacks_dataframe(db)
                callbacks_df.to_excel(writer, sheet_name='Звонки', index=False)
                
                # Экспорт обратной связи
                feedback_df = await self._get_feedback_dataframe(db)
                feedback_df.to_excel(writer, sheet_name='Обратная связь', index=False)
                
                # Форматирование
                workbook = writer.book
                for worksheet in workbook.worksheets():
                    worksheet.set_column('A:Z', 20)
            
            output.seek(0)
            return output.read()
        
    async def export_chat_history(self) -> bytes:
        """Экспорт истории общения с ботом (БЕЗ администраторов)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            output = io.BytesIO()
            chat_df = await self._get_chat_history_dataframe(db)
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                chat_df.to_excel(writer, sheet_name='История общения', index=False)
                
                # Добавляем статистику
                stats_df = self._calculate_chat_stats(chat_df)
                stats_df.to_excel(writer, sheet_name='Статистика', index=False)
                
                # Форматирование
                workbook = writer.book
                worksheet = writer.sheets['История общения']
                
                # Устанавливаем ширину колонок
                worksheet.set_column('A:A', 12)  # ID
                worksheet.set_column('B:B', 20)  # Пользователь
                worksheet.set_column('C:C', 15)  # Тип
                worksheet.set_column('D:D', 15)  # Код клиента
                worksheet.set_column('E:E', 50)  # Вопрос
                worksheet.set_column('F:F', 60)  # Ответ
                worksheet.set_column('G:G', 15)  # Тип запроса
                worksheet.set_column('H:H', 12)  # Успех
                worksheet.set_column('I:I', 15)  # Код теста
                worksheet.set_column('J:J', 20)  # Дата
                
                # Добавляем перенос текста для вопросов и ответов
                wrap_format = workbook.add_format({'text_wrap': True, 'valign': 'top'})
                worksheet.set_column('E:F', None, wrap_format)
                
                # Статистика
                stats_worksheet = writer.sheets['Статистика']
                stats_worksheet.set_column('A:B', 30)
            
            output.seek(0)
            return output.read()

    async def _get_chat_history_dataframe(self, db) -> pd.DataFrame:
        """Получить DataFrame с историей общения (БЕЗ администраторов)"""
        cursor = await db.execute('''
            SELECT 
                ch.id as "ID",
                ch.user_name as "Пользователь",
                CASE u.user_type
                    WHEN 'client' THEN 'Клиент'
                    WHEN 'employee' THEN 'Сотрудник'
                    ELSE 'Пользователь'
                END as "Тип пользователя",
                u.client_code as "Код клиента",
                ch.question as "Вопрос пользователя",
                ch.bot_response as "Ответ бота",
                CASE ch.request_type
                    WHEN 'code_search' THEN 'Поиск по коду'
                    WHEN 'name_search' THEN 'Поиск по названию'
                    WHEN 'text_search' THEN 'Текстовый поиск'
                    WHEN 'callback_selection' THEN 'Выбор из списка'
                    WHEN 'question' THEN 'Вопрос'
                    WHEN 'general' THEN 'Общий вопрос'
                    WHEN 'dialog' THEN 'Вопрос в диалоге'
                    ELSE ch.request_type
                END as "Тип запроса",
                CASE ch.search_success
                    WHEN 1 THEN 'Да'
                    ELSE 'Нет'
                END as "Успешный поиск",
                ch.found_test_code as "Найденный тест",
                ch.timestamp as "Дата и время"
            FROM chat_history ch
            LEFT JOIN users u ON ch.user_id = u.telegram_id
            WHERE u.role != 'admin' OR u.role IS NULL
            ORDER BY ch.timestamp DESC
        ''')
        
        rows = await cursor.fetchall()
        return pd.DataFrame(rows, columns=[desc[0] for desc in cursor.description])

    def _calculate_chat_stats(self, chat_df: pd.DataFrame) -> pd.DataFrame:
        """Рассчитать статистику по истории общения"""
        stats = []
        
        if chat_df.empty:
            return pd.DataFrame([{'Показатель': 'Нет данных', 'Значение': 0}])
        
        # Общая статистика
        stats.append({
            'Показатель': 'Всего взаимодействий',
            'Значение': len(chat_df)
        })
        
        # Уникальные пользователи
        if 'Пользователь' in chat_df.columns:
            unique_users = chat_df['Пользователь'].nunique()
            stats.append({
                'Показатель': 'Уникальных пользователей',
                'Значение': unique_users
            })
        
        # Среднее количество вопросов на пользователя
        if len(stats) > 1:
            avg_questions = len(chat_df) / unique_users
            stats.append({
                'Показатель': 'Среднее вопросов на пользователя',
                'Значение': f'{avg_questions:.1f}'
            })
        
        # По типам запросов
        if 'Тип запроса' in chat_df.columns:
            stats.append({
                'Показатель': '--- Типы запросов ---',
                'Значение': ''
            })
            type_counts = chat_df['Тип запроса'].value_counts()
            for req_type, count in type_counts.items():
                percentage = (count / len(chat_df)) * 100
                stats.append({
                    'Показатель': f'  {req_type}',
                    'Значение': f'{count} ({percentage:.1f}%)'
                })
        
        # Успешность поиска
        if 'Успешный поиск' in chat_df.columns:
            stats.append({
                'Показатель': '--- Успешность ---',
                'Значение': ''
            })
            success_counts = chat_df['Успешный поиск'].value_counts()
            for status, count in success_counts.items():
                percentage = (count / len(chat_df)) * 100
                stats.append({
                    'Показатель': f'  {status}',
                    'Значение': f'{count} ({percentage:.1f}%)'
                })
        
        # По типам пользователей
        if 'Тип пользователя' in chat_df.columns:
            stats.append({
                'Показатель': '--- По типам пользователей ---',
                'Значение': ''
            })
            user_type_counts = chat_df['Тип пользователя'].value_counts()
            for user_type, count in user_type_counts.items():
                percentage = (count / len(chat_df)) * 100
                stats.append({
                    'Показатель': f'  {user_type}',
                    'Значение': f'{count} ({percentage:.1f}%)'
                })
        
        # Самые популярные тесты
        if 'Найденный тест' in chat_df.columns:
            tests_df = chat_df[chat_df['Найденный тест'].notna()]
            if not tests_df.empty:
                stats.append({
                    'Показатель': '--- Топ 10 тестов ---',
                    'Значение': ''
                })
                top_tests = tests_df['Найденный тест'].value_counts().head(10)
                for test, count in top_tests.items():
                    stats.append({
                        'Показатель': f'  {test}',
                        'Значение': count
                    })
        
        # Временная статистика
        if 'Дата и время' in chat_df.columns:
            try:
                chat_df['Дата и время'] = pd.to_datetime(chat_df['Дата и время'])
                
                stats.append({
                    'Показатель': '--- Временные рамки ---',
                    'Значение': ''
                })
                
                first_interaction = chat_df['Дата и время'].min()
                last_interaction = chat_df['Дата и время'].max()
                
                stats.append({
                    'Показатель': '  Первое взаимодействие',
                    'Значение': first_interaction.strftime('%d.%m.%Y %H:%M')
                })
                stats.append({
                    'Показатель': '  Последнее взаимодействие',
                    'Значение': last_interaction.strftime('%d.%m.%Y %H:%M')
                })
                
                # Статистика по дням недели
                chat_df['День недели'] = chat_df['Дата и время'].dt.day_name()
                day_mapping = {
                    'Monday': 'Понедельник',
                    'Tuesday': 'Вторник',
                    'Wednesday': 'Среда',
                    'Thursday': 'Четверг',
                    'Friday': 'Пятница',
                    'Saturday': 'Суббота',
                    'Sunday': 'Воскресенье'
                }
                chat_df['День недели'] = chat_df['День недели'].map(day_mapping)
                
                stats.append({
                    'Показатель': '--- Активность по дням недели ---',
                    'Значение': ''
                })
                day_counts = chat_df['День недели'].value_counts()
                for day, count in day_counts.items():
                    stats.append({
                        'Показатель': f'  {day}',
                        'Значение': count
                    })
            except:
                pass
        
        return pd.DataFrame(stats)
    
    async def export_users(self) -> bytes:
        """Экспорт только пользователей (БЕЗ администраторов)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            output = io.BytesIO()
            users_df = await self._get_users_dataframe(db)
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                users_df.to_excel(writer, sheet_name='Пользователи', index=False)
                
                # Добавляем статистику
                stats_df = self._calculate_user_stats(users_df)
                stats_df.to_excel(writer, sheet_name='Статистика', index=False)
                
                # Форматирование
                workbook = writer.book
                for worksheet in workbook.worksheets():
                    worksheet.set_column('A:Z', 20)
            
            output.seek(0)
            return output.read()
    
    async def export_questions(self) -> bytes:
        """Экспорт только вопросов (БЕЗ вопросов от администраторов)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            output = io.BytesIO()
            questions_df = await self._get_questions_dataframe(db)
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                questions_df.to_excel(writer, sheet_name='Вопросы', index=False)
                
                # Форматирование
                workbook = writer.book
                worksheet = writer.sheets['Вопросы']
                worksheet.set_column('A:A', 15)  # ID
                worksheet.set_column('B:B', 20)  # Пользователь
                worksheet.set_column('C:C', 50)  # Вопрос
                worksheet.set_column('D:D', 20)  # Дата
            
            output.seek(0)
            return output.read()
    
    async def export_callbacks(self) -> bytes:
        """Экспорт только запросов на звонок (БЕЗ запросов от администраторов)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            output = io.BytesIO()
            callbacks_df = await self._get_callbacks_dataframe(db)
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                callbacks_df.to_excel(writer, sheet_name='Звонки', index=False)
                
                # Форматирование
                workbook = writer.book
                worksheet = writer.sheets['Звонки']
                worksheet.set_column('A:Z', 20)
            
            output.seek(0)
            return output.read()
    
    async def export_feedback(self) -> bytes:
        """Экспорт только обратной связи (БЕЗ обращений от администраторов)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            output = io.BytesIO()
            feedback_df = await self._get_feedback_dataframe(db)
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                feedback_df.to_excel(writer, sheet_name='Обратная связь', index=False)
                
                # Форматирование
                workbook = writer.book
                worksheet = writer.sheets['Обратная связь']
                worksheet.set_column('A:Z', 20)
            
            output.seek(0)
            return output.read()
    
    async def _get_users_dataframe(self, db) -> pd.DataFrame:
        """Получить DataFrame с пользователями (БЕЗ администраторов)"""
        cursor = await db.execute('''
            SELECT 
                telegram_id as "Telegram ID",
                name as "Имя",
                CASE user_type
                    WHEN 'client' THEN 'Клиент (ветеринар)'
                    WHEN 'employee' THEN 'Сотрудник'
                    ELSE 'Пользователь'
                END as "Тип пользователя",
                client_code as "Код клиента",
                specialization as "Специализация",
                region as "Регион",
                CASE department_function
                    WHEN 'laboratory' THEN 'Лаборатория'
                    WHEN 'sales' THEN 'Продажи'
                    WHEN 'support' THEN 'Поддержка'
                    ELSE department_function
                END as "Функция",
                CASE country
                    WHEN 'BY' THEN 'Беларусь'
                    WHEN 'RU' THEN 'Россия'
                    WHEN 'KZ' THEN 'Казахстан'
                    WHEN 'AM' THEN 'Армения'
                    ELSE country
                END as "Страна",
                CASE role
                    WHEN 'admin' THEN 'Администратор'
                    WHEN 'user' THEN 'Пользователь'
                    ELSE role
                END as "Роль",
                registration_date as "Дата регистрации",
                CASE is_active
                    WHEN 1 THEN 'Активен'
                    ELSE 'Неактивен'
                END as "Статус"
            FROM users
            WHERE role != 'admin'
            ORDER BY registration_date DESC
        ''')
        
        rows = await cursor.fetchall()
        return pd.DataFrame(rows, columns=[desc[0] for desc in cursor.description])
    
    async def _get_questions_dataframe(self, db) -> pd.DataFrame:
        """Получить DataFrame с вопросами (БЕЗ вопросов от администраторов)"""
        cursor = await db.execute('''
            SELECT 
                rs.id as "ID",
                u.name as "Пользователь",
                u.user_type as user_type_raw,
                u.client_code as "Код клиента",
                rs.request_text as "Вопрос",
                rs.timestamp as "Дата и время"
            FROM request_statistics rs
            LEFT JOIN users u ON rs.user_id = u.telegram_id
            WHERE rs.request_type IN ('question', 'general_question')
              AND (u.role != 'admin' OR u.role IS NULL)
            ORDER BY rs.timestamp DESC
        ''')
        
        rows = await cursor.fetchall()
        df = pd.DataFrame(rows, columns=[desc[0] for desc in cursor.description])
        
        # Добавляем колонку типа пользователя
        if not df.empty:
            df['Тип пользователя'] = df['user_type_raw'].apply(
                lambda x: 'Клиент' if x == 'client' else ('Сотрудник' if x == 'employee' else 'Пользователь')
            )
            df = df.drop('user_type_raw', axis=1)
        
        return df
    
    async def _get_callbacks_dataframe(self, db) -> pd.DataFrame:
        """Получить DataFrame с запросами на звонок (БЕЗ запросов от администраторов)"""
        cursor = await db.execute('''
            SELECT 
                rs.id as "ID",
                u.name as "Пользователь",
                u.user_type as user_type_raw,
                u.client_code as "Код клиента",
                u.specialization as "Специализация",
                rs.request_text as "Детали запроса",
                rs.timestamp as "Дата и время"
            FROM request_statistics rs
            LEFT JOIN users u ON rs.user_id = u.telegram_id
            WHERE rs.request_type = 'callback_request'
              AND (u.role != 'admin' OR u.role IS NULL)
            ORDER BY rs.timestamp DESC
        ''')
        
        rows = await cursor.fetchall()
        df = pd.DataFrame(rows, columns=[desc[0] for desc in cursor.description])
        
        # Извлекаем телефон из текста запроса и добавляем тип пользователя
        if not df.empty:
            df['Телефон'] = df['Детали запроса'].str.extract(r'Телефон: ([^,]+)')
            df['Сообщение'] = df['Детали запроса'].str.extract(r'Сообщение: (.+)')
            df['Тип пользователя'] = df['user_type_raw'].apply(
                lambda x: 'Клиент' if x == 'client' else ('Сотрудник' if x == 'employee' else 'Пользователь')
            )
            df = df.drop(['Детали запроса', 'user_type_raw'], axis=1)
        
        return df
    
    async def _get_feedback_dataframe(self, db) -> pd.DataFrame:
        """Получить DataFrame с обратной связью (БЕЗ обращений от администраторов)"""
        cursor = await db.execute('''
            SELECT 
                f.id as "ID",
                u.name as "Пользователь",
                u.user_type as user_type_raw,
                u.client_code as "Код клиента",
                CASE f.feedback_type
                    WHEN 'suggestion' THEN 'Предложение'
                    WHEN 'complaint' THEN 'Жалоба'
                END as "Тип обращения",
                f.message as "Сообщение",
                f.timestamp as "Дата и время",
                CASE f.status
                    WHEN 'new' THEN 'Новое'
                    WHEN 'in_progress' THEN 'В работе'
                    WHEN 'resolved' THEN 'Решено'
                    ELSE f.status
                END as "Статус"
            FROM feedback f
            LEFT JOIN users u ON f.user_id = u.telegram_id
            WHERE u.role != 'admin' OR u.role IS NULL
            ORDER BY f.timestamp DESC
        ''')
        
        rows = await cursor.fetchall()
        df = pd.DataFrame(rows, columns=[desc[0] for desc in cursor.description])
        
        # Добавляем тип пользователя
        if not df.empty:
            df['Тип пользователя'] = df['user_type_raw'].apply(
                lambda x: 'Клиент' if x == 'client' else ('Сотрудник' if x == 'employee' else 'Пользователь')
            )
            df = df.drop('user_type_raw', axis=1)
        
        return df
    
    def _calculate_user_stats(self, users_df: pd.DataFrame) -> pd.DataFrame:
        """Рассчитать статистику по пользователям"""
        stats = []
        
        # Общая статистика
        stats.append({
            'Показатель': 'Всего пользователей',
            'Значение': len(users_df)
        })
        
        # По типам пользователей
        if 'Тип пользователя' in users_df.columns:
            type_counts = users_df['Тип пользователя'].value_counts()
            for user_type, count in type_counts.items():
                stats.append({
                    'Показатель': f'{user_type}',
                    'Значение': count
                })
        
        # По ролям
        if 'Роль' in users_df.columns:
            role_counts = users_df['Роль'].value_counts()
            for role, count in role_counts.items():
                stats.append({
                    'Показатель': f'Роль: {role}',
                    'Значение': count
                })
        
        # По странам
        if 'Страна' in users_df.columns:
            country_counts = users_df['Страна'].value_counts()
            for country, count in country_counts.items():
                stats.append({
                    'Показатель': f'Из {country}',
                    'Значение': count
                })
        
        # По специализациям (для клиентов)
        if 'Специализация' in users_df.columns:
            spec_df = users_df[users_df['Специализация'].notna()]
            if not spec_df.empty:
                spec_counts = spec_df['Специализация'].value_counts()
                stats.append({
                    'Показатель': '--- Специализации ---',
                    'Значение': ''
                })
                for spec, count in spec_counts.items():
                    stats.append({
                        'Показатель': spec,
                        'Значение': count
                    })
        
        # По функциям (для сотрудников)
        if 'Функция' in users_df.columns:
            func_df = users_df[users_df['Функция'].notna()]
            if not func_df.empty:
                func_counts = func_df['Функция'].value_counts()
                stats.append({
                    'Показатель': '--- Функции сотрудников ---',
                    'Значение': ''
                })
                for func, count in func_counts.items():
                    stats.append({
                        'Показатель': func,
                        'Значение': count
                    })
        
        # Активные/неактивные
        if 'Статус' in users_df.columns:
            status_counts = users_df['Статус'].value_counts()
            for status, count in status_counts.items():
                stats.append({
                    'Показатель': f'Статус: {status}',
                    'Значение': count
                })
        
        return pd.DataFrame(stats)
