import csv
import io
from datetime import datetime
from pathlib import Path
import aiosqlite
from typing import Optional

class CSVExporter:
    """Резервный экспортер в CSV формат"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def export_all_data_csv(self) -> bytes:
        """Экспорт всех данных в ZIP архив с CSV файлами"""
        import zipfile
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Экспорт пользователей
            users_csv = await self._export_users_csv()
            zip_file.writestr('users.csv', users_csv)
            
            # Экспорт вопросов
            questions_csv = await self._export_questions_csv()
            zip_file.writestr('questions.csv', questions_csv)
            
            # Экспорт звонков
            callbacks_csv = await self._export_callbacks_csv()
            zip_file.writestr('callbacks.csv', callbacks_csv)
            
            # Экспорт обратной связи
            feedback_csv = await self._export_feedback_csv()
            zip_file.writestr('feedback.csv', feedback_csv)
            
            # Добавляем README
            readme_content = self._generate_readme()
            zip_file.writestr('README.txt', readme_content)
        
        zip_buffer.seek(0)
        return zip_buffer.read()
    
    async def _export_users_csv(self) -> str:
        """Экспорт пользователей в CSV"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute('''
                SELECT 
                    telegram_id as "Telegram_ID",
                    name as "Name",
                    CASE user_type
                        WHEN 'client' THEN 'Client'
                        WHEN 'employee' THEN 'Employee'
                        ELSE 'User'
                    END as "User_Type",
                    client_code as "Client_Code",
                    specialization as "Specialization",
                    region as "Region",
                    CASE department_function
                        WHEN 'laboratory' THEN 'Laboratory'
                        WHEN 'sales' THEN 'Sales'
                        WHEN 'support' THEN 'Support'
                        ELSE department_function
                    END as "Department",
                    CASE country
                        WHEN 'BY' THEN 'Belarus'
                        WHEN 'RU' THEN 'Russia'
                        WHEN 'KZ' THEN 'Kazakhstan'
                        WHEN 'AM' THEN 'Armenia'
                        ELSE country
                    END as "Country",
                    CASE role
                        WHEN 'admin' THEN 'Administrator'
                        WHEN 'user' THEN 'User'
                        ELSE role
                    END as "Role",
                    registration_date as "Registration_Date",
                    CASE is_active
                        WHEN 1 THEN 'Active'
                        ELSE 'Inactive'
                    END as "Status"
                FROM users
                ORDER BY registration_date DESC
            ''')
            
            rows = await cursor.fetchall()
            
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=[desc[0] for desc in cursor.description])
                writer.writeheader()
                for row in rows:
                    writer.writerow(dict(row))
            
            return output.getvalue()
    
    async def _export_questions_csv(self) -> str:
        """Экспорт вопросов в CSV"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute('''
                SELECT 
                    rs.id as "ID",
                    u.name as "User_Name",
                    CASE u.user_type
                        WHEN 'client' THEN 'Client'
                        WHEN 'employee' THEN 'Employee'
                        ELSE 'User'
                    END as "User_Type",
                    u.client_code as "Client_Code",
                    rs.request_type as "Request_Type",
                    rs.request_text as "Question",
                    rs.timestamp as "Date_Time"
                FROM request_statistics rs
                LEFT JOIN users u ON rs.user_id = u.telegram_id
                WHERE rs.request_type IN ('question', 'general_question')
                ORDER BY rs.timestamp DESC
            ''')
            
            rows = await cursor.fetchall()
            
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=[desc[0] for desc in cursor.description])
                writer.writeheader()
                for row in rows:
                    writer.writerow(dict(row))
            
            return output.getvalue()
    
    async def _export_callbacks_csv(self) -> str:
        """Экспорт запросов на звонок в CSV"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute('''
                SELECT 
                    rs.id as "ID",
                    u.name as "User_Name",
                    CASE u.user_type
                        WHEN 'client' THEN 'Client'
                        WHEN 'employee' THEN 'Employee'
                        ELSE 'User'
                    END as "User_Type",
                    u.client_code as "Client_Code",
                    u.specialization as "Specialization",
                    rs.request_text as "Request_Details",
                    rs.timestamp as "Date_Time"
                FROM request_statistics rs
                LEFT JOIN users u ON rs.user_id = u.telegram_id
                WHERE rs.request_type = 'callback_request'
                ORDER BY rs.timestamp DESC
            ''')
            
            rows = await cursor.fetchall()
            
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=[desc[0] for desc in cursor.description])
                writer.writeheader()
                for row in rows:
                    writer.writerow(dict(row))
            
            return output.getvalue()
    
    async def _export_feedback_csv(self) -> str:
        """Экспорт обратной связи в CSV"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute('''
                SELECT 
                    f.id as "ID",
                    u.name as "User_Name",
                    CASE u.user_type
                        WHEN 'client' THEN 'Client'
                        WHEN 'employee' THEN 'Employee'
                        ELSE 'User'
                    END as "User_Type",
                    u.client_code as "Client_Code",
                    CASE f.feedback_type
                        WHEN 'suggestion' THEN 'Suggestion'
                        WHEN 'complaint' THEN 'Complaint'
                        ELSE f.feedback_type
                    END as "Feedback_Type",
                    f.message as "Message",
                    f.timestamp as "Date_Time",
                    CASE f.status
                        WHEN 'new' THEN 'New'
                        WHEN 'in_progress' THEN 'In_Progress'
                        WHEN 'resolved' THEN 'Resolved'
                        ELSE f.status
                    END as "Status"
                FROM feedback f
                LEFT JOIN users u ON f.user_id = u.telegram_id
                ORDER BY f.timestamp DESC
            ''')
            
            rows = await cursor.fetchall()
            
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=[desc[0] for desc in cursor.description])
                writer.writeheader()
                for row in rows:
                    writer.writerow(dict(row))
            
            return output.getvalue()
    
    def _generate_readme(self) -> str:
        """Генерирует README файл для архива"""
        return f"""VetUnion Data Export - CSV Format
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Files included:
- users.csv: User accounts and registration data
- questions.csv: Questions asked by users
- callbacks.csv: Callback requests
- feedback.csv: User feedback (suggestions and complaints)

Note: This is a backup CSV export. 
For better formatting, use Excel export when available.

Encoding: UTF-8
Delimiter: comma (,)
"""