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
            'bold': True,
            'font_size': 11,
            'font_color': '#1F2937',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '#,##0'
        })
        
        # Значение метрики (процент) - текстовый формат
        formats['metric_percent'] = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'font_color': '#1F2937',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Значение метрики (десятичное)
        formats['metric_decimal'] = workbook.add_format({
            'bold': True,
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
        
        # Положительный результат - текстовый формат
        formats['good'] = workbook.add_format({
            'bold': True,
            'font_color': SUCCESS_GREEN,
            'bg_color': '#D1FAE5',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Предупреждение - текстовый формат
        formats['warning'] = workbook.add_format({
            'bold': True,
            'font_color': WARNING_YELLOW,
            'bg_color': '#FEF3C7',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1
        })
        
        # Негативный результат - текстовый формат
        formats['bad'] = workbook.add_format({
            'bold': True,
            'font_color': ERROR_RED,
            'bg_color': '#FEE2E2',
            'align': 'right',
            'valign': 'vcenter',
            'border': 1
        })
        
        # KPI - высокий показатель
        formats['kpi_high'] = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'font_color': SUCCESS_GREEN,
            'bg_color': '#ECFDF5',
            'align': 'right',
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
            'align': 'right',
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
            'align': 'right',
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
        
        # 2. Лист с инструкциями (новый)
        await self._create_instructions_sheet(workbook, formats)
        
        # 3. Клиентские метрики
        await self._create_client_metrics_sheet(workbook, formats, days)
        
        # 4. Технические метрики
        await self._create_technical_metrics_sheet(workbook, formats, days)
        
        # 5. Метрики качества
        await self._create_quality_metrics_sheet(workbook, formats, days)
        
        # 6. Детальные данные
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
        worksheet.set_column('C:C', 25)
        worksheet.set_column('D:D', 60)  # Добавляем столбец для интерпретации
        
        row = 0
        
        # Главный заголовок
        worksheet.merge_range(row, 0, row, 3,
                            f'ОТЧЕТ ПО МЕТРИКАМ СИСТЕМЫ',
                            formats['main_title'])
        worksheet.set_row(row, 30)
        row += 1
        
        # Подзаголовок с периодом и датой
        period_text = f'Период анализа: {days} дней | Сформирован: {datetime.now().strftime("%d.%m.%Y %H:%M")}'
        worksheet.merge_range(row, 0, row, 3, period_text, formats['subtitle'])
        worksheet.set_row(row, 20)
        row += 2
        
        # Получаем данные
        metrics = await self.db.get_comprehensive_metrics(days)
        if not metrics:
            worksheet.write(row, 0, 'Нет данных за указанный период', formats['metric_label'])
            return
        
        # ===== КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ (KPI) =====
        worksheet.merge_range(row, 0, row, 3,
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
            # Норма задана как DAU/MAU = 5–15% (аналогичные продукты РФ).
            # В отчёте MAU сейчас не рассчитывается, поэтому НЕ оцениваем DAU по норме,
            # а показываем абсолютное значение и пояснение.
            worksheet.write(row, 1, avg_dau, formats['metric_decimal'])
            worksheet.write(row, 2, 'пользователей', formats['metric_value'])
            # По требованию: нормы для среднего DAU не выводим, так как в отчёте нет MAU.
            worksheet.write(row, 3, '', formats['cell_data'])
            row += 1
        
        # Успешность решения (conversion rate)
        # По требованию: «вне специализации» (🔵) НЕ должно влиять на проценты.
        # Поэтому считаем только по релевантным запросам: correct + no_answer (таймаут/нет информации).
        quality = metrics.get('quality_metrics', {})
        correct_answers = quality.get('correct', 0)
        timeout_or_no_info = quality.get('no_answer', 0)
        relevant_total = correct_answers + timeout_or_no_info
        accuracy = (correct_answers / relevant_total * 100) if relevant_total > 0 else 0
        
        worksheet.write(row, 0, '✅ Успешность решения (доля запросов с результатом)', formats['metric_label'])
        
        # Создаем специальный формат с соответствующим цветом без процента в num_format
        # Цвета под «Успешность решения (conversion rate)».
        # Норма (аналогичные продукты РФ): 60–80%.
        # Логика цветов:
        # - < 60%  : 🔴 ниже нормы
        # - 60–80% : 🟡 в норме
        # - ≥ 80%  : 🟢 выше нормы
        acc_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'font_color': '#10B981' if accuracy >= 80 else '#F59E0B' if accuracy >= 60 else '#EF4444',
            'bg_color': '#ECFDF5' if accuracy >= 80 else '#FFFBEB' if accuracy >= 60 else '#FEF2F2',
            'align': 'right',
            'valign': 'vcenter',
            'border': 2,
            'border_color': '#10B981' if accuracy >= 80 else '#F59E0B' if accuracy >= 60 else '#EF4444'
        })
        
        worksheet.write(row, 1, f'{accuracy:.1f}%', acc_format)
        worksheet.write(row, 2, f'{correct_answers}/{relevant_total} вопросов', formats['metric_value'])
        # Интерпретация
        # Норма по успешности решения (conversion rate) для аналогичных продуктов РФ: 60–80%.
        if accuracy >= 80:
            interpretation = '🟢 ≥ 80% — высокий уровень успешных решений (ориентир: 60–80%)'
        elif accuracy >= 60:
            interpretation = '🟡 60–80% — соответствует ориентиру (ориентир: 60–80%)'
        else:
            interpretation = '🔴 < 60% — ниже ориентира, требуется улучшение базы знаний/логики (ориентир: 60–80%)'
        worksheet.write(row, 3, interpretation, formats['cell_data'])
        row += 1
        
        # Оценки пользователей и response rate не выводятся в ежемесячном отчете.
        row += 1
        
        # ===== КЛИЕНТСКАЯ АКТИВНОСТЬ =====
        worksheet.merge_range(row, 0, row, 3,
                            '👥 КЛИЕНТСКАЯ АКТИВНОСТЬ',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        # Retention
        retention = client.get('retention', {})
        if retention and retention.get('today_users', 0) > 0:
            worksheet.merge_range(row, 0, row, 3, 'Показатели удержания (Retention)', formats['subsection_header'])
            row += 1
            
            ret_1d = retention.get('retention_1d', 0)
            worksheet.write(row, 0, '  • Retention 1 день', formats['metric_label'])
            
            # Создаем формат с цветом без процента в num_format
            ret_1d_format = workbook.add_format({
                'bold': True,
                'font_color': '#10B981' if ret_1d >= 20 else '#EF4444',
                'bg_color': '#D1FAE5' if ret_1d >= 20 else '#FEE2E2',
                'align': 'right',
                'valign': 'vcenter',
                'border': 1
            })
            worksheet.write(row, 1, f'{ret_1d:.1f}%', ret_1d_format)
            worksheet.write(row, 2, self._get_retention_status_1d(ret_1d), formats['cell_data'])
            # Интерпретация
            # Норма (аналогичные продукты РФ): 20–35%
            if ret_1d > 35:
                interpretation = '🟢 > 35% — выше нормы (норма: 20–35%)'
            elif ret_1d >= 20:
                interpretation = '🟢 20–35% — норма (норма: 20–35%)'
            else:
                interpretation = '🔴 < 20% — ниже нормы (норма: 20–35%)'
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
            
            ret_7d = retention.get('retention_7d', 0)
            worksheet.write(row, 0, '  • Retention 7 дней', formats['metric_label'])
            
            ret_7d_format = workbook.add_format({
                'bold': True,
                'font_color': '#10B981' if ret_7d >= 10 else '#EF4444',
                'bg_color': '#D1FAE5' if ret_7d >= 10 else '#FEE2E2',
                'align': 'right',
                'valign': 'vcenter',
                'border': 1
            })
            worksheet.write(row, 1, f'{ret_7d:.1f}%', ret_7d_format)
            worksheet.write(row, 2, self._get_retention_status_7d(ret_7d), formats['cell_data'])
            # Интерпретация
            # Норма (аналогичные продукты РФ): 10–20%
            if ret_7d > 20:
                interpretation = '🟢 > 20% — выше нормы (норма: 10–20%)'
            elif ret_7d >= 10:
                interpretation = '🟢 10–20% — норма (норма: 10–20%)'
            else:
                interpretation = '🔴 < 10% — ниже нормы (норма: 10–20%)'
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
            
            ret_30d = retention.get('retention_30d', 0)
            worksheet.write(row, 0, '  • Retention 30 дней', formats['metric_label'])
            
            ret_30d_format = workbook.add_format({
                'bold': True,
                'font_color': '#10B981' if ret_30d >= 8 else '#EF4444',
                'bg_color': '#D1FAE5' if ret_30d >= 8 else '#FEE2E2',
                'align': 'right',
                'valign': 'vcenter',
                'border': 1
            })
            worksheet.write(row, 1, f'{ret_30d:.1f}%', ret_30d_format)
            worksheet.write(row, 2, self._get_retention_status_30d(ret_30d), formats['cell_data'])
            # Интерпретация
            # Для Retention 30 дней норма в текущем списке KPI не задана → не указываем.
            interpretation = 'Норма для Retention 30 дней не задана (в этом отчёте показываем фактическое значение)'
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
        
        row += 1
        
        # === ВРЕМЯ АКТИВНОСТИ ПОЛЬЗОВАТЕЛЕЙ ===
        worksheet.merge_range(row, 0, row, 3,
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
                'font_color': '#10B981' if 2 <= avg_duration <= 5 else '#F59E0B' if avg_duration < 2 or 5 < avg_duration <= 10 else '#EF4444',
                'bg_color': '#ECFDF5' if 2 <= avg_duration <= 5 else '#FFFBEB' if avg_duration < 2 or 5 < avg_duration <= 10 else '#FEF2F2',
                'align': 'center',
                'valign': 'vcenter',
                'border': 2,
                'border_color': '#10B981' if 2 <= avg_duration <= 5 else '#F59E0B' if avg_duration < 2 or 5 < avg_duration <= 10 else '#EF4444',
                'num_format': '0.00'
            })
            worksheet.write(row, 1, avg_duration, kpi_format_duration)
            worksheet.write(row, 2, 'минут', formats['metric_value'])
            # Интерпретация
            if 2 <= avg_duration <= 5:
                interpretation = '🟢 2–5 мин — оптимально (норма: 2-5 минут)'
            elif avg_duration < 1:
                interpretation = '🔴 < 1 мин — пользователь не находит нужное (норма: 2-5 минут)'
            elif avg_duration < 2:
                interpretation = '🟡 1-2 мин — быстрое использование (норма: 2-5 минут)'
            elif 5 < avg_duration <= 10:
                interpretation = '🟡 5-10 мин — приемлемо (норма: 2-5 минут)'
            else:
                interpretation = '🔴 > 10 мин — возможны сложности с навигацией (норма: 2-5 минут)'
            worksheet.write(row, 3, interpretation, formats['cell_data'])
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
        else:
            worksheet.write(row, 0, '⏱️ Средняя длительность сессии', formats['metric_label'])
            worksheet.merge_range(row, 1, row, 3, 'Данные недоступны', formats['metric_value'])
            row += 1
        
        row += 1
        
        row += 1
        
        # Объем обращений
        if dau_list:
            worksheet.merge_range(row, 0, row, 3, 'Объем обращений', formats['subsection_header'])
            row += 1
            
            # NOTE: dau_list приходит отсортированным по убыванию даты (ORDER BY activity_date DESC)
            # dau_list[0] = самая свежая дата (сегодня или последний день с данными)
            # dau_list[:7] = последние 7 дней
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
        worksheet.merge_range(row, 0, row, 3,
                            '⚡ ПРОИЗВОДИТЕЛЬНОСТЬ СИСТЕМЫ',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        # Получаем данные о времени ответа
        tech = metrics.get('technical_metrics', {})
        perf = tech.get('response_time', {})
        overall = perf.get('overall', {}) if perf else {}
        
        if overall:
            # Метрика: распределение времени ответа.
            # По просьбе: интервалы возвращены к прежней схеме (≤3 / 3–6 / 6–10 / >10 секунд).
            #
            # Интервалы взаимно-исключающие (без пересечений),
            # проценты считаем от количества ЗАМЕРЕННЫХ ответов (response_time IS NOT NULL),
            # чтобы распределение корректно суммировалось в ~100%.
            import aiosqlite
            start_date = datetime.now() - timedelta(days=days)

            async with aiosqlite.connect(self.db.db_path) as db:
                cursor = await db.execute('''
                    SELECT
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN rm.response_time IS NULL THEN 1 ELSE 0 END) as no_response_time,
                        SUM(CASE WHEN rm.response_time IS NOT NULL THEN 1 ELSE 0 END) as measured_requests,
                        -- ≤ 3 сек
                        SUM(CASE WHEN rm.response_time IS NOT NULL AND rm.response_time <= 3 THEN 1 ELSE 0 END) as le_3_sec,
                        -- (3; 6] сек
                        SUM(CASE WHEN rm.response_time IS NOT NULL AND rm.response_time > 3 AND rm.response_time <= 6 THEN 1 ELSE 0 END) as between_3_6_sec,
                        -- (6; 10] сек
                        SUM(CASE WHEN rm.response_time IS NOT NULL AND rm.response_time > 6 AND rm.response_time <= 10 THEN 1 ELSE 0 END) as between_6_10_sec,
                        -- > 10 сек
                        SUM(CASE WHEN rm.response_time IS NOT NULL AND rm.response_time > 10 THEN 1 ELSE 0 END) as gt_10_sec
                    FROM request_metrics rm
                    JOIN users u ON rm.user_id = u.telegram_id
                    WHERE rm.timestamp >= ?
                      AND rm.request_type IN ('general', 'code_search', 'name_search')
                      AND u.role != 'admin'
                ''', (start_date,))
                stats = await cursor.fetchone()

            total_requests = (stats[0] or 0) if stats else 0
            no_response_time = (stats[1] or 0) if stats else 0
            measured_requests = (stats[2] or 0) if stats else 0
            le_3_sec = (stats[3] or 0) if stats else 0
            between_3_6_sec = (stats[4] or 0) if stats else 0
            between_6_10_sec = (stats[5] or 0) if stats else 0
            gt_10_sec = (stats[6] or 0) if stats else 0

            # Проценты считаем от ЗАМЕРЕННЫХ (measured_requests)
            pct_le_3 = (le_3_sec / measured_requests * 100) if measured_requests > 0 else 0
            pct_3_6 = (between_3_6_sec / measured_requests * 100) if measured_requests > 0 else 0
            pct_6_10 = (between_6_10_sec / measured_requests * 100) if measured_requests > 0 else 0
            pct_gt_10 = (gt_10_sec / measured_requests * 100) if measured_requests > 0 else 0

            # Отдельно показываем долю "не измерено" (NULL response_time) от общего числа запросов
            pct_no_rt = (no_response_time / total_requests * 100) if total_requests > 0 else 0

            percent_num_format = '0.0%'

            # 1) ≤ 3 секунд
            worksheet.write(row, 0, '⚡ Время ответа ≤ 3 секунд', formats['metric_label'])
            pct_3sec_format = workbook.add_format({
                'bold': True,
                'font_color': '#10B981',
                'bg_color': '#D1FAE5',
                'align': 'right',
                'valign': 'vcenter',
                'border': 1,
                'num_format': percent_num_format
            })
            worksheet.write(row, 1, (pct_le_3 / 100), pct_3sec_format)
            worksheet.write(row, 2, f'{le_3_sec}/{measured_requests}', formats['metric_value'])
            worksheet.write(row, 3, 'Доля быстрых ответов среди замеренных', formats['cell_data'])
            row += 1

            # 2) 3–6 секунд
            worksheet.write(row, 0, '⚡ Время ответа 3–6 секунд', formats['metric_label'])
            # 30–60 сек находится в пределах нормы → зелёный
            pct_3_6_format = workbook.add_format({
                'bold': True,
                'font_color': '#10B981',
                'bg_color': '#D1FAE5',
                'align': 'right',
                'valign': 'vcenter',
                'border': 1,
                'num_format': percent_num_format
            })
            worksheet.write(row, 1, (pct_3_6 / 100), pct_3_6_format)
            worksheet.write(row, 2, f'{between_3_6_sec}/{measured_requests}', formats['metric_value'])
            worksheet.write(row, 3, 'Доля ответов, укладывающихся в 3–6 секунд', formats['cell_data'])
            row += 1

            # 3) 6–10 секунд
            worksheet.write(row, 0, '🟡 Время ответа 6–10 секунд', formats['metric_label'])
            # 60–120 сек = верхняя часть нормы → жёлтый (требует наблюдения)
            pct_6_10_format = workbook.add_format({
                'bold': True,
                'font_color': '#F59E0B',
                'bg_color': '#FEF3C7',
                'align': 'right',
                'valign': 'vcenter',
                'border': 1,
                'num_format': percent_num_format
            })
            worksheet.write(row, 1, (pct_6_10 / 100), pct_6_10_format)
            worksheet.write(row, 2, f'{between_6_10_sec}/{measured_requests}', formats['metric_value'])
            worksheet.write(row, 3, 'Пограничная зона: ответы заметно медленнее быстрых', formats['cell_data'])
            row += 1

            # 4) > 10 секунд
            worksheet.write(row, 0, '🔴 Время ответа > 10 секунд', formats['metric_label'])
            pct_10sec_format = workbook.add_format({
                'bold': True,
                'font_color': '#EF4444',
                'bg_color': '#FEE2E2',
                'align': 'right',
                'valign': 'vcenter',
                'border': 1,
                'num_format': percent_num_format
            })
            worksheet.write(row, 1, (pct_gt_10 / 100), pct_10sec_format)
            worksheet.write(row, 2, f'{gt_10_sec}/{measured_requests}', formats['metric_value'])
            worksheet.write(row, 3, 'Доля очень медленных ответов (>10 секунд)', formats['cell_data'])
            row += 1

            # 5) Не измерено (response_time IS NULL) — отдельно, чтобы было понятно, почему распределение не даёт 100% от total_requests
            if total_requests > 0 and no_response_time > 0:
                worksheet.write(row, 0, '⚪ Ответы без метрики времени (NULL)', formats['metric_label'])
                pct_no_rt_format = workbook.add_format({
                    'bold': True,
                    'font_color': '#6B7280',
                    'bg_color': '#F3F4F6',
                    'align': 'right',
                    'valign': 'vcenter',
                    'border': 1,
                    'num_format': percent_num_format
                })
                worksheet.write(row, 1, (pct_no_rt / 100), pct_no_rt_format)
                worksheet.write(row, 2, f'{no_response_time}/{total_requests}', formats['metric_value'])
                worksheet.write(row, 3, 'Эти запросы НЕ вошли в распределение по времени ответа', formats['cell_data'])
                row += 1
            
            # Среднее время ответа
            avg_response = overall.get('avg_response_time', 0)
            worksheet.write(row, 0, '⏱️ Среднее время ответа', formats['metric_label'])
            worksheet.write(row, 1, avg_response, formats['metric_decimal'])
            worksheet.write(row, 2, 'секунд', formats['metric_value'])
            row += 1
            
            # Минимальное время ответа
            min_response = overall.get('min_response_time', 0)
            worksheet.write(row, 0, '⚡ Минимальное время ответа', formats['metric_label'])
            worksheet.write(row, 1, min_response, formats['metric_decimal'])
            worksheet.write(row, 2, 'секунд', formats['metric_value'])
            row += 1
            
            # Максимальное время ответа (с учетом аварийных случаев)
            max_response = overall.get('max_response_time', 0)
            worksheet.write(row, 0, '🔴 Максимальное время с учетом аварийных случаев', formats['metric_label'])
            worksheet.write(row, 1, max_response, formats['metric_decimal'])
            worksheet.write(row, 2, 'секунд', formats['metric_value'])
            row += 2
        
        # ===== КАЧЕСТВО ОБСЛУЖИВАНИЯ =====
        worksheet.merge_range(row, 0, row, 3,
                            '🎯 КАЧЕСТВО ОБСЛУЖИВАНИЯ',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        quality = metrics.get('quality_metrics', {})
        if quality:
            total = quality.get('total', 0)
            correct = quality.get('correct', 0)
            out_of_scope = quality.get('out_of_scope', 0)  # ПЕРЕИМЕНОВАНО из 'incorrect'
            no_answer = quality.get('no_answer', 0)
            
            worksheet.write(row, 0, '📊 Всего запросов обработано', formats['metric_label'])
            worksheet.write(row, 1, total, formats['metric_value'])
            row += 1
            
            correct_pct = quality.get('correct_percentage', 0)
            worksheet.write(row, 0, '✅ Корректных ответов (с данными)', formats['metric_label'])
            
            correct_format = workbook.add_format({
                'bold': True,
                'font_color': '#10B981' if correct_pct >= 95 else '#F59E0B' if correct_pct >= 90 else '#EF4444',
                'bg_color': '#D1FAE5' if correct_pct >= 95 else '#FEF3C7' if correct_pct >= 90 else '#FEE2E2',
                'align': 'right',
                'valign': 'vcenter',
                'border': 1
            })
            worksheet.write(row, 1, f'{correct_pct:.1f}%', correct_format)
            worksheet.write(row, 2, f'{correct} запросов', formats['metric_value'])
            # Интерпретация
            if correct_pct >= 95:
                interpretation = '🟢 Высокий уровень надёжности (норма: ≥95%)'
            elif correct_pct >= 90:
                interpretation = '🟡 Требует расширения базы знаний (норма: ≥95%)'
            else:
                interpretation = '🔴 База знаний требует коррекции (норма: ≥95%)'
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
            
            # По требованию: «Вопросы вне специализации» считаем как
            # ✅ Обработано (нет результата) из листа «📋 Детали»
            worksheet.write(row, 0, '🔵 Вопросы вне специализации бота', formats['metric_label'])
            
            out_of_scope_format = workbook.add_format({
                'bold': True,
                'font_color': '#3B82F6',  # Синий цвет (нейтральный)
                'bg_color': '#DBEAFE',
                'align': 'right',
                'valign': 'vcenter',
                'border': 1
            })
            # По требованию: для «вне специализации» показываем только количество, без процента.
            worksheet.write(row, 1, '', out_of_scope_format)
            worksheet.write(row, 2, f'{out_of_scope} запросов', formats['metric_value'])
            # Интерпретация
            interpretation = '🔵 Бот корректно определил вопрос вне специализации (не влияет на точность)'
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
            
            # По требованию: «Без ответа» = пользователь не получил ответ в течение 60 секунд
            # (см. расчёт в get_quality_metrics_summary)
            no_answer_pct = quality.get('timeout_no_answer_percentage', quality.get('no_answer_percentage', 0))
            worksheet.write(row, 0, '⚠️ Без ответа (нет информации)', formats['metric_label'])
            
            no_answer_format = workbook.add_format({
                'bold': True,
                'font_color': '#10B981' if no_answer_pct <= 5 else '#F59E0B' if no_answer_pct <= 10 else '#EF4444',
                'bg_color': '#D1FAE5' if no_answer_pct <= 5 else '#FEF3C7' if no_answer_pct <= 10 else '#FEE2E2',
                'align': 'right',
                'valign': 'vcenter',
                'border': 1
            })
            worksheet.write(row, 1, f'{no_answer_pct:.1f}%', no_answer_format)
            worksheet.write(row, 2, f'{no_answer} запросов', formats['metric_value'])
            # Интерпретация
            if no_answer_pct <= 5:
                interpretation = '🟢 Допустимо для редких формулировок (норма: ≤5%)'
            elif no_answer_pct <= 10:
                interpretation = '🟡 Имеются пробелы в базе знаний (норма: ≤5%)'
            else:
                interpretation = '🔴 > 10% — серьёзные пробелы в базе знаний (норма: ≤5%)'
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
    
    def _get_retention_status_1d(self, retention_pct):
        """Возвращает статус retention 1 день"""
        if retention_pct >= 35:
            return '🟢 Отлично'
        elif retention_pct >= 20:
            return '🟡 Норма'
        else:
            return '🔴 Требует внимания'
    
    def _get_retention_status_7d(self, retention_pct):
        """Возвращает статус retention 7 дней"""
        if retention_pct >= 20:
            return '🟢 Отлично'
        elif retention_pct >= 10:
            return '🟡 Норма'
        else:
            return '🔴 Требует внимания'
    
    def _get_retention_status_30d(self, retention_pct):
        """Возвращает статус retention 30 дней"""
        if retention_pct >= 15:
            return '🟢 Отлично'
        elif retention_pct >= 8:
            return '🟡 Норма'
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
        # ВАЖНО:
        # - dau берём из user_activity (активность пользователей)
        # - «Всего запросов» в этом листе должно совпадать с прежней семантикой
        #   (валидные запросы из request_metrics: general/code_search/name_search)
        valid_requests_by_day = await self.db.get_valid_requests_by_day(days)
        
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
                activity_date = str(data.get('activity_date', ''))
                worksheet.write(row, 0, activity_date, formats['cell_data'])
                worksheet.write(row, 1, data.get('dau', 0), formats['cell_number'])
                # «Всего запросов» = валидные запросы (как раньше)
                worksheet.write(row, 2, valid_requests_by_day.get(activity_date, 0), formats['cell_number'])
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
                ('✅ Корректных ответов (с данными)', quality.get('correct', 0), quality.get('correct_percentage', 0)),
                ('🔵 Вопросы вне специализации', quality.get('out_of_scope', 0), quality.get('out_of_scope_percentage', 0)),
                ('⚠️ Без ответа (нет информации)', quality.get('no_answer', 0), quality.get('no_answer_percentage', 0)),
            ]
            
            for metric_name, value, percent in metrics_data:
                worksheet.write(row, 0, metric_name, formats['metric_label'])
                worksheet.write(row, 1, value, formats['metric_value'])
                
                # Цветовое выделение процентов
                if 'Корректных' in metric_name:
                    pct_format = formats['good'] if percent >= 70 else formats['warning'] if percent >= 50 else formats['bad']
                else:
                    pct_format = formats['metric_percent']
                
                worksheet.write(row, 2, f'{percent:.0f}%', pct_format)
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
                worksheet.write(row, 2, f'{pct:.0f}%', formats['metric_percent'])
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
    
    async def _create_instructions_sheet(self, workbook, formats):
        """Создает лист с инструкциями по интерпретации метрик"""
        worksheet = workbook.add_worksheet('📖 Инструкции')
        
        # Настройка колонок
        worksheet.set_column('A:A', 30)  # Метрика
        worksheet.set_column('B:B', 50)  # Что обозначает
        worksheet.set_column('C:C', 25)  # Норма
        worksheet.set_column('D:D', 80)  # Интерпретация
        
        row = 0
        
        # Главный заголовок
        worksheet.merge_range(row, 0, row, 3,
                            'ИНСТРУКЦИЯ ПО ИНТЕРПРЕТАЦИИ МЕТРИК',
                            formats['main_title'])
        worksheet.set_row(row, 30)
        row += 2
        
        # === КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ ЭФФЕКТИВНОСТИ ===
        worksheet.merge_range(row, 0, row, 3,
                            '🎯 КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ ЭФФЕКТИВНОСТИ',
                            formats['section_header'])
        row += 1
        
        # Заголовки таблицы
        headers = ['Метрика', 'Что обозначает', 'Норма', 'Интерпретация']
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        row += 1
        
        # Данные по KPI
        kpi_data = [
            ('Средний DAU', 'Среднее число уникальных пользователей в день',
             '5 - 15% от месячной активности пользователей',
             '🔴 < 5 — низкая вовлечённость\n🟢 5–15 — норма\n🟢 >15 — высокая интеграция'),
            
            ('Коэффициент точности ответов', 'Доля корректных ответов среди оцененных',
             '≥ 95%',
             '🔴 < 90% — проблемы с контентом\n🟢 ≥ 95% — высокий показатель понимания сути'),
            
            ('Процент положительных оценок', 'Доля положительных оценок в бинарной системе (да/нет)',
             '≥ 80%',
             '🔴 < 60% — низкая удовлетворенность\n🟡 60-80% — требует внимания\n🟢 ≥ 80% — высокая удовлетворенность'),
        ]
        
        for metric, meaning, norm, interpretation in kpi_data:
            worksheet.write(row, 0, metric, formats['cell_data'])
            worksheet.write(row, 1, meaning, formats['cell_data'])
            worksheet.write(row, 2, norm, formats['cell_data'])
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
        
        row += 1
        
        # === КЛИЕНТСКАЯ АКТИВНОСТЬ (RETENTION) ===
        worksheet.merge_range(row, 0, row, 3,
                            '👥 КЛИЕНТСКАЯ АКТИВНОСТЬ (RETENTION)',
                            formats['section_header'])
        row += 1
        
        # Заголовки таблицы
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        row += 1
        
        # Данные по Retention
        retention_data = [
            ('Retention 1 день', 'Доля пользователей, вернувшихся на следующий день',
             '20–35%',
             '🔴 < 20% — первый опыт не мотивирует вернуться\n🟢 20–35% — норма\n🟢 >35% — отличный показатель'),
            
            ('Retention 7 дней', '% пользователей, обращающихся к системе повторно в течение недели',
             '10–20%',
             '🔴 < 10% — низкая ценность для повторного использования\n🟢 10–20% — хороший показатель для эпизодических запросов'),
            
            ('Retention 30 дней', 'Долгосрочная востребованность: сколько пользователей возвращаются спустя месяц',
             '8–15%',
             '🔴 < 5% — Низкий показатель\n🟢 ≥ 8% — норма'),
        ]
        
        for metric, meaning, norm, interpretation in retention_data:
            worksheet.write(row, 0, metric, formats['cell_data'])
            worksheet.write(row, 1, meaning, formats['cell_data'])
            worksheet.write(row, 2, norm, formats['cell_data'])
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
        
        row += 1
        
        # === ВРЕМЯ АКТИВНОСТИ ПОЛЬЗОВАТЕЛЕЙ ===
        worksheet.merge_range(row, 0, row, 3,
                            '⏱️ ВРЕМЯ АКТИВНОСТИ ПОЛЬЗОВАТЕЛЕЙ',
                            formats['section_header'])
        row += 1
        
        # Заголовки таблицы
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        row += 1
        
        # Данные по времени активности
        activity_data = [
            ('Средняя длительность сессии', 'Среднее время, которое пользователь проводит в боте за одну сессию',
             '2–5 минут',
             '🔴 < 1 мин — пользователь не находит нужное\n🟢 2–5 мин — оптимально\n🔴 > 10 мин — возможны сложности с навигацией или поиском'),
            
            ('Всего сессий за период', 'Общее число сессий всех пользователей за отчётный период',
             'Не нормируется, но важна стабильность или рост',
             '📉 Резкое снижение — сигнал к анализу вовлечённости\n📈 Пик активности — повод изучить внешние триггеры (обучение, рассылка и др.)'),
            
            ('Суммарное время активности', 'Общее время всех пользователей в боте за период',
             'Не нормируется',
             'Используется для расчёта средних значений и оценки общей нагрузки на систему'),
        ]
        
        for metric, meaning, norm, interpretation in activity_data:
            worksheet.write(row, 0, metric, formats['cell_data'])
            worksheet.write(row, 1, meaning, formats['cell_data'])
            worksheet.write(row, 2, norm, formats['cell_data'])
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
        
        row += 1
        
        # === ОБЪЁМ ОБРАЩЕНИЙ ===
        worksheet.merge_range(row, 0, row, 3,
                            '📊 ОБЪЁМ ОБРАЩЕНИЙ',
                            formats['section_header'])
        row += 1
        
        # Заголовки таблицы
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        row += 1
        
        # Данные по объему обращений
        volume_data = [
            ('Запросов за день / неделю / месяц', 'Интенсивность использования бота',
             'Не нормируется',
             '🟢 Низкий, но стабильный объём — типично для профессиональных инструментов\n🔴 Полное отсутствие активности в течение недели — требует проверки доступности и вовлечённости'),
        ]
        
        for metric, meaning, norm, interpretation in volume_data:
            worksheet.write(row, 0, metric, formats['cell_data'])
            worksheet.write(row, 1, meaning, formats['cell_data'])
            worksheet.write(row, 2, norm, formats['cell_data'])
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
        
        row += 1
        
        # === ПРОИЗВОДИТЕЛЬНОСТЬ СИСТЕМЫ ===
        worksheet.merge_range(row, 0, row, 3,
                            '⚡ ПРОИЗВОДИТЕЛЬНОСТЬ СИСТЕМЫ',
                            formats['section_header'])
        row += 1
        
        # Заголовки таблицы
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        row += 1
        
        # Данные по производительности
        performance_data = [
            ('Ответы < 6 сек', 'Доля запросов, обработанных менее чем за 6 секунд',
             '≥ 95%',
             ''),
            
            ('Ответы > 10 сек', 'Доля запросов с длительной обработкой',
             '≤ 2%',
             ''),
            
            ('Среднее время ответа', 'Средняя скорость генерации ответа',
             '< 6 секунд',
             ''),
            
            ('Максимальное время', 'Самое долгое время обработки за период (включая аварийные случаи)',
             '< 30 секунд',
             '🔴 Превышение — признак неоптимального запроса или технической проблемы, требует анализа'),
        ]
        
        for metric, meaning, norm, interpretation in performance_data:
            worksheet.write(row, 0, metric, formats['cell_data'])
            worksheet.write(row, 1, meaning, formats['cell_data'])
            worksheet.write(row, 2, norm, formats['cell_data'])
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
        
        row += 1
        
        # === КАЧЕСТВО ОБСЛУЖИВАНИЯ ===
        worksheet.merge_range(row, 0, row, 3,
                            '🎯 КАЧЕСТВО ОБСЛУЖИВАНИЯ',
                            formats['section_header'])
        row += 1
        
        # Заголовки таблицы
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        row += 1
        
        # Данные по качеству
        quality_data = [
            ('Корректных ответов (с данными)', 'Доля запросов с точной и полезной информацией',
             '≥ 95%',
             '🟢 Высокий уровень надёжности\n🔴 < 90% — база знаний требует расширения или коррекции'),
            
            ('Вопросы вне специализации', 'Вопросы не относящиеся к лабораторной диагностике (цены, лечение, диагнозы и т.д.)',
             'Не нормируется',
             '🔵 Бот корректно определил вопрос вне специализации и сообщил об этом пользователю.\nНЕ влияет на коэффициент точности, т.к. это корректная работа бота'),
            
            ('Без ответа (нет информации)', 'Доля запросов в рамках специализации, по которым не найдена информация в базе знаний',
             '≤ 5%',
             '🟢 ≤ 5% — допустимо для редких формулировок\n🔴 > 5% — указывает на пробелы в базе знаний'),
        ]
        
        for metric, meaning, norm, interpretation in quality_data:
            worksheet.write(row, 0, metric, formats['cell_data'])
            worksheet.write(row, 1, meaning, formats['cell_data'])
            worksheet.write(row, 2, norm, formats['cell_data'])
            worksheet.write(row, 3, interpretation, formats['cell_data'])
            row += 1
        
        row += 1
        
        # === ОЦЕНКИ ПОЛЬЗОВАТЕЛЕЙ (БИНАРНАЯ СИСТЕМА) ===
        worksheet.merge_range(row, 0, row, 3,
                            '👍👎 ОЦЕНКИ ПОЛЬЗОВАТЕЛЕЙ (БИНАРНАЯ СИСТЕМА)',
                            formats['section_header'])
        row += 1
        
        # Заголовки таблицы
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        row += 1
        
        # Данные по оценкам пользователей
        user_feedback_data = [
            ('Процент положительных оценок (Satisfaction Rate)', 
             'Доля ответов "Да" из всех полученных оценок',
             '≥ 80%',
             '🔴 < 60% — низкая удовлетворенность, требуется анализ проблем\n🟡 60-80% — требует внимания и улучшений\n🟢 ≥ 80% — высокая удовлетворенность пользователей'),
            
            ('Процент отрицательных оценок (Dissatisfaction Rate)', 
             'Доля ответов "Нет" из всех полученных оценок',
             '< 10%',
             '🟢 < 10% — отличный показатель качества\n🟡 10-20% — требует улучшений и анализа причин\n🔴 ≥ 20% — критический уровень недовольства, нужны срочные меры'),
            
            ('Общее количество оценок', 
             'Суммарное количество оценок (Да + Нет + Отказы от оценки) за период',
             'Не нормируется',
             'Используется для оценки статистической значимости и вовлеченности пользователей'),
            
            ('Коэффициент отклика (Response Rate)', 
             'Соотношение полученных оценок к общему количеству валидных взаимодействий (general/code_search/name_search)',
             '≥ 20%',
             '🔴 < 10% — низкая вовлеченность, пользователи не оставляют обратную связь\n🟡 10-20% — средняя вовлеченность, можно улучшить\n🟢 ≥ 20% — высокая вовлеченность, пользователи активно оценивают'),
        ]
        
        for metric, meaning, norm, interpretation in user_feedback_data:
            worksheet.write(row, 0, metric, formats['cell_data'])
            worksheet.write(row, 1, meaning, formats['cell_data'])
            worksheet.write(row, 2, norm, formats['cell_data'])
            worksheet.write(row, 3, interpretation, formats['cell_data'])
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
    
    async def export_session_activity_report(self, days: int = 30) -> bytes:
        """
        Создает детальный отчет по времени активности пользователей.
        Анализирует причины запредельного времени сессий.
        """
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        formats = self._create_formats(workbook)
        
        # === ЛИСТ 1: СВОДКА ===
        summary_sheet = workbook.add_worksheet('📊 Сводка')
        await self._create_session_summary_sheet(summary_sheet, formats, days)
        
        # === ЛИСТ 2: ДЕТАЛЬНЫЕ СЕССИИ ===
        detail_sheet = workbook.add_worksheet('🔍 Детали сессий')
        await self._create_session_detail_sheet(detail_sheet, formats, days)
        
        # === ЛИСТ 3: АНАЛИЗ ПРОБЛЕМ ===
        analysis_sheet = workbook.add_worksheet('⚠️ Анализ проблем')
        await self._create_session_analysis_sheet(analysis_sheet, formats, days)
        
        # === ЛИСТ 4: РЕКОМЕНДАЦИИ ===
        recommendations_sheet = workbook.add_worksheet('💡 Рекомендации')
        await self._create_recommendations_sheet(recommendations_sheet, formats, days)
        
        workbook.close()
        output.seek(0)
        return output.read()
    
    async def _create_session_summary_sheet(self, worksheet, formats, days):
        """Создает сводный лист с общей статистикой по сессиям"""
        # Настройка колонок
        worksheet.set_column('A:A', 40)
        worksheet.set_column('B:B', 20)
        worksheet.set_column('C:C', 30)
        
        row = 0
        
        # Заголовок
        worksheet.merge_range(row, 0, row, 2,
                            '📊 ОТЧЕТ ПО ВРЕМЕНИ АКТИВНОСТИ ПОЛЬЗОВАТЕЛЕЙ',
                            formats['main_title'])
        worksheet.set_row(row, 30)
        row += 1
        
        # Подзаголовок
        period_text = f'Период: последние {days} дней | Сформирован: {datetime.now().strftime("%d.%m.%Y %H:%M")}'
        worksheet.merge_range(row, 0, row, 2, period_text, formats['subtitle'])
        worksheet.set_row(row, 20)
        row += 2
        
        # Получаем данные
        sessions_data = await self.db.get_detailed_session_report(days)
        session_metrics = await self.db.get_session_metrics(days)
        
        if not sessions_data:
            worksheet.write(row, 0, 'Нет данных о сессиях за указанный период', formats['metric_label'])
            return
        
        # === ОБЩАЯ СТАТИСТИКА ===
        worksheet.merge_range(row, 0, row, 2,
                            '📈 ОБЩАЯ СТАТИСТИКА',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        total_sessions = len(sessions_data)
        avg_duration = sum(s['duration_minutes'] for s in sessions_data) / total_sessions if total_sessions > 0 else 0
        max_duration = max(s['duration_minutes'] for s in sessions_data) if sessions_data else 0
        min_duration = min(s['duration_minutes'] for s in sessions_data) if sessions_data else 0
        
        # Средние показатели валидных запросов
        avg_valid_requests = sum(s.get('valid_requests', 0) for s in sessions_data) / total_sessions if total_sessions > 0 else 0
        avg_total_actions = sum(s.get('total_actions', 0) for s in sessions_data) / total_sessions if total_sessions > 0 else 0
        avg_active_time = sum(s.get('active_time_minutes', 0) for s in sessions_data) / total_sessions if total_sessions > 0 else 0
        avg_reading_time = avg_duration - avg_active_time
        
        worksheet.write(row, 0, '📊 Всего сессий', formats['metric_label'])
        worksheet.write(row, 1, total_sessions, formats['metric_value'])
        row += 1
        
        worksheet.write(row, 0, '⏱️ Средняя ОБЩАЯ длительность', formats['metric_label'])
        kpi_format = formats['kpi_high'] if avg_duration >= 5 else formats['kpi_medium'] if avg_duration >= 2 else formats['kpi_low']
        worksheet.write(row, 1, avg_duration, kpi_format)
        worksheet.write(row, 2, 'минут', formats['metric_value'])
        row += 1
        
        worksheet.write(row, 0, '⚡ Среднее АКТИВНОЕ время', formats['metric_label'])
        worksheet.write(row, 1, avg_active_time, formats['metric_decimal'])
        worksheet.write(row, 2, 'минут (работа с запросами)', formats['cell_data'])
        row += 1
        
        worksheet.write(row, 0, '📖 Среднее время на ЧТЕНИЕ', formats['metric_label'])
        worksheet.write(row, 1, avg_reading_time, formats['metric_decimal'])
        worksheet.write(row, 2, 'минут (изучение материала)', formats['cell_data'])
        row += 1
        
        worksheet.write(row, 0, '📊 Среднее валидных запросов', formats['metric_label'])
        worksheet.write(row, 1, avg_valid_requests, formats['metric_decimal'])
        worksheet.write(row, 2, 'запросов/сессию', formats['metric_value'])
        row += 1
        
        worksheet.write(row, 0, '🔘 Среднее всех действий', formats['metric_label'])
        worksheet.write(row, 1, avg_total_actions, formats['metric_decimal'])
        worksheet.write(row, 2, 'действий/сессию', formats['metric_value'])
        row += 1
        
        worksheet.write(row, 0, '⏰ Максимальная длительность', formats['metric_label'])
        worksheet.write(row, 1, max_duration, formats['metric_decimal'])
        worksheet.write(row, 2, f'минут ({max_duration/60:.1f} ч)', formats['metric_value'])
        row += 1
        
        worksheet.write(row, 0, '⚡ Минимальная длительность', formats['metric_label'])
        worksheet.write(row, 1, min_duration, formats['metric_decimal'])
        worksheet.write(row, 2, 'минут', formats['metric_value'])
        row += 2
        
        # === РАСПРЕДЕЛЕНИЕ ПО ДЛИТЕЛЬНОСТИ ===
        worksheet.merge_range(row, 0, row, 2,
                            '⏱️ РАСПРЕДЕЛЕНИЕ ПО ДЛИТЕЛЬНОСТИ',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        # Категоризация сессий
        quick_sessions = len([s for s in sessions_data if s['duration_minutes'] < 2])
        normal_sessions = len([s for s in sessions_data if 2 <= s['duration_minutes'] < 10])
        long_sessions = len([s for s in sessions_data if 10 <= s['duration_minutes'] < 30])
        very_long_sessions = len([s for s in sessions_data if s['duration_minutes'] >= 30])
        
        categories = [
            ('⚡ Быстрые сессии (< 2 мин)', quick_sessions),
            ('✅ Обычные сессии (2-10 мин)', normal_sessions),
            ('⏰ Длинные сессии (10-30 мин)', long_sessions),
            ('🔴 Очень длинные сессии (> 30 мин)', very_long_sessions)
        ]
        
        for cat_name, count in categories:
            worksheet.write(row, 0, cat_name, formats['metric_label'])
            worksheet.write(row, 1, count, formats['metric_value'])
            percent = (count / total_sessions * 100) if total_sessions > 0 else 0
            worksheet.write(row, 2, f'{percent:.0f}%', formats['metric_percent'])
            row += 1
        
        row += 1
        
        # === ТОП ПРИЧИН ДЛИННЫХ СЕССИЙ ===
        worksheet.merge_range(row, 0, row, 2,
                            '🔍 ТОП ПРИЧИН ДЛИННЫХ СЕССИЙ',
                            formats['section_header'])
        worksheet.set_row(row, 25)
        row += 1
        
        # Собираем все причины
        all_reasons = []
        for session in sessions_data:
            if session['duration_minutes'] > 10:  # Только длинные сессии
                all_reasons.extend(session.get('analysis_reasons', []))
        
        # Подсчитываем частоту каждой причины
        from collections import Counter
        reason_counts = Counter(all_reasons)
        top_reasons = reason_counts.most_common(10)
        
        if top_reasons:
            worksheet.write(row, 0, 'Причина', formats['table_header'])
            worksheet.write(row, 1, 'Количество', formats['table_header'])
            worksheet.write(row, 2, 'Процент от длинных', formats['table_header'])
            row += 1
            
            long_count = len([s for s in sessions_data if s['duration_minutes'] > 10])
            for reason, count in top_reasons:
                worksheet.write(row, 0, reason, formats['cell_data'])
                worksheet.write(row, 1, count, formats['cell_number'])
                percent = (count / long_count * 100) if long_count > 0 else 0
                worksheet.write(row, 2, f'{percent:.0f}%', formats['metric_percent'])
                row += 1
        else:
            worksheet.write(row, 0, 'Нет длинных сессий для анализа', formats['metric_label'])
    
    async def _create_session_detail_sheet(self, worksheet, formats, days):
        """Создает детальный лист с информацией по каждой сессии"""
        # Настройка колонок
        worksheet.set_column('A:A', 18)  # Дата/время
        worksheet.set_column('B:B', 25)  # Пользователь
        worksheet.set_column('C:C', 15)  # Общая длительность
        worksheet.set_column('D:D', 15)  # Активное время
        worksheet.set_column('E:E', 12)  # Валидных запросов
        worksheet.set_column('F:F', 12)  # Всего действий
        worksheet.set_column('G:G', 60)  # Причины длительности
        worksheet.set_column('H:H', 15)  # Статус
        
        row = 0
        
        # Заголовок
        worksheet.merge_range(row, 0, row, 7,
                            '🔍 ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О СЕССИЯХ',
                            formats['main_title'])
        worksheet.set_row(row, 30)
        row += 1
        
        # Описание колонок
        worksheet.merge_range(row, 0, row, 7,
                            'Активное время = между первым и последним запросом | Общая длительность = включает время на изучение материала',
                            formats['subtitle'])
        row += 1
        
        # Получаем данные
        sessions_data = await self.db.get_detailed_session_report(days)
        
        if not sessions_data:
            worksheet.write(row, 0, 'Нет данных о сессиях', formats['metric_label'])
            return
        
        # Заголовки таблицы
        headers = [
            'Начало сессии',
            'Пользователь',
            'Общая длительность (мин)',
            'Активное время (мин)',
            'Валидных запросов',
            'Всего действий',
            'Анализ и причины',
            'Статус'
        ]
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        row += 1
        
        # Данные по сессиям
        for session in sessions_data[:500]:  # Ограничиваем до 500 сессий
            # Дата начала
            start_time = session.get('session_start', '')
            if start_time:
                dt = datetime.fromisoformat(start_time)
                start_str = dt.strftime('%d.%m.%Y %H:%M')
            else:
                start_str = 'Неизвестно'
            worksheet.write(row, 0, start_str, formats['cell_data'])
            
            # Пользователь
            user_name = session.get('user_name', 'Неизвестный')
            client_code = session.get('client_code', '')
            user_info = f"{user_name}"
            if client_code:
                user_info += f" ({client_code})"
            worksheet.write(row, 1, user_info, formats['cell_data'])
            
            # Общая длительность
            duration = session.get('duration_minutes', 0)
            worksheet.write(row, 2, duration, formats['cell_decimal'])
            
            # Активное время (между первым и последним запросом)
            active_time = session.get('active_time_minutes', 0)
            worksheet.write(row, 3, active_time, formats['cell_decimal'])
            
            # Валидных запросов (из request_metrics)
            valid_requests = session.get('valid_requests', 0)
            worksheet.write(row, 4, valid_requests, formats['cell_number'])
            
            # Всего действий (включая навигацию)
            total_actions = session.get('total_actions', 0)
            worksheet.write(row, 5, total_actions, formats['cell_number'])
            
            # Причины и анализ
            reasons = session.get('analysis_reasons', [])
            
            # Добавляем информацию о разнице времени
            reading_time = duration - active_time
            analysis_text = f"Время на чтение: {reading_time:.1f} мин\n"
            analysis_text += f"Навигация: {session.get('navigation_actions', 0)} действий\n\n"
            analysis_text += '\n'.join(reasons[:4])  # Показываем до 4 причин
            
            worksheet.write(row, 6, analysis_text, formats['cell_data'])
            
            # Статус
            if duration >= 30:
                status = '🔴 Очень длинная'
            elif duration >= 10:
                status = '⏰ Длинная'
            elif duration >= 2:
                status = '✅ Нормальная'
            else:
                status = '⚡ Быстрая'
            worksheet.write(row, 7, status, formats['cell_data'])
            
            row += 1
    
    async def _create_session_analysis_sheet(self, worksheet, formats, days):
        """Создает лист с анализом проблемных сессий"""
        # Настройка колонок
        worksheet.set_column('A:A', 25)
        worksheet.set_column('B:B', 20)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 15)
        worksheet.set_column('E:E', 50)
        worksheet.set_column('F:F', 50)
        
        row = 0
        
        # Заголовок
        worksheet.merge_range(row, 0, row, 5,
                            '⚠️ АНАЛИЗ ПРОБЛЕМНЫХ СЕССИЙ (> 30 минут)',
                            formats['main_title'])
        worksheet.set_row(row, 30)
        row += 2
        
        # Получаем данные
        sessions_data = await self.db.get_detailed_session_report(days)
        
        # Фильтруем только длинные сессии (> 30 минут)
        long_sessions = [s for s in sessions_data if s.get('duration_minutes', 0) > 30]
        
        if not long_sessions:
            worksheet.merge_range(row, 0, row, 5,
                                '✅ Проблемных сессий не обнаружено!',
                                formats['subsection_header'])
            row += 2
            worksheet.write(row, 0, 'Все сессии имеют нормальную длительность (< 30 минут)', formats['metric_label'])
            return
        
        # === СВОДКА ПО ПРОБЛЕМАМ ===
        worksheet.merge_range(row, 0, row, 5,
                            '📊 СВОДКА ПО ПРОБЛЕМНЫМ СЕССИЯМ',
                            formats['section_header'])
        row += 1
        
        worksheet.write(row, 0, '🔴 Количество проблемных сессий', formats['metric_label'])
        worksheet.write(row, 1, len(long_sessions), formats['metric_value'])
        worksheet.write(row, 2, f'{len(long_sessions) / len(sessions_data) * 100:.1f}% от всех сессий', formats['cell_data'])
        row += 1
        
        avg_duration = sum(s['duration_minutes'] for s in long_sessions) / len(long_sessions)
        worksheet.write(row, 0, '⏰ Средняя длительность проблемных', formats['metric_label'])
        worksheet.write(row, 1, avg_duration, formats['metric_decimal'])
        worksheet.write(row, 2, 'минут', formats['metric_value'])
        row += 1
        
        # Средние показатели проблемных сессий
        avg_valid = sum(s.get('valid_requests', 0) for s in long_sessions) / len(long_sessions)
        avg_actions = sum(s.get('total_actions', 0) for s in long_sessions) / len(long_sessions)
        
        worksheet.write(row, 0, '📊 Среднее валидных запросов', formats['metric_label'])
        worksheet.write(row, 1, avg_valid, formats['metric_decimal'])
        row += 1
        
        worksheet.write(row, 0, '🔘 Среднее всех действий', formats['metric_label'])
        worksheet.write(row, 1, avg_actions, formats['metric_decimal'])
        row += 2
        
        # === ДЕТАЛИ ПРОБЛЕМНЫХ СЕССИЙ ===
        worksheet.merge_range(row, 0, row, 5,
                            '🔍 ТОП-50 САМЫХ ДЛИННЫХ СЕССИЙ',
                            formats['section_header'])
        row += 1
        
        # Заголовки
        headers = [
            'Пользователь',
            'Длительность',
            'Активное время',
            'Валидных запросов',
            'Анализ причин',
            'Рекомендации'
        ]
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, formats['table_header'])
        row += 1
        
        # Сортируем по длительности (самые длинные первыми)
        long_sessions_sorted = sorted(long_sessions, key=lambda x: x.get('duration_minutes', 0), reverse=True)
        
        for session in long_sessions_sorted[:50]:  # Топ-50 самых длинных
            user_info = f"{session.get('user_name', 'Неизвестный')}"
            if session.get('client_code'):
                user_info += f"\n({session['client_code']})"
            worksheet.write(row, 0, user_info, formats['cell_data'])
            
            duration = session.get('duration_minutes', 0)
            duration_text = f"{duration:.1f} мин\n({duration/60:.1f} ч)"
            worksheet.write(row, 1, duration_text, formats['cell_data'])
            
            active_time = session.get('active_time_minutes', 0)
            active_text = f"{active_time:.1f} мин\n({(duration - active_time):.1f} мин на чтение)"
            worksheet.write(row, 2, active_text, formats['cell_data'])
            
            valid_requests = session.get('valid_requests', 0)
            total_actions = session.get('total_actions', 0)
            requests_text = f"{valid_requests} валидных\n{total_actions} всего действий"
            worksheet.write(row, 3, requests_text, formats['cell_data'])
            
            reasons = session.get('analysis_reasons', [])
            reasons_text = '\n'.join(reasons)
            worksheet.write(row, 4, reasons_text, formats['cell_data'])
            
            # Рекомендуемые действия на основе анализа
            actions = []
            reading_time = duration - active_time
            
            if reading_time > 10:
                actions.append(f'📖 Пользователь долго изучал материал ({reading_time:.1f} мин)')
                actions.append('→ Это нормально, информация полезна')
            
            if session.get('navigation_actions', 0) > valid_requests * 2:
                nav_count = session.get('navigation_actions', 0)
                actions.append(f'🔘 Много навигации ({nav_count} vs {valid_requests} запросов)')
                actions.append('→ Возможно, сложно найти нужную функцию')
            
            if valid_requests == 0:
                actions.append('⚠️ Только навигация, нет запросов')
                actions.append('→ Пользователь не нашел что искал или просто смотрел')
            
            pauses = session.get('pauses', [])
            if pauses:
                max_pause = max(p['pause_minutes'] for p in pauses)
                if max_pause > 10:
                    actions.append(f'⏸️ Длинная пауза: {max_pause:.1f} мин')
                    actions.append('→ Возможно отвлекся или думал над задачей')
            
            if not actions:
                actions.append('✅ Активная работа с ботом')
                actions.append('→ Нормальное использование')
            
            worksheet.write(row, 5, '\n'.join(actions), formats['cell_data'])
            row += 1
    
    async def _create_recommendations_sheet(self, worksheet, formats, days):
        """Создает лист с рекомендациями"""
        # Настройка колонок
        worksheet.set_column('A:A', 60)
        worksheet.set_column('B:B', 80)
        
        row = 0
        
        # Заголовок
        worksheet.merge_range(row, 0, row, 1,
                            '💡 РЕКОМЕНДАЦИИ ПО ОПТИМИЗАЦИИ',
                            formats['main_title'])
        worksheet.set_row(row, 30)
        row += 2
        
        # Получаем данные
        sessions_data = await self.db.get_detailed_session_report(days)
        
        # Анализируем данные для рекомендаций
        long_sessions = [s for s in sessions_data if s.get('duration_minutes', 0) > 30]
        avg_duration = sum(s['duration_minutes'] for s in sessions_data) / len(sessions_data) if sessions_data else 0
        
        # === ОБЩИЕ РЕКОМЕНДАЦИИ ===
        worksheet.merge_range(row, 0, row, 1,
                            '🎯 ОБЩИЕ РЕКОМЕНДАЦИИ',
                            formats['section_header'])
        row += 1
        
        recommendations = [
            {
                'title': '1️⃣ Оптимизация времени сессий',
                'desc': 'Текущая средняя длительность сессии: {:.1f} минут.\n\n'
                        'Рекомендации:\n'
                        '• Если время > 10 минут: добавьте быстрые подсказки и FAQ\n'
                        '• Если время > 30 минут: проверьте, не возникают ли трудности у пользователей\n'
                        '• Оптимальное время сессии: 3-7 минут'.format(avg_duration)
            },
            {
                'title': '2️⃣ Анализ пауз между запросами',
                'desc': 'Длинные паузы могут означать:\n'
                        '• Пользователь изучает предоставленную информацию (это хорошо)\n'
                        '• Пользователь испытывает трудности с интерфейсом (требует улучшения)\n'
                        '• Пользователь отвлекся (нормально для рабочего процесса)\n\n'
                        'Действие: Проверьте, насколько понятны ответы бота'
            },
            {
                'title': '3️⃣ Мониторинг проблемных сессий',
                'desc': f'Обнаружено {len(long_sessions)} сессий длительностью > 30 минут.\n\n'
                        'Рекомендуется:\n'
                        '• Проанализировать причины запредельного времени\n'
                        '• Связаться с пользователями, у которых возникли проблемы\n'
                        '• Оптимизировать процессы, вызывающие длительное ожидание'
            },
            {
                'title': '4️⃣ Улучшение пользовательского опыта',
                'desc': 'Для сокращения времени сессий:\n'
                        '• Добавьте быстрый доступ к часто используемым функциям\n'
                        '• Улучшите поиск и навигацию\n'
                        '• Предоставляйте структурированные ответы\n'
                        '• Добавьте возможность сохранения избранного'
            }
        ]
        
        for rec in recommendations:
            worksheet.write(row, 0, rec['title'], formats['subsection_header'])
            row += 1
            worksheet.write(row, 0, rec['desc'], formats['cell_data'])
            row += 2
        
        # === МЕТРИКИ ДЛЯ ОТСЛЕЖИВАНИЯ ===
        worksheet.merge_range(row, 0, row, 1,
                            '📊 КЛЮЧЕВЫЕ МЕТРИКИ ДЛЯ ОТСЛЕЖИВАНИЯ',
                            formats['section_header'])
        row += 1
        
        metrics_to_track = [
            '✅ Средняя длительность сессии (целевое значение: 3-7 минут)',
            '✅ Процент сессий > 30 минут (целевое значение: < 5%)',
            '✅ Среднее количество запросов в сессии (целевое значение: 3-8)',
            '✅ Процент пользователей с проблемными сессиями (целевое значение: < 10%)'
        ]
        
        for metric in metrics_to_track:
            worksheet.write(row, 0, metric, formats['metric_label'])
            row += 1
