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
        
        question_format = workbook.add_format({
            'bold': True,
            'bg_color': '#F5F5F5',
            'border': 1,
            'text_wrap': True
        })
        
        text_wrap_format = workbook.add_format({
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
            summary_sheet.write(row, 1, poll['total_responses'])
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
            worksheet.merge_range(0, 0, 0, 5, poll['title'], header_format)
            if poll.get('description'):
                worksheet.merge_range(1, 0, 1, 5, poll['description'], subheader_format)
                current_row = 3
            else:
                current_row = 2
            
            # Для каждого вопроса
            for q_idx, question in enumerate(poll['questions'], 1):
                # Заголовок вопроса
                worksheet.merge_range(current_row, 0, current_row, 5, 
                                     f"Вопрос {q_idx}: {question['text']}", 
                                     question_format)
                current_row += 1
                
                if question['type'] in ['single', 'multiple']:
                    # Статистика по вариантам ответов
                    worksheet.write(current_row, 0, 'Вариант', subheader_format)
                    worksheet.write(current_row, 1, 'Количество', subheader_format)
                    worksheet.write(current_row, 2, 'Процент', subheader_format)
                    current_row += 1
                    
                    if question.get('options_stats'):
                        for option in question['options_stats']:
                            worksheet.write(current_row, 0, option['text'])
                            worksheet.write(current_row, 1, option['count'])
                            worksheet.write(current_row, 2, f"{option['percentage']:.1f}%")
                            current_row += 1
                    
                    # Детальные ответы
                    current_row += 1
                    worksheet.write(current_row, 0, 'Детальные ответы:', subheader_format)
                    current_row += 1
                    
                    if question.get('detailed_answers'):
                        worksheet.write(current_row, 0, 'Пользователь', subheader_format)
                        worksheet.write(current_row, 1, 'ID', subheader_format)
                        worksheet.write(current_row, 2, 'Код клиента', subheader_format)
                        worksheet.write(current_row, 3, 'Ответ', subheader_format)
                        current_row += 1
                        
                        for detail in question['detailed_answers']:
                            worksheet.write(current_row, 0, detail.get('user_name', 'Неизвестный'))
                            worksheet.write(current_row, 1, detail.get('user_id', ''))
                            worksheet.write(current_row, 2, detail.get('client_code', '-'))
                            worksheet.write(current_row, 3, detail.get('answer', ''))
                            current_row += 1
                
                elif question['type'] == 'rating':
                    worksheet.write(current_row, 0, 'Средняя оценка:', subheader_format)
                    worksheet.write(current_row, 1, f"{question.get('avg_rating', 0):.2f}")
                    current_row += 1
                    
                    # Детальные оценки
                    if question.get('detailed_answers'):
                        current_row += 1
                        worksheet.write(current_row, 0, 'Пользователь', subheader_format)
                        worksheet.write(current_row, 1, 'ID', subheader_format)
                        worksheet.write(current_row, 2, 'Оценка', subheader_format)
                        current_row += 1
                        
                        for detail in question['detailed_answers']:
                            worksheet.write(current_row, 0, detail.get('user_name', 'Неизвестный'))
                            worksheet.write(current_row, 1, detail.get('user_id', ''))
                            worksheet.write(current_row, 2, detail.get('answer', ''))
                            current_row += 1
                
                elif question['type'] == 'text':
                    worksheet.write(current_row, 0, 'Текстовые ответы:', subheader_format)
                    current_row += 1
                    
                    if question.get('text_answers_detailed'):
                        # Заголовки колонок
                        worksheet.write(current_row, 0, 'Пользователь', subheader_format)
                        worksheet.write(current_row, 1, 'ID', subheader_format)
                        worksheet.write(current_row, 2, 'Код клиента', subheader_format)
                        worksheet.write(current_row, 3, 'Тип', subheader_format)
                        worksheet.write(current_row, 4, 'Дата ответа', subheader_format)
                        worksheet.merge_range(current_row, 5, current_row, 7, 'Ответ', subheader_format)
                        current_row += 1
                        
                        for answer_detail in question['text_answers_detailed']:
                            worksheet.write(current_row, 0, answer_detail.get('user_name', 'Неизвестный'))
                            worksheet.write(current_row, 1, answer_detail.get('user_id', ''))
                            worksheet.write(current_row, 2, answer_detail.get('client_code', '-'))
                            worksheet.write(current_row, 3, answer_detail.get('user_type', '-'))
                            worksheet.write(current_row, 4, answer_detail.get('answered_at', '-'))
                            
                            # Объединяем ячейки для длинного текста ответа
                            worksheet.merge_range(current_row, 5, current_row, 7, 
                                                answer_detail.get('answer', ''), 
                                                text_wrap_format)
                            current_row += 1
                
                current_row += 2  # Отступ между вопросами
            
            # Настройка ширины колонок
            worksheet.set_column(0, 0, 25)  # Пользователь
            worksheet.set_column(1, 1, 12)  # ID
            worksheet.set_column(2, 2, 15)  # Код клиента
            worksheet.set_column(3, 3, 12)  # Тип
            worksheet.set_column(4, 4, 18)  # Дата
            worksheet.set_column(5, 7, 30)  # Ответ
        
        workbook.close()
        output.seek(0)
        return output.read()
