"""
Модуль экспорта метрик в Excel
"""
import io
from datetime import datetime, timedelta
from typing import Optional
import xlsxwriter


class MetricsExporter:
    """Экспортер метрик в Excel"""
    
    def __init__(self, db):
        self.db = db
    
    async def export_comprehensive_metrics(self, days: int = 30) -> bytes:
        """Экспортирует полные метрики в Excel"""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Форматы
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'bg_color': '#D9E1F2'
        })
        
        good_format = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        warning_format = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C6500'})
        bad_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        
        # 1. Сводный лист
        await self._create_summary_sheet(workbook, header_format, title_format, days)
        
        # 2. Клиентские метрики
        await self._create_client_metrics_sheet(workbook, header_format, title_format, days)
        
        # 3. Технические метрики
        await self._create_technical_metrics_sheet(workbook, header_format, title_format, days)
        
        # 4. Метрики качества
        await self._create_quality_metrics_sheet(workbook, header_format, title_format, good_format, warning_format, days)
        
        # 5. Детальные данные
        await self._create_detailed_data_sheet(workbook, header_format, days)
        
        workbook.close()
        output.seek(0)
        return output.read()
    
    async def _create_summary_sheet(self, workbook, header_format, title_format, days):
        """Создает сводный лист"""
        worksheet = workbook.add_worksheet('Сводка')
        worksheet.set_column('A:A', 30)
        worksheet.set_column('B:B', 20)
        
        row = 0
        
        # Заголовок
        worksheet.write(row, 0, f'СВОДКА МЕТРИК ЗА {days} ДНЕЙ', title_format)
        worksheet.write(row, 1, datetime.now().strftime('%d.%m.%Y %H:%M'))
        row += 2
        
        # Получаем данные
        metrics = await self.db.get_comprehensive_metrics(days)
        
        if not metrics:
            worksheet.write(row, 0, 'Нет данных')
            return
        
        # Клиентские метрики
        worksheet.write(row, 0, '👥 КЛИЕНТСКИЕ МЕТРИКИ', title_format)
        row += 1
        
        client = metrics.get('client_metrics', {})
        dau_list = client.get('dau', [])
        retention = client.get('retention', {})
        sessions = client.get('sessions', {})
        
        if dau_list and len(dau_list) > 0:
            today_dau = dau_list[0].get('dau', 0) if dau_list else 0
            week_data = dau_list[:7]
            avg_dau = sum(d.get('dau', 0) for d in week_data) / len(week_data) if week_data else 0
            
            worksheet.write(row, 0, 'DAU сегодня')
            worksheet.write(row, 1, today_dau)
            row += 1
            
            worksheet.write(row, 0, 'Средний DAU')
            worksheet.write(row, 1, f'{avg_dau:.1f}')
            row += 1
        
        if retention and retention.get('today_users', 0) > 0:
            worksheet.write(row, 0, 'Retention 1 день')
            worksheet.write(row, 1, f"{retention.get('retention_1d', 0):.1f}%")
            row += 1
            
            worksheet.write(row, 0, 'Retention 7 дней')
            worksheet.write(row, 1, f"{retention.get('retention_7d', 0):.1f}%")
            row += 1
            
            worksheet.write(row, 0, 'Retention 30 дней')
            worksheet.write(row, 1, f"{retention.get('retention_30d', 0):.1f}%")
            row += 1
        
        if sessions and sessions.get('total_sessions', 0) > 0:
            avg_duration = sessions.get('avg_duration_minutes') or 0
            worksheet.write(row, 0, 'Средняя длительность сессии')
            worksheet.write(row, 1, f"{avg_duration:.1f} мин")
            row += 2
        
        # Технические метрики
        worksheet.write(row, 0, '⚙️ ТЕХНИЧЕСКИЕ МЕТРИКИ', title_format)
        row += 1
        
        tech = metrics.get('technical_metrics', {})
        perf = tech.get('response_time', {})
        
        if perf and perf.get('overall'):
            overall = perf['overall']
            
            worksheet.write(row, 0, 'Всего запросов')
            worksheet.write(row, 1, overall.get('total_requests', 0))
            row += 1
            
            worksheet.write(row, 0, 'Успешных запросов')
            worksheet.write(row, 1, overall.get('successful_requests', 0))
            row += 1
            
            worksheet.write(row, 0, 'Среднее время ответа')
            worksheet.write(row, 1, f"{overall.get('avg_response_time', 0):.2f} сек")
            row += 1
            
            worksheet.write(row, 0, 'Макс. время ответа')
            worksheet.write(row, 1, f"{overall.get('max_response_time', 0):.2f} сек")
            row += 2
        
        # Метрики качества
        worksheet.write(row, 0, '🎯 МЕТРИКИ КАЧЕСТВА', title_format)
        row += 1
        
        quality = metrics.get('quality_metrics', {})
        if quality:
            worksheet.write(row, 0, 'Всего запросов')
            worksheet.write(row, 1, quality.get('total', 0))
            row += 1
            
            worksheet.write(row, 0, 'Корректных ответов')
            worksheet.write(row, 1, f"{quality.get('correct_percentage', 0):.1f}%")
            row += 1
            
            worksheet.write(row, 0, 'Ошибок')
            worksheet.write(row, 1, f"{quality.get('incorrect_percentage', 0):.1f}%")
            row += 1
            
            worksheet.write(row, 0, 'Без ответа')
            worksheet.write(row, 1, f"{quality.get('no_answer_percentage', 0):.1f}%")
    
    async def _create_client_metrics_sheet(self, workbook, header_format, title_format, days):
        """Создает лист с клиентскими метриками"""
        worksheet = workbook.add_worksheet('Клиентские метрики')
        
        # DAU по дням
        dau_data = await self.db.get_dau_metrics(days)
        
        if dau_data:
            worksheet.write(0, 0, 'DAU ПО ДНЯМ', title_format)
            row = 1
            
            headers = ['Дата', 'DAU', 'Всего запросов', 'Запросов/пользователь']
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, header_format)
            
            row += 1
            for data in dau_data:
                worksheet.write(row, 0, str(data.get('activity_date', '')))
                worksheet.write(row, 1, data.get('dau', 0))
                worksheet.write(row, 2, data.get('total_requests', 0))
                avg_req = data.get('avg_requests_per_user') or 0
                worksheet.write(row, 3, f"{avg_req:.2f}")
                row += 1
            
            # Автоширина колонок
            worksheet.set_column('A:A', 12)
            worksheet.set_column('B:D', 15)
    
    async def _create_technical_metrics_sheet(self, workbook, header_format, title_format, days):
        """Создает лист с техническими метриками"""
        worksheet = workbook.add_worksheet('Технические метрики')
        
        # Метрики производительности
        perf_data = await self.db.get_metrics_summary(days)
        
        row = 0
        worksheet.write(row, 0, 'МЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ', title_format)
        row += 2
        
        if perf_data and perf_data.get('by_type'):
            headers = ['Тип запроса', 'Количество', 'Среднее время (сек)', 'Успешных', 'Без ответа']
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, header_format)
            
            row += 1
            for type_data in perf_data['by_type']:
                worksheet.write(row, 0, type_data.get('request_type', 'unknown'))
                worksheet.write(row, 1, type_data.get('count', 0))
                avg_time = type_data.get('avg_time') or 0
                worksheet.write(row, 2, f"{avg_time:.2f}")
                worksheet.write(row, 3, type_data.get('successful', 0))
                worksheet.write(row, 4, type_data.get('no_answer', 0))
                row += 1
        
        # Системные метрики
        row += 2
        worksheet.write(row, 0, 'СИСТЕМНЫЕ РЕСУРСЫ', title_format)
        row += 1
        
        sys_metrics = await self.db._get_latest_system_metrics()
        
        if sys_metrics:
            headers = ['Дата', 'CPU %', 'Память %', 'Диск %', 'Активных сессий', 'Ошибок']
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, header_format)
            
            row += 1
            for metric in sys_metrics:
                worksheet.write(row, 0, str(metric.get('metric_date', '')))
                worksheet.write(row, 1, f"{metric.get('cpu_usage') or 0:.1f}")
                worksheet.write(row, 2, f"{metric.get('memory_usage') or 0:.1f}")
                worksheet.write(row, 3, f"{metric.get('disk_usage') or 0:.1f}")
                worksheet.write(row, 4, metric.get('active_sessions') or 0)
                worksheet.write(row, 5, metric.get('error_count') or 0)
                row += 1
        
        worksheet.set_column('A:A', 12)
        worksheet.set_column('B:F', 15)
    
    async def _create_quality_metrics_sheet(self, workbook, header_format, title_format, good_format, warning_format, days):
        """Создает лист с метриками качества"""
        worksheet = workbook.add_worksheet('Метрики качества')
        
        quality = await self.db.get_quality_metrics_summary(days)
        
        row = 0
        worksheet.write(row, 0, f'МЕТРИКИ КАЧЕСТВА ЗА {days} ДНЕЙ', title_format)
        row += 2
        
        if quality:
            # Общая таблица
            headers = ['Метрика', 'Значение', 'Процент']
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, header_format)
            
            row += 1
            
            total = quality.get('total', 0)
            
            metrics_data = [
                ('Всего запросов', total, '100%'),
                ('Корректных ответов', quality.get('correct', 0), f"{quality.get('correct_percentage', 0):.1f}%"),
                ('Ошибок', quality.get('incorrect', 0), f"{quality.get('incorrect_percentage', 0):.1f}%"),
                ('Без ответа', quality.get('no_answer', 0), f"{quality.get('no_answer_percentage', 0):.1f}%"),
            ]
            
            for metric_name, value, percent in metrics_data:
                worksheet.write(row, 0, metric_name)
                worksheet.write(row, 1, value)
                
                # Цветовое выделение
                if 'Корректных' in metric_name:
                    pct_value = quality.get('correct_percentage', 0)
                    if pct_value >= 70:
                        worksheet.write(row, 2, percent, good_format)
                    elif pct_value >= 50:
                        worksheet.write(row, 2, percent, warning_format)
                    else:
                        worksheet.write(row, 2, percent)
                else:
                    worksheet.write(row, 2, percent)
                
                row += 1
            
            # Распределение по типам
            row += 2
            worksheet.write(row, 0, 'РАСПРЕДЕЛЕНИЕ ПО ТИПАМ ЗАПРОСОВ', title_format)
            row += 1
            
            headers = ['Тип запроса', 'Количество', 'Доля']
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, header_format)
            
            row += 1
            
            types_data = [
                ('Поиск по коду', quality.get('code_searches', 0)),
                ('Поиск по названию', quality.get('name_searches', 0)),
                ('Общие вопросы', quality.get('general_questions', 0)),
            ]
            
            for type_name, count in types_data:
                worksheet.write(row, 0, type_name)
                worksheet.write(row, 1, count)
                worksheet.write(row, 2, f"{(count / total * 100):.1f}%" if total > 0 else "0%")
                row += 1
        
        worksheet.set_column('A:A', 30)
        worksheet.set_column('B:C', 15)
    
    async def _create_detailed_data_sheet(self, workbook, header_format, days):
        """Создает лист с детальными данными"""
        worksheet = workbook.add_worksheet('Детальные данные')
        
        start_date = datetime.now() - timedelta(days=days)
        detailed = await self.db.get_detailed_metrics(start_date=start_date)
        
        if not detailed or not detailed.get('requests'):
            worksheet.write(0, 0, 'Нет данных')
            return
        
        # Заголовки
        headers = [
            'Дата/Время', 'Пользователь', 'Тип запроса', 'Запрос',
            'Время ответа (сек)', 'Успех', 'Есть ответ', 'Ошибка'
        ]
        
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        
        # Данные
        row = 1
        for req in detailed['requests'][:1000]:  # Максимум 1000 записей
            worksheet.write(row, 0, str(req.get('timestamp', '')))
            worksheet.write(row, 1, req.get('user_name', 'Неизвестный'))
            worksheet.write(row, 2, req.get('request_type', ''))
            
            query = req.get('query_text', '')
            worksheet.write(row, 3, query[:100] if query else '')
            
            response_time = req.get('response_time') or 0
            worksheet.write(row, 4, f"{response_time:.2f}")
            worksheet.write(row, 5, 'Да' if req.get('success') else 'Нет')
            worksheet.write(row, 6, 'Да' if req.get('has_answer') else 'Нет')
            worksheet.write(row, 7, req.get('error_message', '') or '')
            
            row += 1
        
        # Автоширина
        worksheet.set_column('A:A', 20)
        worksheet.set_column('B:B', 25)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 50)
        worksheet.set_column('E:H', 15)
    
    async def export_dau_report(self, days: int = 30) -> bytes:
        """Экспортирует отчет по DAU"""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        worksheet = workbook.add_worksheet('DAU Report')
        
        # Форматы
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white'
        })
        
        # Заголовки
        headers = ['Дата', 'DAU', 'Всего запросов', 'Запросов на пользователя']
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        
        # Данные
        dau_data = await self.db.get_dau_metrics(days)
        
        row = 1
        for data in dau_data:
            worksheet.write(row, 0, str(data.get('activity_date', '')))
            worksheet.write(row, 1, data.get('dau', 0))
            worksheet.write(row, 2, data.get('total_requests', 0))
            avg_req = data.get('avg_requests_per_user') or 0
            worksheet.write(row, 3, f"{avg_req:.2f}")
            row += 1
        
        # Создаем график
        chart = workbook.add_chart({'type': 'line'})
        
        chart.add_series({
            'name': 'DAU',
            'categories': f'=DAU Report!$A$2:$A${row}',
            'values': f'=DAU Report!$B$2:$B${row}',
        })
        
        chart.set_title({'name': f'Daily Active Users ({days} дней)'})
        chart.set_x_axis({'name': 'Дата'})
        chart.set_y_axis({'name': 'Пользователей'})
        
        worksheet.insert_chart('F2', chart)
        
        worksheet.set_column('A:D', 20)
        
        workbook.close()
        output.seek(0)
        return output.read()