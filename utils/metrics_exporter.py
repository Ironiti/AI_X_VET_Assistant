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
    
    def _create_formats(self, workbook):
        """Создает все необходимые форматы для документа"""
        formats = {}
        
        # Корпоративная палитра цветов
        PRIMARY_BLUE = '#1E3A8A'
        LIGHT_BLUE = '#DBEAFE'
        ACCENT_BLUE = '#3B82F6'
        SUCCESS_GREEN = '#10B981'
        WARNING_YELLOW = '#F59E0B'
        ERROR_RED = '#EF4444'
        GRAY_LIGHT = '#F3F4F6'
        GRAY_DARK = '#6B7280'
        
        # Главный заголовок документа
        formats['main_title'] = workbook.add_format({
            'bold': True,
            'font_size': 20,
            'font_color': 'white',
            'bg_color': PRIMARY_BLUE,
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': PRIMARY_BLUE
        })
        
        # Подзаголовок документа
        formats['subtitle'] = workbook.add_format({
            'font_size': 12,
            'font_color': GRAY_DARK,
            'bg_color': LIGHT_BLUE,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'border_color': ACCENT_BLUE
        })
        
        # Заголовок секции
        formats['section_header'] = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'font_color': 'white',
            'bg_color': ACCENT_BLUE,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'left': 2,
            'border_color': PRIMARY_BLUE
        })
        
        # Заголовок подсекции
        formats['subsection_header'] = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'font_color': PRIMARY_BLUE,
            'bg_color': LIGHT_BLUE,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Заголовок таблицы
        formats['table_header'] = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'font_color': 'white',
            'bg_color': PRIMARY_BLUE,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'text_wrap': True
        })
        
        # Метка (label) для метрик
        formats['metric_label'] = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'font_color': '#1F2937',
            'bg_color': GRAY_LIGHT,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1,
            'indent': 1
        })
        
        # Значение метрики
        formats['metric_value'] = workbook.add_format({
            'font_size': 11,
            'font_color': '#1F2937',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0'
        })
        
        # Значение метрики (процент)
        formats['metric_percent'] = workbook.add_format({
            'font_size': 11,
            'font_color': '#1F2937',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '0.0"%"'
        })
        
        # Значение метрики (десятичное)
        formats['metric_decimal'] = workbook.add_format({
            'font_size': 11,
            'font_color': '#1F2937',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '0.00'
        })
        
        # Ячейка данных таблицы
        formats['cell_data'] = workbook.add_format({
            'font_size': 10,
            'align': 'left',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Ячейка данных таблицы (число)
        formats['cell_number'] = workbook.add_format({
            'font_size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0'
        })
        
        # Ячейка данных таблицы (десятичное)
        formats['cell_decimal'] = workbook.add_format({
            'font_size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '0.00'
        })
        
        # Положительный результат
        formats['good'] = workbook.add_format({
            'bold': True,
            'font_color': SUCCESS_GREEN,
            'bg_color': '#D1FAE5',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '0.0"%"'
        })
        
        # Предупреждение
        formats['warning'] = workbook.add_format({
            'bold': True,
            'font_color': WARNING_YELLOW,
            'bg_color': '#FEF3C7',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '0.0"%"'
        })
        
        # Негативный результат
        formats['bad'] = workbook.add_format({
            'bold': True,
            'font_color': ERROR_RED,
            'bg_color': '#FEE2E2',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '0.0"%"'
        })
        
        # KPI - высокий показатель
        formats['kpi_high'] = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'font_color': SUCCESS_GREEN,
            'bg_color': '#ECFDF5',
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': SUCCESS_GREEN,
            'num_format': '0.00'
        })
        
        # KPI - средний показатель
        formats['kpi_medium'] = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'font_color': WARNING_YELLOW,
            'bg_color': '#FFFBEB',
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': WARNING_YELLOW,
            'num_format': '0.00'
        })
        
        # KPI - низкий показатель
        formats['kpi_low'] = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'font_color': ERROR_RED,
            'bg_color': '#FEF2F2',
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': ERROR_RED,
            'num_format': '0.00'
        })
        
        # Дата/время
        formats['datetime'] = workbook.add_format({
            'font_size': 10,
            'font_color': GRAY_DARK,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        
        return formats
    
    async def export_comprehensive_metrics(self, days: int = 30) -> bytes:
        """Экспортирует полные метрики в Excel"""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Создаем все форматы
        formats = self._create_formats(workbook)
        
        # 1. Сводный лист (Executive Dashboard)
        await self._create_summary_sheet(workbook, formats, days)
        
        # 2. Клиентские метрики
        await self._create_client_metrics_sheet(workbook, formats, days)
        
        # 3. Технические метрики
        await self._create_technical_metrics_sheet(workbook, formats, days)
        
        # 4. Метрики качества
        await self._create_quality_metrics_sheet(workbook, formats, days)
        
        # 5. Детальные данные
        await self._create_detailed_data_sheet(workbook, formats, days)
        
        workbook.close()
        output.seek(0)
        return output.read()
    
    async def _create_summary_sheet(self, workbook, formats, days):
        """Создает сводный лист - Executive Dashboard"""
        worksheet = workbook.add_worksheet('📊 Сводная панель')
        
        # Настройка размеров колонок
        worksheet.set_column('A:A', 40)
        worksheet.set_column('B:B', 20)
        worksheet.set_column('C:C', 20)
        
        row = 0
        
        # Главный заголовок
        worksheet.merge_range(row, 0, row, 2, 
                            f'ОТЧЕТ ПО МЕТРИКАМ СИСТЕМЫ', 
                            formats['main_title'])
        worksheet.set_row(row, 30)
        row += 1
        
        # Подзаголовок с периодом и датой
        period_text = f'Период анализа: {days} дней | Сформирован: {datetime.now().strftime("%d.%m.%Y %H:%M")}'
        worksheet.merge_range(row, 0, row, 2, period_text, formats['subtitle'])
        worksheet.set_row(row, 20)
        row += 2
        
        # Получаем данные
        metrics = await self.db.get_comprehensive_metrics(days)
        avg_rating = await self.db.get_average_user_rating(days)
        
        if not metrics:
            worksheet.write(row, 0, 'Нет данных за указанный период', formats['metric_label'])
            return
        
        # ===== КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ (KPI) =====
        worksheet.merge_range(row, 0, row, 2, 
                            '🎯 КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ ЭФФЕКТИВНОСТИ',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        client = metrics.get('client_metrics', {})
        dau_list = client.get('dau', [])
        
        # Средний DAU
        if dau_list and len(dau_list) > 0:
            avg_dau = sum(d.get('dau', 0) for d in dau_list) / len(dau_list)
            worksheet.write(row, 0, '👥 Средний DAU (активных пользователей в день)', formats['metric_label'])
            kpi_format = formats['kpi_high'] if avg_dau >= 50 else formats['kpi_medium'] if avg_dau >= 20 else formats['kpi_low']
            worksheet.write(row, 1, avg_dau, kpi_format)
            worksheet.write(row, 2, 'пользователей', formats['metric_value'])
            row += 1
        
        # Коэффициент точности
        tech = metrics.get('technical_metrics', {})
        perf = tech.get('response_time', {})
        overall = perf.get('overall', {}) if perf else {}
        total_requests = overall.get('total_requests', 0)
        successful_requests = overall.get('successful_requests', 0)
        accuracy = (successful_requests / total_requests * 100) if total_requests > 0 else 0
        
        worksheet.write(row, 0, '✅ Коэффициент точности ответов', formats['metric_label'])
        kpi_format = formats['kpi_high'] if accuracy >= 80 else formats['kpi_medium'] if accuracy >= 60 else formats['kpi_low']
        worksheet.write(row, 1, accuracy / 100, kpi_format)
        worksheet.write(row, 2, f'{successful_requests}/{total_requests}', formats['metric_value'])
        row += 1
        
        # Средний рейтинг
        worksheet.write(row, 0, '⭐ Средняя оценка пользователей', formats['metric_label'])
        kpi_format = formats['kpi_high'] if avg_rating >= 4.0 else formats['kpi_medium'] if avg_rating >= 3.0 else formats['kpi_low']
        worksheet.write(row, 1, avg_rating, kpi_format)
        worksheet.write(row, 2, 'из 5.00', formats['metric_value'])
        row += 2
        
        # ===== КЛИЕНТСКАЯ АКТИВНОСТЬ =====
        worksheet.merge_range(row, 0, row, 2,
                            '👥 КЛИЕНТСКАЯ АКТИВНОСТЬ',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        # Retention
        retention = client.get('retention', {})
        if retention and retention.get('today_users', 0) > 0:
            worksheet.merge_range(row, 0, row, 2, 'Показатели удержания (Retention)', formats['subsection_header'])
            row += 1
            
            ret_1d = retention.get('retention_1d', 0)
            worksheet.write(row, 0, '  • Retention 1 день', formats['metric_label'])
            worksheet.write(row, 1, ret_1d / 100, formats['metric_percent'])
            worksheet.write(row, 2, self._get_retention_status(ret_1d), formats['cell_data'])
            row += 1
            
            ret_7d = retention.get('retention_7d', 0)
            worksheet.write(row, 0, '  • Retention 7 дней', formats['metric_label'])
            worksheet.write(row, 1, ret_7d / 100, formats['metric_percent'])
            worksheet.write(row, 2, self._get_retention_status(ret_7d), formats['cell_data'])
            row += 1
            
            ret_30d = retention.get('retention_30d', 0)
            worksheet.write(row, 0, '  • Retention 30 дней', formats['metric_label'])
            worksheet.write(row, 1, ret_30d / 100, formats['metric_percent'])
            worksheet.write(row, 2, self._get_retention_status(ret_30d), formats['cell_data'])
            row += 1
        
        row += 1
        
        # === ВРЕМЯ АКТИВНОСТИ ПОЛЬЗОВАТЕЛЕЙ ===
        worksheet.merge_range(row, 0, row, 2,
                            '⏱️ ВРЕМЯ АКТИВНОСТИ ПОЛЬЗОВАТЕЛЕЙ',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        # Средняя длительность сессии
        sessions = client.get('sessions', {})
        if sessions and sessions.get('total_sessions', 0) > 0:
            total_sessions = sessions.get('total_sessions', 0)
            avg_duration = sessions.get('avg_duration_minutes', 0)
            
            # Основная метрика - средняя длительность
            worksheet.write(row, 0, '📊 Средняя длительность сессии', formats['metric_label'])
            kpi_format_duration = workbook.add_format({
                'bold': True,
                'font_size': 14,
                'font_color': '#10B981' if avg_duration >= 5 else '#F59E0B' if avg_duration >= 2 else '#EF4444',
                'bg_color': '#ECFDF5' if avg_duration >= 5 else '#FFFBEB' if avg_duration >= 2 else '#FEF2F2',
                'align': 'center',
                'valign': 'vcenter',
                'border': 2,
                'border_color': '#10B981' if avg_duration >= 5 else '#F59E0B' if avg_duration >= 2 else '#EF4444',
                'num_format': '0.00'
            })
            worksheet.write(row, 1, avg_duration, kpi_format_duration)
            worksheet.write(row, 2, 'минут', formats['metric_value'])
            row += 1
            
            # Количество сессий
            worksheet.write(row, 0, '  📈 Всего сессий за период', formats['metric_label'])
            worksheet.write(row, 1, total_sessions, formats['metric_value'])
            row += 1
            
            # Общее время активности
            total_activity_time = avg_duration * total_sessions
            worksheet.write(row, 0, '  ⏳ Суммарное время активности', formats['metric_label'])
            worksheet.write(row, 1, total_activity_time, formats['metric_decimal'])
            worksheet.write(row, 2, 'минут', formats['metric_value'])
            row += 1
            
            # Среднее время в часах для удобства
            avg_hours = avg_duration / 60
            worksheet.write(row, 0, '  🕐 Средняя длительность (часы)', formats['metric_label'])
            worksheet.write(row, 1, avg_hours, formats['metric_decimal'])
            worksheet.write(row, 2, 'часов', formats['metric_value'])
            row += 1
        else:
            worksheet.write(row, 0, '⏱️ Средняя длительность сессии', formats['metric_label'])
            worksheet.merge_range(row, 1, row, 2, 'Данные недоступны', formats['metric_value'])
            row += 1
        
        row += 1
        
        # Количество обращений
        if dau_list:
            worksheet.merge_range(row, 0, row, 2, 'Объем обращений', formats['subsection_header'])
            row += 1
            
            today_req = dau_list[0].get('total_requests', 0) if dau_list else 0
            week_req = sum(d.get('total_requests', 0) for d in dau_list[:7])
            month_req = sum(d.get('total_requests', 0) for d in dau_list)
            
            worksheet.write(row, 0, '  📅 За последний день', formats['metric_label'])
            worksheet.write(row, 1, today_req, formats['metric_value'])
            row += 1
            
            worksheet.write(row, 0, '  📅 За последние 7 дней', formats['metric_label'])
            worksheet.write(row, 1, week_req, formats['metric_value'])
            row += 1
            
            worksheet.write(row, 0, f'  📅 За весь период ({days} дней)', formats['metric_label'])
            worksheet.write(row, 1, month_req, formats['metric_value'])
            row += 2
        
        # ===== ПРОИЗВОДИТЕЛЬНОСТЬ СИСТЕМЫ =====
        worksheet.merge_range(row, 0, row, 2,
                            '⚡ ПРОИЗВОДИТЕЛЬНОСТЬ СИСТЕМЫ',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        if overall:
            avg_response = overall.get('avg_response_time', 0)
            worksheet.write(row, 0, '⏱️ Среднее время ответа', formats['metric_label'])
            worksheet.write(row, 1, avg_response, formats['metric_decimal'])
            worksheet.write(row, 2, 'секунд', formats['metric_value'])
            row += 1
            
            max_response = overall.get('max_response_time', 0)
            worksheet.write(row, 0, '⏱️ Максимальное время ответа', formats['metric_label'])
            worksheet.write(row, 1, max_response, formats['metric_decimal'])
            worksheet.write(row, 2, 'секунд', formats['metric_value'])
            row += 2
        
        # ===== КАЧЕСТВО ОБСЛУЖИВАНИЯ =====
        worksheet.merge_range(row, 0, row, 2,
                            '🎯 КАЧЕСТВО ОБСЛУЖИВАНИЯ',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        quality = metrics.get('quality_metrics', {})
        if quality:
            total = quality.get('total', 0)
            correct = quality.get('correct', 0)
            incorrect = quality.get('incorrect', 0)
            no_answer = quality.get('no_answer', 0)
            
            worksheet.write(row, 0, '📊 Всего запросов обработано', formats['metric_label'])
            worksheet.write(row, 1, total, formats['metric_value'])
            row += 1
            
            correct_pct = quality.get('correct_percentage', 0)
            worksheet.write(row, 0, '✅ Корректных ответов', formats['metric_label'])
            pct_format = formats['good'] if correct_pct >= 70 else formats['warning'] if correct_pct >= 50 else formats['bad']
            worksheet.write(row, 1, correct_pct / 100, pct_format)
            worksheet.write(row, 2, f'{correct} запросов', formats['metric_value'])
            row += 1
            
            incorrect_pct = quality.get('incorrect_percentage', 0)
            worksheet.write(row, 0, '❌ Некорректных ответов', formats['metric_label'])
            worksheet.write(row, 1, incorrect_pct / 100, formats['metric_percent'])
            worksheet.write(row, 2, f'{incorrect} запросов', formats['metric_value'])
            row += 1
            
            no_answer_pct = quality.get('no_answer_percentage', 0)
            worksheet.write(row, 0, '⚠️ Без ответа', formats['metric_label'])
            worksheet.write(row, 1, no_answer_pct / 100, formats['metric_percent'])
            worksheet.write(row, 2, f'{no_answer} запросов', formats['metric_value'])
            row += 1
    
    def _get_retention_status(self, retention_pct):
        """Возвращает статус retention"""
        if retention_pct >= 40:
            return '🟢 Отлично'
        elif retention_pct >= 20:
            return '🟡 Хорошо'
        else:
            return '🔴 Требует внимания'
    
    async def _create_client_metrics_sheet(self, workbook, formats, days):
        """Создает лист с клиентскими метриками"""
        worksheet = workbook.add_worksheet('👥 Клиенты')
        
        # Заголовок
        worksheet.merge_range(0, 0, 0, 3, 
                            f'КЛИЕНТСКИЕ МЕТРИКИ ЗА {days} ДНЕЙ',
                            formats['main_title'])
        worksheet.set_row(0, 30)
        
        # DAU по дням
        dau_data = await self.db.get_dau_metrics(days)
        
        if dau_data:
            row = 2
            worksheet.merge_range(row, 0, row, 3,
                                'Ежедневная активность пользователей (DAU)',
                                formats['section_header'])
            row += 1
            
            headers = ['Дата', 'DAU', 'Всего запросов', 'Запросов/пользователь']
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, formats['table_header'])
            
            worksheet.set_column('A:A', 15)
            worksheet.set_column('B:B', 12)
            worksheet.set_column('C:C', 18)
            worksheet.set_column('D:D', 22)
            
            row += 1
            for data in dau_data:
                worksheet.write(row, 0, str(data.get('activity_date', '')), formats['cell_data'])
                worksheet.write(row, 1, data.get('dau', 0), formats['cell_number'])
                worksheet.write(row, 2, data.get('total_requests', 0), formats['cell_number'])
                avg_req = data.get('avg_requests_per_user') or 0
                worksheet.write(row, 3, avg_req, formats['cell_decimal'])
                row += 1
            
            # Добавляем график DAU
            if len(dau_data) > 1:
                chart = workbook.add_chart({'type': 'line'})
                chart.add_series({
                    'name': 'DAU',
                    'categories': f'=\'👥 Клиенты\'!$A$5:$A${row}',
                    'values': f'=\'👥 Клиенты\'!$B$5:$B${row}',
                    'line': {'color': '#3B82F6', 'width': 2.5}
                })
                chart.set_title({
                    'name': f'Динамика активных пользователей ({days} дней)',
                    'name_font': {'size': 14, 'bold': True}
                })
                chart.set_x_axis({'name': 'Дата', 'name_font': {'size': 11}})
                chart.set_y_axis({'name': 'Пользователей', 'name_font': {'size': 11}})
                chart.set_size({'width': 720, 'height': 400})
                chart.set_legend({'position': 'bottom'})
                worksheet.insert_chart(row + 2, 0, chart)
    
    async def _create_technical_metrics_sheet(self, workbook, formats, days):
        """Создает лист с техническими метриками"""
        worksheet = workbook.add_worksheet('⚙️ Технические')
        
        # Заголовок
        worksheet.merge_range(0, 0, 0, 4,
                            f'ТЕХНИЧЕСКИЕ МЕТРИКИ ЗА {days} ДНЕЙ',
                            formats['main_title'])
        worksheet.set_row(0, 30)
        
        # Метрики производительности
        perf_data = await self.db.get_metrics_summary(days)
        
        row = 2
        worksheet.merge_range(row, 0, row, 4,
                            'Производительность по типам запросов',
                            formats['section_header'])
        row += 1
        
        if perf_data and perf_data.get('by_type'):
            headers = ['Тип запроса', 'Количество', 'Среднее время (сек)', 'Успешных', 'Без ответа']
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, formats['table_header'])
            
            worksheet.set_column('A:A', 25)
            worksheet.set_column('B:E', 18)
            
            row += 1
            for type_data in perf_data['by_type']:
                worksheet.write(row, 0, type_data.get('request_type', 'unknown'), formats['cell_data'])
                worksheet.write(row, 1, type_data.get('count', 0), formats['cell_number'])
                avg_time = type_data.get('avg_time') or 0
                worksheet.write(row, 2, avg_time, formats['cell_decimal'])
                worksheet.write(row, 3, type_data.get('successful', 0), formats['cell_number'])
                worksheet.write(row, 4, type_data.get('no_answer', 0), formats['cell_number'])
                row += 1
        
        # Системные метрики
        row += 2
        worksheet.merge_range(row, 0, row, 5,
                            'Мониторинг системных ресурсов',
                            formats['section_header'])
        row += 1
        
        sys_metrics = await self.db._get_latest_system_metrics()
        
        if sys_metrics:
            headers = ['Дата', 'CPU %', 'Память %', 'Диск %', 'Активных сессий', 'Ошибок']
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, formats['table_header'])
            
            worksheet.set_column('A:A', 15)
            worksheet.set_column('B:D', 12)
            worksheet.set_column('E:F', 16)
            
            row += 1
            for metric in sys_metrics:
                worksheet.write(row, 0, str(metric.get('metric_date', '')), formats['cell_data'])
                worksheet.write(row, 1, metric.get('cpu_usage') or 0, formats['cell_decimal'])
                worksheet.write(row, 2, metric.get('memory_usage') or 0, formats['cell_decimal'])
                worksheet.write(row, 3, metric.get('disk_usage') or 0, formats['cell_decimal'])
                worksheet.write(row, 4, metric.get('active_sessions') or 0, formats['cell_number'])
                worksheet.write(row, 5, metric.get('error_count') or 0, formats['cell_number'])
                row += 1
    
    async def _create_quality_metrics_sheet(self, workbook, formats, days):
        """Создает лист с метриками качества"""
        worksheet = workbook.add_worksheet('🎯 Качество')
        
        # Заголовок
        worksheet.merge_range(0, 0, 0, 2,
                            f'МЕТРИКИ КАЧЕСТВА ЗА {days} ДНЕЙ',
                            formats['main_title'])
        worksheet.set_row(0, 30)
        
        quality = await self.db.get_quality_metrics_summary(days)
        
        row = 2
        worksheet.merge_range(row, 0, row, 2,
                            'Общая статистика качества ответов',
                            formats['section_header'])
        row += 1
        
        if quality:
            # Общая таблица
            headers = ['Метрика', 'Значение', 'Процент']
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, formats['table_header'])
            
            worksheet.set_column('A:A', 35)
            worksheet.set_column('B:C', 18)
            
            row += 1
            
            total = quality.get('total', 0)
            
            metrics_data = [
                ('📊 Всего запросов обработано', total, 100.0),
                ('✅ Корректных ответов', quality.get('correct', 0), quality.get('correct_percentage', 0)),
                ('❌ Некорректных ответов', quality.get('incorrect', 0), quality.get('incorrect_percentage', 0)),
                ('⚠️ Без ответа', quality.get('no_answer', 0), quality.get('no_answer_percentage', 0)),
            ]
            
            for metric_name, value, percent in metrics_data:
                worksheet.write(row, 0, metric_name, formats['metric_label'])
                worksheet.write(row, 1, value, formats['metric_value'])
                
                # Цветовое выделение процентов
                if 'Корректных' in metric_name:
                    pct_format = formats['good'] if percent >= 70 else formats['warning'] if percent >= 50 else formats['bad']
                else:
                    pct_format = formats['metric_percent']
                
                worksheet.write(row, 2, percent / 100, pct_format)
                row += 1
            
            # Распределение по типам
            row += 2
            worksheet.merge_range(row, 0, row, 2,
                                'Распределение запросов по типам',
                                formats['section_header'])
            row += 1
            
            headers = ['Тип запроса', 'Количество', 'Доля от общего объема']
            for col, header in enumerate(headers):
                worksheet.write(row, col, header, formats['table_header'])
            
            row += 1
            
            types_data = [
                ('🔍 Поиск по коду', quality.get('code_searches', 0)),
                ('📝 Поиск по названию', quality.get('name_searches', 0)),
                ('💬 Общие вопросы', quality.get('general_questions', 0)),
            ]
            
            for type_name, count in types_data:
                worksheet.write(row, 0, type_name, formats['metric_label'])
                worksheet.write(row, 1, count, formats['metric_value'])
                pct = (count / total * 100) if total > 0 else 0
                worksheet.write(row, 2, pct / 100, formats['metric_percent'])
                row += 1
            
            # Добавляем круговую диаграмму
            if total > 0:
                chart = workbook.add_chart({'type': 'pie'})
                chart.add_series({
                    'name': 'Распределение по типам',
                    'categories': f'=\'🎯 Качество\'!$A${row-2}:$A${row}',
                    'values': f'=\'🎯 Качество\'!$B${row-2}:$B${row}',
                    'data_labels': {'percentage': True, 'leader_lines': True}
                })
                chart.set_title({
                    'name': 'Распределение запросов по типам',
                    'name_font': {'size': 14, 'bold': True}
                })
                chart.set_size({'width': 500, 'height': 400})
                worksheet.insert_chart(row + 2, 0, chart)
    
    async def _create_detailed_data_sheet(self, workbook, formats, days):
        """Создает лист с детальными данными - ТОЛЬКО валидные запросы (общие вопросы, поиск по коду/названию)"""
        worksheet = workbook.add_worksheet('📋 Детали')
        
        # Заголовок
        worksheet.merge_range(0, 0, 0, 5,
                            f'ДЕТАЛЬНЫЕ ДАННЫЕ ЗА {days} ДНЕЙ',
                            formats['main_title'])
        worksheet.set_row(0, 30)
        
        start_date = datetime.now() - timedelta(days=days)
        
        # Получаем ТОЛЬКО валидные запросы (общие вопросы, поиск по коду, поиск по названию)
        import aiosqlite
        async with aiosqlite.connect(self.db.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT
                    rm.timestamp,
                    u.name as user_name,
                    u.user_type,
                    u.client_code,
                    rm.request_type,
                    rm.query_text,
                    rm.success,
                    rm.has_answer,
                    rm.response_time
                FROM request_metrics rm
                JOIN users u ON rm.user_id = u.telegram_id
                WHERE rm.timestamp >= ?
                  AND u.role != 'admin'
                  AND rm.request_type IN ('general', 'code_search', 'name_search')
                ORDER BY rm.timestamp DESC
                LIMIT 1000
            ''', (start_date,))
            
            interactions = await cursor.fetchall()
        
        if not interactions:
            worksheet.write(2, 0, 'Нет данных за указанный период', formats['metric_label'])
            return
        
        row = 2
        worksheet.merge_range(row, 0, row, 5,
                            'История валидных запросов (общие вопросы, поиск по коду, поиск по названию)',
                            formats['section_header'])
        row += 1
        
        # Заголовки
        headers = [
            'Дата/Время', 'Пользователь', 'Тип взаимодействия',
            'Текст/Сообщение', 'Время обработки (сек)', 'Статус'
        ]
        
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        
        # Настройка ширины колонок
        worksheet.set_column('A:A', 18)
        worksheet.set_column('B:B', 25)
        worksheet.set_column('C:C', 20)
        worksheet.set_column('D:D', 50)
        worksheet.set_column('E:E', 20)
        worksheet.set_column('F:F', 12)
        
        row += 1
        
        # Данные - только валидные запросы
        for interaction in interactions:
            worksheet.write(row, 0, str(interaction['timestamp']), formats['datetime'])
            worksheet.write(row, 1, interaction['user_name'] or 'Неизвестный', formats['cell_data'])
            
            # Тип взаимодействия с понятными названиями
            request_type = interaction['request_type'] or 'unknown'
            type_names = {
                'navigation': '🔘 Навигация (кнопка)',
                'command': '⌨️ Команда',
                'general': '💬 Общий вопрос',
                'code_search': '🔍 Поиск по коду',
                'name_search': '📝 Поиск по названию',
                'question': '❓ Вопрос'
            }
            type_display = type_names.get(request_type, request_type)
            worksheet.write(row, 2, type_display, formats['cell_data'])
            
            # Текст взаимодействия
            query = interaction['query_text'] or ''
            worksheet.write(row, 3, query[:100] if query else '', formats['cell_data'])
            
            # Время обработки
            response_time = interaction['response_time'] or 0
            worksheet.write(row, 4, response_time, formats['cell_decimal'])
            
            # Статус (обновленная логика)
            success = interaction['success']
            has_answer = interaction['has_answer']
            
            if not success:
                # Реальная ошибка (некорректный формат и т.д.)
                status_text = '❌ Ошибка'
            elif success and not has_answer:
                # Корректно обработано, но результата нет (код не найден, нет информации)
                status_text = '✅ Обработано (нет результата)'
            else:
                # Корректно обработано, результат есть
                status_text = '✅ Успешно'
            worksheet.write(row, 5, status_text, formats['cell_data'])
            
            row += 1
    
    async def export_dau_report(self, days: int = 30) -> bytes:
        """Экспортирует отчет по DAU с улучшенным дизайном"""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        formats = self._create_formats(workbook)
        worksheet = workbook.add_worksheet('📊 DAU Отчет')
        
        # Заголовок
        worksheet.merge_range(0, 0, 0, 3,
                            f'ОТЧЕТ ПО АКТИВНЫМ ПОЛЬЗОВАТЕЛЯМ (DAU)',
                            formats['main_title'])
        worksheet.set_row(0, 30)
        
        row = 2
        
        # Заголовки таблицы
        headers = ['Дата', 'DAU', 'Всего запросов', 'Запросов на пользователя']
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        
        worksheet.set_column('A:D', 22)
        
        # Данные
        dau_data = await self.db.get_dau_metrics(days)
        
        row += 1
        for data in dau_data:
            worksheet.write(row, 0, str(data.get('activity_date', '')), formats['cell_data'])
            worksheet.write(row, 1, data.get('dau', 0), formats['cell_number'])
            worksheet.write(row, 2, data.get('total_requests', 0), formats['cell_number'])
            avg_req = data.get('avg_requests_per_user') or 0
            worksheet.write(row, 3, avg_req, formats['cell_decimal'])
            row += 1
        
        # Создаем график
        if len(dau_data) > 1:
            chart = workbook.add_chart({'type': 'line'})
            
            chart.add_series({
                'name': 'DAU',
                'categories': f'=\'📊 DAU Отчет\'!$A$4:$A${row}',
                'values': f'=\'📊 DAU Отчет\'!$B$4:$B${row}',
                'line': {'color': '#3B82F6', 'width': 3}
            })
            
            chart.set_title({
                'name': f'Динамика активных пользователей ({days} дней)',
                'name_font': {'size': 16, 'bold': True}
            })
            chart.set_x_axis({'name': 'Дата', 'name_font': {'size': 12}})
            chart.set_y_axis({'name': 'Количество пользователей', 'name_font': {'size': 12}})
            chart.set_size({'width': 800, 'height': 450})
            chart.set_legend({'position': 'bottom'})
            
            worksheet.insert_chart(row + 2, 0, chart)
        
        workbook.close()
        output.seek(0)
        return output.read()