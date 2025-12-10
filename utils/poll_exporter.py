import io
import xlsxwriter
from datetime import datetime

class PollExporter:
    async def export_polls_to_excel(self, polls_data):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        
        # Стили
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4CAF50',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        subheader_format = workbook.add_format({
            'bold': True,
            'bg_color': '#E8F5E9',
            'border': 1
        })
        
        # ВАЖНО: Числовой формат для ячеек
        number_format = workbook.add_format({
            'num_format': '0',  # Целое число без десятичных
            'border': 1
        })
        
        text_format = workbook.add_format({
            'border': 1,
            'text_wrap': True,
            'valign': 'top'
        })
        
        # Лист со сводкой
        summary_sheet = workbook.add_worksheet('Сводка')
        summary_headers = ['Название опроса', 'Всего участников', 'Дата создания', 'Статус']
        
        for col, header in enumerate(summary_headers):
            summary_sheet.write(0, col, header, header_format)
        
        row = 1
        for poll in polls_data:
            summary_sheet.write(row, 0, poll['title'])
            summary_sheet.write(row, 1, poll['total_responses'], number_format)
            summary_sheet.write(row, 2, poll['created_at'])
            summary_sheet.write(row, 3, 'Активен' if poll['is_active'] else 'Завершен')
            row += 1
        
        # Автоподбор ширины колонок
        summary_sheet.set_column(0, 0, 40)
        summary_sheet.set_column(1, 1, 15)
        summary_sheet.set_column(2, 2, 20)
        summary_sheet.set_column(3, 3, 15)
        
        # Создаем отдельный лист для каждого опроса
        for poll in polls_data:
            sheet_name = f"Опрос_{poll['id']}"[:31]
            worksheet = workbook.add_worksheet(sheet_name)
            
            # Заголовок опроса
            worksheet.merge_range(0, 0, 0, len(poll['questions']) + 2, poll['title'], header_format)
            if poll.get('description'):
                worksheet.merge_range(1, 0, 1, len(poll['questions']) + 2, poll['description'], subheader_format)
                current_row = 3
            else:
                current_row = 2
            
            # НОВАЯ СТРУКТУРА: По человеку (горизонтально)
            # Собираем уникальных пользователей
            users_dict = {}  # user_id -> {name, client_code, user_type, answers}
            
            for q_idx, question in enumerate(poll['questions'], 1):
                question_key = f"q_{q_idx}"
                
                # Собираем ответы по всем типам вопросов
                if question.get('detailed_answers'):
                    for detail in question['detailed_answers']:
                        user_id = detail.get('user_id')
                        if user_id not in users_dict:
                            # Определяем роль пользователя
                            user_type = detail.get('user_type', '')
                            if user_type == 'client':
                                role_display = 'Клиент'
                            elif user_type == 'employee':
                                role_display = 'Сотрудник'
                            else:
                                role_display = '-'
                            
                            users_dict[user_id] = {
                                'name': detail.get('user_name', 'Неизвестный'),
                                'user_id': user_id,
                                'client_code': detail.get('client_code', '-'),
                                'user_type': role_display,
                                'answers': {}
                            }
                        users_dict[user_id]['answers'][question_key] = detail.get('answer', '')
                
                if question.get('text_answers_detailed'):
                    for detail in question['text_answers_detailed']:
                        user_id = detail.get('user_id')
                        if user_id not in users_dict:
                            # Определяем роль пользователя
                            user_type = detail.get('user_type', '')
                            if user_type == 'client':
                                role_display = 'Клиент'
                            elif user_type == 'employee':
                                role_display = 'Сотрудник'
                            else:
                                role_display = '-'
                            
                            users_dict[user_id] = {
                                'name': detail.get('user_name', 'Неизвестный'),
                                'user_id': user_id,
                                'client_code': detail.get('client_code', '-'),
                                'user_type': role_display,
                                'answers': {}
                            }
                        users_dict[user_id]['answers'][question_key] = detail.get('answer', '')
            
            # Заголовки таблицы
            worksheet.write(current_row, 0, 'ID', header_format)
            worksheet.write(current_row, 1, 'Имя', header_format)
            worksheet.write(current_row, 2, 'Роль', header_format)
            worksheet.write(current_row, 3, 'Код клиента', header_format)
            
            # Заголовки вопросов
            for q_idx, question in enumerate(poll['questions'], 1):
                col = 3 + q_idx
                question_text = f"Вопрос {q_idx}"
                worksheet.write(current_row, col, question_text, header_format)
            
            current_row += 1
            
            # Вторая строка с текстом вопросов
            worksheet.write(current_row, 0, '', subheader_format)
            worksheet.write(current_row, 1, '', subheader_format)
            worksheet.write(current_row, 2, '', subheader_format)
            worksheet.write(current_row, 3, '', subheader_format)
            
            for q_idx, question in enumerate(poll['questions'], 1):
                col = 3 + q_idx
                question_text = question['text']
                if len(question_text) > 50:
                    question_text = question_text[:47] + "..."
                worksheet.write(current_row, col, question_text, subheader_format)
            
            current_row += 1
            
            # Данные пользователей (каждая строка = один человек)
            for user_data in users_dict.values():
                worksheet.write(current_row, 0, user_data['user_id'], number_format)
                worksheet.write(current_row, 1, user_data['name'], text_format)
                worksheet.write(current_row, 2, user_data['user_type'], text_format)
                worksheet.write(current_row, 3, user_data['client_code'], text_format)
                
                # Ответы на каждый вопрос
                for q_idx, question in enumerate(poll['questions'], 1):
                    col = 3 + q_idx
                    question_key = f"q_{q_idx}"
                    answer = user_data['answers'].get(question_key, '-')
                    
                    # Проверяем, является ли ответ числом (рейтинг)
                    if question['type'] == 'rating':
                        try:
                            # Извлекаем число из ответа
                            if isinstance(answer, str) and answer.strip().isdigit():
                                numeric_answer = int(answer.strip())
                                worksheet.write(current_row, col, numeric_answer, number_format)
                            elif isinstance(answer, (int, float)):
                                worksheet.write(current_row, col, answer, number_format)
                            else:
                                worksheet.write(current_row, col, answer, text_format)
                        except:
                            worksheet.write(current_row, col, answer, text_format)
                    else:
                        worksheet.write(current_row, col, answer, text_format)
                
                current_row += 1
            
            # Добавляем строку статистики (средние значения для рейтинговых вопросов)
            current_row += 1
            worksheet.write(current_row, 0, '', header_format)
            worksheet.write(current_row, 1, 'Средние значения', header_format)
            worksheet.write(current_row, 2, '', header_format)
            worksheet.write(current_row, 3, '', header_format)
            
            for q_idx, question in enumerate(poll['questions'], 1):
                col = 3 + q_idx
                if question['type'] == 'rating':
                    # Формула для расчета среднего
                    start_row = current_row - len(users_dict)
                    end_row = current_row - 1
                    if start_row <= end_row:
                        col_letter = chr(65 + col)  # A=65, B=66, etc.
                        formula = f'=AVERAGE({col_letter}{start_row}:{col_letter}{end_row})'
                        avg_format = workbook.add_format({
                            'bold': True,
                            'bg_color': '#E8F5E9',
                            'border': 1,
                            'num_format': '0.0'  # Десятичная для среднего
                        })
                        worksheet.write_formula(current_row, col, formula, avg_format)
                    else:
                        worksheet.write(current_row, col, '-', header_format)
                else:
                    worksheet.write(current_row, col, '-', header_format)
            
            # Настройка ширины колонок
            worksheet.set_column(0, 0, 12)  # ID
            worksheet.set_column(1, 1, 25)  # Имя
            worksheet.set_column(2, 2, 15)  # Роль
            worksheet.set_column(3, 3, 15)  # Код клиента
            # Вопросы
            for q_idx in range(len(poll['questions'])):
                col = 4 + q_idx
                worksheet.set_column(col, col, 20)
        
        workbook.close()
        output.seek(0)
        return output.read()
