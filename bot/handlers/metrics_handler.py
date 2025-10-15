"""
Обработчики для просмотра метрик администратором
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import html
from datetime import datetime, timedelta

from src.database.db_init import db
from bot.keyboards import get_admin_menu_kb

metrics_router = Router()


class MetricsStates(StatesGroup):
    """Состояния для работы с метриками"""
    viewing_metrics = State()
    selecting_period = State()


def get_metrics_main_kb():
    """Главное меню метрик"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="👥 Клиентские метрики")],
        [KeyboardButton(text="⚙️ Технические метрики")],
        [KeyboardButton(text="🎯 Метрики качества")],
        [KeyboardButton(text="📊 Полный отчет")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_period_selection_kb():
    """Клавиатура выбора периода"""
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = [
        [KeyboardButton(text="📅 За сегодня")],
        [KeyboardButton(text="📅 За 7 дней"), KeyboardButton(text="📅 За 30 дней")],
        [KeyboardButton(text="📅 За всё время")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


@metrics_router.message(F.text == "📊 Метрики системы")
async def metrics_menu(message: Message, state: FSMContext):
    """Главное меню метрик"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user or user['role'] != 'admin':
        await message.answer("У вас нет доступа к этой функции.")
        return
    
    await message.answer(
        "📊 <b>Система метрик</b>\n\n"
        "Выберите категорию метрик для просмотра:",
        parse_mode="HTML",
        reply_markup=get_metrics_main_kb()
    )
    await state.set_state(MetricsStates.viewing_metrics)


@metrics_router.message(MetricsStates.viewing_metrics, F.text == "👥 Клиентские метрики")
async def show_client_metrics(message: Message, state: FSMContext):
    """Показывает клиентские метрики"""
    loading_msg = await message.answer("⏳ Загружаю клиентские метрики...")
    
    try:
        # Обновляем метрики
        await db.update_daily_metrics()
        
        # Получаем DAU за 30 дней
        dau_data = await db.get_dau_metrics(days=30)
        
        # Получаем retention
        retention = await db.get_retention_metrics()
        
        # Получаем метрики сессий
        sessions = await db.get_session_metrics(days=7)
        
        # Формируем ответ
        response = "👥 <b>КЛИЕНТСКИЕ МЕТРИКИ</b>\n\n"
        
        # DAU
        response += "📈 <b>Daily Active Users (DAU)</b>\n"
        if dau_data and len(dau_data) > 0:
            today_dau = dau_data[0].get('dau', 0) if dau_data else 0
            
            week_data = dau_data[:7]
            week_dau = sum(day.get('dau', 0) for day in week_data) / len(week_data) if week_data else 0
            
            month_dau = sum(day.get('dau', 0) for day in dau_data) / len(dau_data) if dau_data else 0
            
            response += f"• Сегодня: <b>{today_dau}</b> чел.\n"
            response += f"• Среднее за 7 дней: <b>{week_dau:.1f}</b> чел.\n"
            response += f"• Среднее за 30 дней: <b>{month_dau:.1f}</b> чел.\n\n"
        else:
            response += "• Нет данных (начните использовать бота для накопления статистики)\n\n"
        
        # Возвратность
        response += "🔄 <b>Возвратность пользователей</b>\n"
        if retention and retention.get('today_users', 0) > 0:
            response += f"• За 1 день: <b>{retention.get('retention_1d', 0):.1f}%</b> ({retention.get('returned_1d', 0)} чел.)\n"
            response += f"• За 7 дней: <b>{retention.get('retention_7d', 0):.1f}%</b> ({retention.get('returned_7d', 0)} чел.)\n"
            response += f"• За 30 дней: <b>{retention.get('retention_30d', 0):.1f}%</b> ({retention.get('returned_30d', 0)} чел.)\n\n"
        else:
            response += "• Недостаточно данных (нужно минимум 2 дня активности)\n\n"
        
        # Сессии
        response += "⏱ <b>Метрики сессий (за 7 дней)</b>\n"
        if sessions and sessions.get('total_sessions', 0) > 0:
            avg_dur = sessions.get('avg_duration_minutes')
            avg_req = sessions.get('avg_requests_per_session')
            
            response += f"• Всего сессий: <b>{sessions.get('total_sessions', 0)}</b>\n"
            response += f"• Средняя длительность: <b>{avg_dur if avg_dur else 0:.1f}</b> мин.\n"
            response += f"• Запросов на сессию: <b>{avg_req if avg_req else 0:.1f}</b>\n"
            response += f"• Уникальных пользователей: <b>{sessions.get('unique_users', 0)}</b>\n"
        else:
            response += "• Нет завершенных сессий (сессии завершаются через 3 часа неактивности)\n"
        
        await loading_msg.delete()
        await message.answer(response, parse_mode="HTML", reply_markup=get_metrics_main_kb())
        
    except Exception as e:
        await loading_msg.delete()
        await message.answer(
            f"❌ Ошибка при загрузке метрик: {str(e)}",
            reply_markup=get_metrics_main_kb()
        )


@metrics_router.message(MetricsStates.viewing_metrics, F.text == "⚙️ Технические метрики")
async def show_technical_metrics(message: Message, state: FSMContext):
    """Показывает технические метрики"""
    loading_msg = await message.answer("⏳ Загружаю технические метрики...")
    
    try:
        # Обновляем метрики
        await db.update_system_metrics()
        
        # Получаем метрики производительности
        perf_metrics = await db.get_metrics_summary(days=7)
        
        # Получаем системные метрики
        system_metrics = await db._get_latest_system_metrics()
        
        response = "⚙️ <b>ТЕХНИЧЕСКИЕ МЕТРИКИ</b>\n\n"
        
        # Производительность
        if perf_metrics and perf_metrics.get('overall'):
            overall = perf_metrics['overall']
            response += "🚀 <b>Производительность (за 7 дней)</b>\n"
            response += f"• Всего запросов: <b>{overall.get('total_requests', 0)}</b>\n"
            response += f"• Успешных: <b>{overall.get('successful_requests', 0)}</b>\n"
            response += f"• Неудачных: <b>{overall.get('failed_requests', 0)}</b>\n"
            response += f"• Среднее время ответа: <b>{overall.get('avg_response_time', 0):.2f}</b> сек.\n"
            response += f"• Макс. время ответа: <b>{overall.get('max_response_time', 0):.2f}</b> сек.\n"
            response += f"• Средний DAU: <b>{overall.get('avg_daily_users', 0):.1f}</b> чел.\n\n"
        
        # Системные ресурсы
        response += "💻 <b>Системные ресурсы (сегодня)</b>\n"
        if system_metrics:
            latest = system_metrics[0]
            response += f"• CPU: <b>{latest.get('cpu_usage', 0):.1f}%</b>\n"
            response += f"• Память: <b>{latest.get('memory_usage', 0):.1f}%</b>\n"
            response += f"• Диск: <b>{latest.get('disk_usage', 0):.1f}%</b>\n"
            response += f"• Активных сессий: <b>{latest.get('active_sessions', 0)}</b>\n"
            response += f"• Ошибок за день: <b>{latest.get('error_count', 0)}</b>\n\n"
        else:
            response += "• Нет данных\n\n"
        
        # Нагрузка vs DAU
        if perf_metrics and perf_metrics.get('overall'):
            overall = perf_metrics['overall']
            dau = overall.get('avg_daily_users', 1)
            avg_time = overall.get('avg_response_time', 0)
            
            response += "📊 <b>Зависимость времени от нагрузки</b>\n"
            response += f"• Время/пользователь: <b>{avg_time / max(dau, 1):.3f}</b> сек.\n"
            
            # Оценка состояния
            if avg_time < 2.0:
                status = "✅ Отлично"
            elif avg_time < 5.0:
                status = "⚠️ Нормально"
            else:
                status = "🔴 Требует внимания"
            
            response += f"• Статус: {status}\n"
        
        await loading_msg.delete()
        await message.answer(response, parse_mode="HTML", reply_markup=get_metrics_main_kb())
        
    except Exception as e:
        await loading_msg.delete()
        await message.answer(
            f"❌ Ошибка при загрузке метрик: {str(e)}",
            reply_markup=get_metrics_main_kb()
        )


@metrics_router.message(MetricsStates.viewing_metrics, F.text == "🎯 Метрики качества")
async def show_quality_metrics(message: Message, state: FSMContext):
    """Показывает метрики качества работы бота"""
    loading_msg = await message.answer("⏳ Загружаю метрики качества...")
    
    try:
        # Обновляем метрики
        await db.update_quality_metrics()
        
        # Получаем метрики качества
        quality = await db.get_quality_metrics_summary(days=7)
        
        # Получаем детальные метрики по типам
        detailed = await db.get_metrics_summary(days=7)
        
        response = "🎯 <b>МЕТРИКИ КАЧЕСТВА (за 7 дней)</b>\n\n"
        
        if quality:
            total = quality.get('total', 0)
            correct = quality.get('correct', 0)
            
            response += "📊 <b>Общая эффективность</b>\n"
            response += f"• Всего запросов: <b>{total}</b>\n"
            response += f"• Обработано корректно: <b>{correct}</b> ({quality.get('correct_percentage', 0):.1f}%)\n"
            response += f"• Ошибки: <b>{quality.get('incorrect', 0)}</b> ({quality.get('incorrect_percentage', 0):.1f}%)\n"
            response += f"• Без ответа: <b>{quality.get('no_answer', 0)}</b> ({quality.get('no_answer_percentage', 0):.1f}%)\n\n"
            
            # Целевой показатель
            target = 70.0
            actual = quality.get('correct_percentage', 0)
            
            if actual >= target:
                status = f"✅ Цель достигнута ({actual:.1f}% ≥ {target}%)"
            else:
                diff = target - actual
                status = f"⚠️ До цели: {diff:.1f}% (текущий: {actual:.1f}%)"
            
            response += f"🎯 <b>Целевой показатель:</b> {status}\n\n"
            
            # Типы запросов
            response += "📋 <b>Аналитика по типам запросов</b>\n"
            response += f"• Поиск по коду: <b>{quality.get('code_searches', 0)}</b>\n"
            response += f"• Поиск по названию: <b>{quality.get('name_searches', 0)}</b>\n"
            response += f"• Общие вопросы: <b>{quality.get('general_questions', 0)}</b>\n\n"
        else:
            response += "• Нет данных за период\n\n"
        
        # Топ пользователей по активности
        if detailed and detailed.get('top_users'):
            response += "👑 <b>Топ-5 активных пользователей</b>\n"
            for i, user in enumerate(detailed['top_users'][:5], 1):
                name = user.get('name', 'Неизвестный')
                count = user.get('request_count', 0)
                success_rate = (user.get('successful', 0) / count * 100) if count > 0 else 0
                
                response += f"{i}. {html.escape(name)}: <b>{count}</b> запросов ({success_rate:.0f}% успех)\n"
        
        await loading_msg.delete()
        await message.answer(response, parse_mode="HTML", reply_markup=get_metrics_main_kb())
        
    except Exception as e:
        await loading_msg.delete()
        await message.answer(
            f"❌ Ошибка при загрузке метрик: {str(e)}",
            reply_markup=get_metrics_main_kb()
        )


@metrics_router.message(MetricsStates.viewing_metrics, F.text == "📊 Полный отчет")
async def show_comprehensive_metrics(message: Message, state: FSMContext):
    """Показывает полный отчет по всем метрикам в новом формате"""
    loading_msg = await message.answer("⏳ Формирую полный отчет...")
    
    try:
        days = 30  # По умолчанию 30 дней
        
        # Обновляем все метрики
        await db.update_daily_metrics()
        await db.update_quality_metrics()
        await db.update_system_metrics()
        
        # Получаем полные метрики
        metrics = await db.get_comprehensive_metrics(days=days)
        
        if not metrics:
            await loading_msg.delete()
            await message.answer(
                "❌ Не удалось загрузить метрики",
                reply_markup=get_metrics_main_kb()
            )
            return
        
        # Получаем средний рейтинг
        avg_rating = await db.get_average_user_rating(days=days)
        
        # ==================== СВОДКА МЕТРИК ====================
        response = f"📊 <b>СВОДКА МЕТРИК ЗА {days} ДНЕЙ</b>\n"
        response += f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        
        # ==================== КЛИЕНТСКИЕ МЕТРИКИ ====================
        response += "👥 <b>КЛИЕНТСКИЕ МЕТРИКИ</b>\n\n"
        
        client = metrics.get('client_metrics', {})
        dau_list = client.get('dau', [])
        retention = client.get('retention', {})
        sessions = client.get('sessions', {})
        
        # Средний DAU
        if dau_list and len(dau_list) > 0:
            avg_dau = sum(d.get('dau', 0) for d in dau_list) / len(dau_list)
            response += f"• Средний DAU: <b>{avg_dau:.1f}</b>\n"
        else:
            response += "• Средний DAU: <b>н/д</b>\n"
        
        # Retention
        if retention and retention.get('today_users', 0) > 0:
            response += f"• Retention 1 день: <b>{retention.get('retention_1d', 0):.1f}%</b>\n"
            response += f"• Retention 7 дней: <b>{retention.get('retention_7d', 0):.1f}%</b>\n"
            response += f"• Retention 30 дней: <b>{retention.get('retention_30d', 0):.1f}%</b>\n"
        else:
            response += "• Retention 1 день: <b>н/д</b>\n"
            response += "• Retention 7 дней: <b>н/д</b>\n"
            response += "• Retention 30 дней: <b>н/д</b>\n"
        
        # Средняя длительность сессии
        if sessions and sessions.get('total_sessions', 0) > 0:
            avg_dur = sessions.get('avg_duration_minutes', 0)
            response += f"• Средняя длительность сессии: <b>{avg_dur:.2f}</b> мин\n\n"
        else:
            response += "• Средняя длительность сессии: <b>н/д</b>\n\n"
        
        # Получаем данные по обращениям
        tech = metrics.get('technical_metrics', {})
        perf = tech.get('response_time', {})
        overall = perf.get('overall', {}) if perf else {}
        
        total_requests = overall.get('total_requests', 0)
        successful_requests = overall.get('successful_requests', 0)
        
        # Общее количество обращений и среднее
        response += "<b>Общее количество обращений:</b>\n"
        
        # За разные периоды (получаем из метрик)
        if dau_list:
            # 1 день
            today_req = dau_list[0].get('total_requests', 0) if dau_list else 0
            response += f"  • 1 день: <b>{today_req}</b>\n"
            
            # 7 дней
            week_req = sum(d.get('total_requests', 0) for d in dau_list[:7])
            response += f"  • 7 дней: <b>{week_req}</b>\n"
            
            # 30 дней
            month_req = sum(d.get('total_requests', 0) for d in dau_list)
            response += f"  • {days} дней: <b>{month_req}</b>\n\n"
        else:
            response += f"  • Всего за период: <b>{total_requests}</b>\n\n"
        
        response += "<b>Среднее количество обращений:</b>\n"
        if dau_list:
            today_dau = dau_list[0].get('dau', 1) if dau_list else 1
            week_dau = sum(d.get('dau', 0) for d in dau_list[:7]) / min(7, len(dau_list[:7]))
            month_dau = avg_dau if dau_list else 1
            
            response += f"  • 1 день: <b>{today_req / max(today_dau, 1):.1f}</b>\n"
            response += f"  • 7 дней: <b>{week_req / max(week_dau, 1) / 7:.1f}</b>\n"
            response += f"  • {days} дней: <b>{month_req / max(month_dau, 1) / days:.1f}</b>\n\n"
        else:
            response += "  • н/д\n\n"
        
        # Всего запросов и успешных
        response += f"• Всего запросов: <b>{total_requests}</b>\n"
        response += f"• Успешных запросов: <b>{successful_requests}</b>\n"
        
        # Коэффициент точности
        accuracy = (successful_requests / total_requests * 100) if total_requests > 0 else 0
        response += f"• Коэффициент точности: <b>{accuracy:.1f}%</b>\n"
        
        # Средний рейтинг
        response += f"• Средний рейтинг: <b>{avg_rating:.2f}/5</b> ⭐\n\n"
        
        # ==================== ТЕХНИЧЕСКИЕ МЕТРИКИ ====================
        response += "⚙️ <b>ТЕХНИЧЕСКИЕ МЕТРИКИ</b>\n\n"
        
        if overall:
            response += f"• Среднее время ответа: <b>{overall.get('avg_response_time', 0):.2f}</b> сек\n"
            response += f"• Макс. время ответа: <b>{overall.get('max_response_time', 0):.2f}</b> сек\n\n"
        else:
            response += "• Среднее время ответа: <b>н/д</b>\n"
            response += "• Макс. время ответа: <b>н/д</b>\n\n"
        
        # ==================== МЕТРИКИ КАЧЕСТВА ====================
        response += "🎯 <b>МЕТРИКИ КАЧЕСТВА</b>\n\n"
        
        quality = metrics.get('quality_metrics', {})
        if quality:
            total = quality.get('total', 0)
            correct = quality.get('correct', 0)
            incorrect = quality.get('incorrect', 0)
            no_answer = quality.get('no_answer', 0)
            
            response += f"• Всего вопросов: <b>{total}</b>\n"
            response += f"• Всего корректных ответов: <b>{correct}</b>\n"
            response += f"• Ошибок: <b>{incorrect}</b>\n"
            response += f"• Без ответа: <b>{no_answer}</b>\n\n"
            
            response += f"• Всего запросов: <b>{total}</b>\n"
            response += f"• Корректных ответов: <b>{quality.get('correct_percentage', 0):.1f}%</b>\n"
            response += f"• Ошибок: <b>{quality.get('incorrect_percentage', 0):.1f}%</b>\n"
            response += f"• Без ответа: <b>{quality.get('no_answer_percentage', 0):.1f}%</b>\n"
        else:
            response += "• Нет данных\n"
        
        await loading_msg.delete()
        await message.answer(response, parse_mode="HTML", reply_markup=get_metrics_main_kb())
        
    except Exception as e:
        await loading_msg.delete()
        await message.answer(
            f"❌ Ошибка при загрузке метрик: {str(e)}",
            reply_markup=get_metrics_main_kb()
        )


@metrics_router.message(MetricsStates.viewing_metrics, F.text == "🔙 Назад")
async def back_from_metrics(message: Message, state: FSMContext):
    """Возврат в главное меню админа"""
    await state.clear()
    await message.answer(
        "Главное меню администратора",
        reply_markup=get_admin_menu_kb()
    )