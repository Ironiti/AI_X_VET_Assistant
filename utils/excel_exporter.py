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
        """Экспорт всех данных в Excel"""
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
    
    async def export_users(self) -> bytes:
        """Экспорт только пользователей"""
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
        """Экспорт только вопросов"""
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
        """Экспорт только запросов на звонок"""
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
        """Экспорт только обратной связи"""
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
        """Получить DataFrame с пользователями для новой структуры БД"""
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
            ORDER BY registration_date DESC
        ''')
        
        rows = await cursor.fetchall()
        return pd.DataFrame(rows, columns=[desc[0] for desc in cursor.description])
    
    async def _get_questions_dataframe(self, db) -> pd.DataFrame:
        """Получить DataFrame с вопросами"""
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
        """Получить DataFrame с запросами на звонок"""
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
        """Получить DataFrame с обратной связью"""
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