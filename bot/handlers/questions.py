from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from langchain.schema import SystemMessage, HumanMessage, Document
import asyncio
import html
from typing import Optional, Dict, List, Tuple
from fuzzywuzzy import fuzz
from datetime import datetime
import re

from src.database.db_init import db
from src.data_vectorization import DataProcessor
from models.models_init import Google_Gemini_2_5_Flash_Lite as llm
from bot.handlers.utils import (
    fix_bold, 
    safe_delete_message, 
    create_test_link, 
    is_test_code_pattern, 
    normalize_test_code
    )
from bot.handlers.sending_style import (
    animate_loading,
    format_test_data, 
    format_test_info, 
    get_user_first_name, 
    get_time_based_farewell,
    format_similar_tests_with_links
)
from bot.handlers.score_test import (
    select_best_match,
    fuzzy_test_search, 
    smart_test_search
)
from bot.keyboards import (
    get_menu_by_role,
    get_dialog_kb,
    get_back_to_menu_kb,
    get_search_type_kb,
)

from bot.handlers.query_preprocessing import (
    expand_query_with_abbreviations
)

# LOADING_GIF_ID = (
#     "CgACAgIAAxkBAAMIaGr_qy1Wxaw2VrBrm3dwOAkYji4AAu54AAKmqHlJAtZWBziZvaA2BA"
# )
LOADING_GIF_ID = "CgACAgIAAxkBAAIBFGiBcXtGY7OZvr3-L1dZIBRNqSztAALueAACpqh5Scn4VmIRb4UjNgQ"
# LOADING_GIF_ID = "CgACAgIAAxkBAAMMaHSq3vqxq2RuMMj-DIMvldgDjfkAAu54AAKmqHlJCNcCjeoHRJI2BA"

questions_router = Router()


class TestCallback:
    @staticmethod
    def pack(action: str, test_code: str) -> str:
        return f"{action}:{test_code}"

    @staticmethod
    def unpack(callback_data: str) -> Tuple[str, str]:
        parts = callback_data.split(":", 1)
        return parts[0] if len(parts) > 0 else "", parts[1] if len(parts) > 1 else ""


class QuestionStates(StatesGroup):
    waiting_for_search_type = State()
    waiting_for_code = State()
    waiting_for_name = State()
    in_dialog = State()
    processing = State()
    clarifying_search = State()


# Структура для хранения контекста поиска
class SearchContext:
    def __init__(self):
        self.original_query = ""
        self.search_attempts = []
        self.candidate_tests = []
        self.clarification_step = 0
        self.filters = {}


@questions_router.callback_query(F.data.startswith("show_container_photos:"))
async def handle_show_container_photos_callback(callback: CallbackQuery):
    """Обработчик для показа фото контейнеров"""
    await callback.answer()

    # Извлекаем код теста
    test_code = callback.data.split(":", 1)[1]

    try:
        # Ищем тест в базе
        processor = DataProcessor()
        processor.load_vector_store()

        results = processor.search_test(filter_dict={"test_code": test_code})

        if not results:
            await callback.message.answer("❌ Тест не найден")
            return

        doc = results[0][0] if isinstance(results[0], tuple) else results[0]
        test_data = format_test_data(doc.metadata)

        container_type_raw = str(test_data.get("container_type", "")).strip()

        # Убираем кавычки и нормализуем
        container_type_raw = container_type_raw.replace('"', "").replace("\n", " ")
        container_type_raw = " ".join(container_type_raw.split())

        # Получаем все типы контейнеров
        if "*I*" in container_type_raw:
            container_types = [ct.strip() for ct in container_type_raw.split("*I*")]
        else:
            container_types = [container_type_raw]

        # Собираем все фото контейнеров
        found_photos = []

        for ct in container_types:
            # Нормализуем каждый тип
            ct_normalized = " ".join(word.capitalize() for word in ct.split())

            photo_data = await db.get_container_photo(ct_normalized)
            if photo_data:
                found_photos.append(photo_data["file_id"])

        # Если есть фото - отправляем
        if found_photos:
            message_ids = []

            # Отправляем все фото по отдельности
            for i, file_id in enumerate(found_photos):
                is_last = i == len(found_photos) - 1

                if is_last:
                    # Последнее фото с кнопкой
                    hide_keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="🙈 Скрыть фото",
                                    callback_data=f"hide_photos:{test_code}:placeholder",
                                )
                            ]
                        ]
                    )

                    sent_msg = await callback.message.answer_photo(
                        photo=file_id, reply_markup=hide_keyboard
                    )
                else:
                    # Остальные фото без кнопки
                    sent_msg = await callback.message.answer_photo(photo=file_id)

                message_ids.append(sent_msg.message_id)

            # Обновляем callback_data последнего сообщения со всеми ID
            if message_ids:
                hide_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🙈 Скрыть фото",
                                callback_data=f"hide_photos:{test_code}:{','.join(map(str, message_ids))}",
                            )
                        ]
                    ]
                )

                # Редактируем кнопку последнего сообщения
                await callback.bot.edit_message_reply_markup(
                    chat_id=callback.message.chat.id,
                    message_id=message_ids[-1],
                    reply_markup=hide_keyboard,
                )

        else:
            await callback.message.answer("❌ Фото контейнеров не найдены в базе")

    except Exception as e:
        print(f"[ERROR] Failed to show container photos: {e}")
        await callback.message.answer("❌ Ошибка при загрузке фото")


@questions_router.callback_query(F.data.startswith("hide_photos:"))
async def handle_hide_photos_callback(callback: CallbackQuery):
    """Обработчик для скрытия фото контейнеров"""
    await callback.answer("Фото скрыты")

    try:
        # Парсим данные: hide_photos:test_code:photo_msg_ids
        parts = callback.data.split(":", 2)
        photo_msg_ids = [int(msg_id) for msg_id in parts[2].split(",")]

        # Удаляем все сообщения с фото (включая последнее с кнопкой)
        for msg_id in photo_msg_ids:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id, message_id=msg_id
                )
            except:
                pass

    except Exception as e:
        print(f"[ERROR] Failed to hide photos: {e}")
        await callback.answer("❌ Ошибка при скрытии фото", show_alert=True)


# Добавляем обработчик для одиночного фото
@questions_router.callback_query(F.data.startswith("hide_single:"))
async def handle_hide_single_photo(callback: CallbackQuery):
    """Обработчик для скрытия одиночного фото с кнопкой"""
    await callback.answer("Фото скрыто")

    try:
        # Удаляем сообщение с фото и кнопкой
        await callback.message.delete()
    except Exception as e:
        print(f"[ERROR] Failed to hide single photo: {e}")


@questions_router.callback_query(F.data.startswith("hide_photos:"))
async def handle_hide_photos_callback(callback: CallbackQuery):
    """Обработчик для скрытия фото контейнеров"""
    await callback.answer("Фото скрыты")  # Только всплывающее уведомление

    try:
        # Парсим данные: hide_photos:test_code:photo_msg_ids
        parts = callback.data.split(":", 2)
        photo_msg_ids = [int(msg_id) for msg_id in parts[2].split(",")]

        for msg_id in photo_msg_ids:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id, message_id=msg_id
                )
            except:
                pass

        try:
            await callback.message.delete()
        except:
            pass

    except Exception as e:
        print(f"[ERROR] Failed to hide photos: {e}")
        # Ошибку показываем только во всплывающем уведомлении
        await callback.answer("❌ Ошибка при скрытии фото", show_alert=True)


@questions_router.callback_query(F.data == "close_keyboard")
async def handle_close_keyboard(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)


# Также добавим обработчики для callback кнопок, которые могут быть не определены:
@questions_router.callback_query(F.data == "search_by_code")
async def handle_search_by_code_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "Введите код теста (например, AN5):", reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(QuestionStates.waiting_for_code)


@questions_router.callback_query(F.data == "search_by_name")
async def handle_search_by_name_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "Введите название или описание теста:", reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(QuestionStates.waiting_for_name)


# Обработчики
@questions_router.callback_query(F.data.startswith("show_test:"))
async def handle_show_test_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик для показа информации о тесте из inline кнопки."""
    action, test_code = TestCallback.unpack(callback.data)

    # Отвечаем на callback чтобы убрать "часики"
    await callback.answer()

    try:
        processor = DataProcessor()
        processor.load_vector_store()

        # Сначала пробуем точный поиск
        results = processor.search_test(filter_dict={"test_code": test_code})

        # Если не нашли - пробуем с нормализацией
        if not results:
            normalized_code = normalize_test_code(test_code)
            results = processor.search_test(filter_dict={"test_code": normalized_code})

        # Если не нашли - используем fuzzy поиск с высоким порогом
        if not results:
            print(
                f"[DEBUG] Test {test_code} not found with exact search. Trying fuzzy..."
            )
            fuzzy_results = await fuzzy_test_search(processor, test_code, threshold=85)

            if fuzzy_results:
                # Ищем точное совпадение среди fuzzy результатов
                for doc, score in fuzzy_results:
                    if doc.metadata.get("test_code", "").upper() == test_code.upper():
                        results = [(doc, score)]
                        print(
                            f"[DEBUG] Found exact match in fuzzy results: {doc.metadata.get('test_code')}"
                        )
                        break

                # Если точного не нашли - берем первый с высоким score
                if not results and fuzzy_results[0][1] >= 90:
                    results = [fuzzy_results[0]]
                    print(
                        f"[DEBUG] Using best fuzzy match: {fuzzy_results[0][0].metadata.get('test_code')} (score: {fuzzy_results[0][1]})"
                    )

        # Последняя попытка - текстовый поиск
        if not results:
            print(f"[DEBUG] Trying text search for {test_code}")
            text_results = processor.search_test(query=test_code, top_k=50)

            # Ищем точное совпадение кода
            for doc, score in text_results:
                doc_code = doc.metadata.get("test_code", "")
                # Проверяем точное совпадение с учетом регистра и пробелов
                if doc_code.strip().upper() == test_code.strip().upper():
                    results = [(doc, score)]
                    print(f"[DEBUG] Found via text search: {doc_code}")
                    break

        # Если все еще не нашли - используем smart_test_search
        if not results:
            result, found_variant, match_type = await smart_test_search(
                processor, test_code
            )
            if result:
                results = [result]
                print(
                    f"[DEBUG] Found via smart search: {found_variant} (type: {match_type})"
                )

        if not results:
            print(f"[ERROR] Test {test_code} not found after all attempts")
            await callback.message.answer(f"❌ Тест {test_code} не найден в базе данных")
            return

        doc = results[0][0] if isinstance(results[0], tuple) else results[0]
        test_data = format_test_data(doc.metadata)

        # Формируем полный ответ
        response = f"<b>Информация о выбранном тесте:</b>\n\n"
        response += format_test_info(test_data)

        # Обновляем статистику
        user_id = callback.from_user.id
        await db.add_search_history(
            user_id=user_id,
            search_query=f"Выбор из списка: {test_code}",
            found_test_code=test_data["test_code"],
            search_type="code",
            success=True,
        )
        await db.update_user_frequent_test(
            user_id=user_id,
            test_code=test_data["test_code"],
            test_name=test_data["test_name"],
        )

        # Обновляем связанные тесты
        data = await state.get_data()
        if (
            "last_viewed_test" in data
            and data["last_viewed_test"] != test_data["test_code"]
        ):
            await db.update_related_tests(
                user_id=user_id,
                test_code_1=data["last_viewed_test"],
                test_code_2=test_data["test_code"],
            )

        # Получаем связанные тесты из истории пользователя
        related_tests = await db.get_user_related_tests(user_id, test_data["test_code"])

        # Ищем похожие тесты для этого теста
        similar_tests = await fuzzy_test_search(
            processor, test_data["test_code"], threshold=40
        )

        # Фильтруем, чтобы не показывать сам тест
        similar_tests = [
            (d, s)
            for d, s in similar_tests
            if d.metadata.get("test_code") != test_data["test_code"]
        ]

        # Создаем клавиатуру если есть похожие или связанные
        reply_markup = None
        if related_tests or similar_tests:
            keyboard = []
            row = []

            # Сначала связанные из истории (приоритет)
            for related in related_tests[:4]:
                row.append(
                    InlineKeyboardButton(
                        text=f"⭐ {related['test_code']}",
                        callback_data=TestCallback.pack(
                            "show_test", related["test_code"]
                        ),
                    )
                )
                if len(row) >= 2:
                    keyboard.append(row)
                    row = []

            # Затем похожие
            for doc, _ in similar_tests[:4]:
                if len(keyboard) * 2 + len(row) >= 8:  # Максимум 8 кнопок
                    break
                code = doc.metadata.get("test_code")
                if not any(r["test_code"] == code for r in related_tests):
                    row.append(
                        InlineKeyboardButton(
                            text=code,
                            callback_data=TestCallback.pack("show_test", code),
                        )
                    )
                    if len(row) >= 2:
                        keyboard.append(row)
                        row = []

            if row:
                keyboard.append(row)

            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        # Отправляем информацию с фото ТОЛЬКО ОДИН РАЗ
        await send_test_info_with_photo(callback.message, test_data, response)

        # Если есть рекомендации - отправляем их отдельным сообщением
        if reply_markup:
            await callback.message.answer(
                "🎯 Рекомендуем также:", reply_markup=reply_markup
            )

        # Обновляем состояние с текущим тестом
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(
            current_test=test_data, last_viewed_test=test_data["test_code"]
        )

        # # Показываем клавиатуру для продолжения диалога
        # await callback.message.answer(
        #     "Можете задать вопрос об этом тесте или выбрать действие:",
        #     reply_markup=get_dialog_kb()
        # )

    except Exception as e:
        print(f"[ERROR] Callback handling failed: {e}")
        import traceback

        traceback.print_exc()
        await callback.message.answer("⚠️ Ошибка при загрузке информации о тесте")


@questions_router.callback_query(F.data.startswith("quick_test:"))
async def handle_quick_test_selection(callback: CallbackQuery, state: FSMContext):
    """Обработчик быстрого выбора теста из подсказок"""
    test_code = callback.data.split(":")[1]

    try:
        # Используем DataProcessor напрямую для поиска
        processor = DataProcessor()
        processor.load_vector_store()

        # Нормализуем код теста
        normalized_code = normalize_test_code(test_code)

        # Сначала пробуем точный поиск по нормализованному коду
        results = processor.search_test(filter_dict={"test_code": normalized_code})

        # Если не нашли - пробуем оригинальный код
        if not results:
            results = processor.search_test(filter_dict={"test_code": test_code})

        # Если не нашли - пробуем fuzzy поиск
        if not results:
            print(
                f"[DEBUG] Test {test_code} not found with filter. Trying fuzzy search..."
            )
            fuzzy_results = await fuzzy_test_search(processor, test_code, threshold=90)

            if fuzzy_results:
                # Берем первый результат с высоким score
                results = [fuzzy_results[0]]
                print(
                    f"[DEBUG] Found via fuzzy search: {results[0][0].metadata.get('test_code')}"
                )
            else:
                # Пробуем текстовый поиск
                print(f"[DEBUG] Trying text search for {test_code}")
                text_results = processor.search_test(query=test_code, top_k=10)

                # Фильтруем по точному совпадению кода
                for doc, score in text_results:
                    doc_code = doc.metadata.get("test_code", "")
                    if (
                        doc_code.upper() == test_code.upper()
                        or doc_code.upper() == normalized_code.upper()
                    ):
                        results = [(doc, score)]
                        print(f"[DEBUG] Found via text search: {doc_code}")
                        break

        if not results:
            # Последняя попытка - используем smart_test_search
            result, found_variant, match_type = await smart_test_search(
                processor, test_code
            )
            if result:
                results = [result]
                print(
                    f"[DEBUG] Found via smart search: {found_variant} (type: {match_type})"
                )

        if not results:
            print(f"[ERROR] Test {test_code} not found after all attempts")
            await callback.message.answer(f"❌ Тест {test_code} не найден в базе данных")
            await callback.answer()
            return

        doc = results[0][0] if isinstance(results[0], tuple) else results[0]
        test_data = format_test_data(doc.metadata)

        # Формируем ответ
        response = f"<b>Информация о выбранном тесте:</b>\n\n"
        response += format_test_info(test_data)

        # Обновляем статистику
        user_id = callback.from_user.id
        await db.add_search_history(
            user_id=user_id,
            search_query=f"Быстрый выбор: {test_code}",
            found_test_code=test_data["test_code"],
            search_type="code",
            success=True,
        )
        await db.update_user_frequent_test(
            user_id=user_id,
            test_code=test_data["test_code"],
            test_name=test_data["test_name"],
        )

        # Обновляем связанные тесты
        data = await state.get_data()
        if (
            "last_viewed_test" in data
            and data["last_viewed_test"] != test_data["test_code"]
        ):
            await db.update_related_tests(
                user_id=user_id,
                test_code_1=data["last_viewed_test"],
                test_code_2=test_data["test_code"],
            )

        # Получаем связанные тесты из истории пользователя
        related_tests = await db.get_user_related_tests(user_id, test_data["test_code"])

        # Ищем похожие тесты для этого теста
        similar_tests = await fuzzy_test_search(
            processor, test_data["test_code"], threshold=40
        )

        # Фильтруем, чтобы не показывать сам тест
        similar_tests = [
            (d, s)
            for d, s in similar_tests
            if d.metadata.get("test_code") != test_data["test_code"]
        ]

        # Создаем клавиатуру если есть похожие или связанные
        reply_markup = None
        if related_tests or similar_tests:
            keyboard = []
            row = []

            # Сначала связанные из истории (приоритет)
            for related in related_tests[:4]:
                row.append(
                    InlineKeyboardButton(
                        text=f"⭐ {related['test_code']}",
                        callback_data=TestCallback.pack(
                            "show_test", related["test_code"]
                        ),
                    )
                )
                if len(row) >= 2:
                    keyboard.append(row)
                    row = []

            # Затем похожие
            for doc, _ in similar_tests[:4]:
                if len(keyboard) * 2 + len(row) >= 8:  # Максимум 8 кнопок
                    break
                code = doc.metadata.get("test_code")
                if not any(r["test_code"] == code for r in related_tests):
                    row.append(
                        InlineKeyboardButton(
                            text=code,
                            callback_data=TestCallback.pack("show_test", code),
                        )
                    )
                    if len(row) >= 2:
                        keyboard.append(row)
                        row = []

            if row:
                keyboard.append(row)

            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

        # Отправляем информацию с фото ТОЛЬКО ОДИН РАЗ
        await send_test_info_with_photo(callback.message, test_data, response)

        # Если есть рекомендации - отправляем их отдельным сообщением
        if reply_markup:
            await callback.message.answer(
                "🎯 Рекомендуем также:", reply_markup=reply_markup
            )

        # Обновляем состояние с текущим тестом
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(
            current_test=test_data, last_viewed_test=test_data["test_code"]
        )

        # # Показываем клавиатуру для продолжения диалога
        # await callback.message.answer(
        #     "Можете задать вопрос об этом тесте или выбрать действие:",
        #     reply_markup=get_dialog_kb()
        # )

    except Exception as e:
        print(f"[ERROR] Quick test selection failed: {e}")
        import traceback

        traceback.print_exc()
        await callback.message.answer("⚠️ Ошибка при загрузке информации о тесте")

    await callback.answer()  # Закрываем уведомление о нажатии


@questions_router.callback_query(F.data == "ignore")
async def handle_ignore_callback(callback: CallbackQuery):
    """Обработчик для информационных кнопок"""
    await callback.answer()


@questions_router.message(F.text == "🔬 Задать вопрос ассистенту")
async def start_question(message: Message, state: FSMContext):
    """Начало диалога с ассистентом без выбора типа поиска."""
    user_id = message.from_user.id
    user = await db.get_user(user_id)

    if not user:
        await message.answer(
            "Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start"
        )
        return

    # Используем обновленную функцию
    user_name = get_user_first_name(user)

    prompt = f"""Привет, {user_name} 👋
    
🔬 Я могу помочь с поиском информации по:
• Лабораторным тестам (введите код, например: AN5)
• Преаналитическим требованиям
• Типам контейнеров и условиям хранения
• Или задайте любой вопрос о лабораторной диагностике

💡 Просто напишите ваш вопрос или код теста:"""

    await db.clear_buffer(user_id)
    await message.answer(prompt, reply_markup=get_back_to_menu_kb())

    # Показываем персонализированные подсказки
    await show_personalized_suggestions(message, state)

    await state.set_state(QuestionStates.waiting_for_search_type)


# Глобальный хендлер для кнопки завершения диалога (работает в любом состоянии)
@questions_router.message(F.text == "❌ Завершить диалог")
async def handle_end_dialog(message: Message, state: FSMContext):
    current_state = await state.get_state()
    user = await db.get_user(message.from_user.id)

    # Исправленная обработка role
    if user:
        try:
            role = user["role"] if user["role"] else "user"
        except (KeyError, TypeError):
            role = "user"
    else:
        role = "user"

    # Используем обновленную функцию
    user_name = get_user_first_name(user)

    # Исключение: если пользователь нажал "задать вопрос ассистенту" и не ввел вопрос
    if current_state == QuestionStates.waiting_for_search_type:
        # Возвращаем в главное меню
        await state.clear()
        farewell = get_time_based_farewell(user_name)
        await message.answer(farewell, reply_markup=get_menu_by_role(role))
        return

    # Во всех остальных случаях завершаем диалог
    await state.clear()
    farewell = get_time_based_farewell(user_name)
    await message.answer(farewell, reply_markup=get_menu_by_role(role))
    return


# Обработчик для старой кнопки (для совместимости)
@questions_router.message(F.text == "🔙 Вернуться в главное меню")
async def handle_back_to_menu_legacy(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    role = user["role"] if "role" in user.keys() else "staff"
    await message.answer("Операция отменена.", reply_markup=get_menu_by_role(role))
    return


@questions_router.message(QuestionStates.waiting_for_search_type)
async def handle_universal_search(message: Message, state: FSMContext):
    """Универсальный обработчик запросов - автоматически определяет тип поиска."""
    text = expand_query_with_abbreviations(message.text.strip())
    user_id = message.from_user.id


    # Проверяем, не кнопка ли это возврата или завершения диалога
    if text == "🔙 Вернуться в главное меню" or text == "❌ Завершить диалог":
        return

    # Расширенная проверка для разных вариантов
    # Проверяем не только коды, но и явные запросы
    search_indicators = [
        "покажи",
        "найди",
        "поиск",
        "информация",
        "что такое",
        "расскажи про",
        "анализ на",
    ]

    text_lower = text.lower()
    
    is_search_query = any(indicator in text_lower for indicator in search_indicators)

    # Определяем тип запроса
    if is_test_code_pattern(text):
        # Это похоже на код теста
        await state.set_state(QuestionStates.waiting_for_code)
        await handle_code_search(message, state)
    elif is_search_query or len(text.split()) <= 7:
        # Короткий запрос или явный поиск - используем текстовый поиск
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search(message, state)
    else:
        # Длинный вопрос - возможно, общий вопрос
        # Сначала пробуем найти тест
        processor = DataProcessor()
        processor.load_vector_store()

        # Быстрый поиск
        results = processor.search_test(text, top_k=3)

        if results and results[0][1] > 0.7:  # Высокая уверенность
            await state.set_state(QuestionStates.waiting_for_name)
            await handle_name_search(message, state)
        else:
            # Сохраняем статистику для общих вопросов
            await db.add_request_stat(
                user_id=user_id, request_type="question", request_text=text
            )
            # Обрабатываем как общий вопрос
            await handle_general_question(message, state, text)


@questions_router.message(QuestionStates.waiting_for_code)
async def handle_code_search(message: Message, state: FSMContext):
    """Handle test code search with smart matching and fuzzy suggestions."""
    data = await state.get_data()
    if data.get("is_processing", False):
        await message.answer(
            "⏳ Подождите, идет обработка предыдущего запроса...",
            reply_markup=get_back_to_menu_kb(),
        )
        return

    await state.update_data(is_processing=True)

    user_id = message.from_user.id
    original_input = message.text.strip()

    # Сохраняем статистику вопроса
    await db.add_request_stat(
        user_id=user_id, request_type="question", request_text=original_input
    )

    gif_msg = None
    loading_msg = None
    animation_task = None

    try:
        current_task = asyncio.current_task()
        await state.update_data(current_task=current_task)

        try:
            if LOADING_GIF_ID:
                gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
        except Exception:
            gif_msg = None

        loading_msg = await message.answer(
            "🔍 Ищу тест по коду...\n⏳ Анализирую данные..."
        )
        if loading_msg:
            animation_task = asyncio.create_task(animate_loading(loading_msg))

        if current_task and current_task.cancelled():
            raise asyncio.CancelledError()

        processor = DataProcessor()
        processor.load_vector_store()

        # Нормализуем входной код (с учетом кириллицы)
        normalized_input = normalize_test_code(original_input)

        # Используем умный поиск
        result, found_variant, match_type = await smart_test_search(
            processor, original_input
        )

        if current_task and current_task.cancelled():
            raise asyncio.CancelledError()

        if not result:
            # Ищем похожие тесты с улучшенной фильтрацией
            similar_tests = await fuzzy_test_search(
                processor, normalized_input, threshold=30
            )

            if animation_task:
                animation_task.cancel()
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)

            await db.add_search_history(
                user_id=user_id,
                search_query=original_input,
                search_type="code",
                success=False,
            )

            if similar_tests:
                # Показываем найденные варианты
                response = (
                    f"❌ Тест с кодом '<code>{normalized_input}</code>' не найден.\n"
                )
                response += format_similar_tests_with_links(
                    similar_tests, max_display=10
                )

                keyboard = create_similar_tests_keyboard(similar_tests[:20])

                await message.answer(
                    response
                    + "\n<i>Нажмите на код теста в сообщении выше или выберите из кнопок ниже:</i>",
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
            else:
                error_msg = f"❌ Тест с кодом '{normalized_input}' не найден.\n"
                error_msg += "Попробуйте ввести другой код или опишите, что вы ищете."
                await message.answer(error_msg, reply_markup=get_back_to_menu_kb())

            await state.set_state(QuestionStates.waiting_for_search_type)
            return

        # Найден результат - продолжаем как обычно
        doc = result[0]
        test_data = format_test_data(doc.metadata)

        response = format_test_info(test_data)

        await db.add_search_history(
            user_id=user_id,
            search_query=original_input,
            found_test_code=test_data["test_code"],
            search_type="code",
            success=True,
        )

        await db.update_user_frequent_test(
            user_id=user_id,
            test_code=test_data["test_code"],
            test_name=test_data["test_name"],
        )

        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)

        # ИЗМЕНЕНО: Отправляем информацию с фото
        await send_test_info_with_photo(message, test_data, response)

        # await message.answer(
        #     "Можете задать вопрос об этом тесте или выбрать действие:",
        #     reply_markup=get_dialog_kb()
        # )

        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(
            current_test=test_data, last_viewed_test=test_data["test_code"]
        )

    except asyncio.CancelledError:
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        await message.answer("⏹ Поиск остановлен.", reply_markup=get_back_to_menu_kb())

    except Exception as e:
        print(f"[ERROR] Code search failed: {e}")
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)

        await message.answer(
            "⚠️ Ошибка при поиске. Попробуйте позже", reply_markup=get_back_to_menu_kb()
        )
        await state.set_state(QuestionStates.waiting_for_search_type)

    finally:
        await state.update_data(is_processing=False, current_task=None)


@questions_router.message(QuestionStates.in_dialog, F.text == "🔄 Новый вопрос")
async def handle_new_question_in_dialog(message: Message, state: FSMContext):
    """Обработчик для новых вопросов в режиме диалога."""
    # Сохраняем контекст последних тестов
    data = await state.get_data()
    last_viewed = data.get("last_viewed_test")

    await message.answer(
        "💡 Введите код теста (например: AN5) или опишите, что вы ищете:",
        reply_markup=get_back_to_menu_kb(),
    )

    # Показываем персонализированные подсказки
    await show_personalized_suggestions(message, state)

    # Сохраняем историю просмотров при переходе к новому поиску
    await state.set_state(QuestionStates.waiting_for_search_type)
    if last_viewed:
        await state.update_data(last_viewed_test=last_viewed)


@questions_router.callback_query(F.data == "new_search")
async def handle_new_search(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    # Сохраняем контекст
    data = await state.get_data()
    last_viewed = data.get("last_viewed_test")

    await callback.message.answer(
        "💡 Введите код теста (например: AN5) или опишите, что вы ищете:",
        reply_markup=get_back_to_menu_kb(),
    )

    # Показываем персонализированные подсказки
    message = callback.message
    message.from_user = callback.from_user
    await show_personalized_suggestions(message, state)

    await state.set_state(QuestionStates.waiting_for_search_type)
    if last_viewed:
        await state.update_data(last_viewed_test=last_viewed)


@questions_router.message(QuestionStates.in_dialog, F.text == "📷 Показать контейнер")
async def handle_show_container_photo(message: Message, state: FSMContext):
    """Показывает фото контейнеров для текущего теста."""
    data = await state.get_data()
    test_data = data.get("current_test")

    if not test_data:
        await message.answer("❌ Сначала выберите тест")
        return


@questions_router.message(QuestionStates.waiting_for_name)
async def handle_name_search(message: Message, state: FSMContext):
    """Handle test name search using RAG."""
    user_id = message.from_user.id
    text = message.text.strip()

    # Сохраняем статистику вопроса
    await db.add_request_stat(
        user_id=user_id, request_type="question", request_text=text
    )

    gif_msg = None
    loading_msg = None
    animation_task = None

    try:
        if LOADING_GIF_ID:
            gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
            loading_msg = await message.answer(
                "Обрабатываю ваш запрос...\n⏳ Анализирую данные..."
            )
            animation_task = asyncio.create_task(animate_loading(loading_msg))
        else:
            loading_msg = await message.answer("🔍 Ищем тест...")

        expanded_query = expand_query_with_abbreviations(text)
        processor = DataProcessor()
        processor.load_vector_store()

        rag_hits = processor.search_test(expanded_query, top_k=20)

        if not rag_hits:
            # Записываем неудачный поиск
            await db.add_search_history(
                user_id=user_id, search_query=text, search_type="text", success=False
            )
            raise ValueError("Тесты не найдены")

        selected_docs = await select_best_match(text, rag_hits)

        # Записываем успешный поиск
        for doc in selected_docs[:1]:  # Записываем только первый найденный
            await db.add_search_history(
                user_id=user_id,
                search_query=text,
                found_test_code=doc.metadata["test_code"],
                search_type="text",
                success=True,
            )

            await db.update_user_frequent_test(
                user_id=user_id,
                test_code=doc.metadata["test_code"],
                test_name=doc.metadata["test_name"],
            )

        # Безопасная очистка
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)

        if len(selected_docs) > 1:
            # Показываем несколько результатов с КЛИКАБЕЛЬНЫМИ ССЫЛКАМИ

            # Формируем сообщение с кликабельными кодами
            response = "Найдено несколько подходящих тестов:\n\n"

            for i, doc in enumerate(selected_docs, 1):
                test_data = format_test_data(doc.metadata)
                test_code = test_data["test_code"]
                test_name = html.escape(test_data["test_name"])
                department = html.escape(test_data["department"])

                # Создаем кликабельную ссылку для кода
                link = create_test_link(test_code)

                response += (
                    f"<b>{i}.</b> Тест: <a href='{link}'>{test_code}</a> - {test_name}\n"
                    f"🧬 <b>Вид исследования:</b> {department}\n\n"
                )

                # Ограничиваем длину сообщения
                if len(response) > 3500:
                    response += "\n<i>... и другие результаты</i>"
                    break

            # Отправляем сообщение с кликабельными ссылками
            await message.answer(
                response, parse_mode="HTML", disable_web_page_preview=True
            )

            # Создаем компактную клавиатуру с кнопками (как дополнение к ссылкам)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            row = []

            for i, doc in enumerate(selected_docs[:15]):  # До 15 кнопок
                test_code = doc.metadata["test_code"]
                row.append(
                    InlineKeyboardButton(
                        text=test_code,
                        callback_data=TestCallback.pack("show_test", test_code),
                    )
                )

                # По 3 кнопки в ряд
                if len(row) >= 3:
                    keyboard.inline_keyboard.append(row)
                    row = []

            # Добавляем последний ряд если есть
            if row:
                keyboard.inline_keyboard.append(row)

            # Отправляем клавиатуру с инструкцией
            await message.answer(
                "💡 <b>Нажмите на код теста в сообщении выше или выберите из кнопок:</b>",
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        else:
            # Один результат
            test_data = format_test_data(selected_docs[0].metadata)
            response = format_test_info(test_data)

            # Добавляем похожие тесты с кликабельными ссылками
            similar_tests = await fuzzy_test_search(
                processor, test_data["test_code"], threshold=40
            )
            similar_tests = [
                (d, s)
                for d, s in similar_tests
                if d.metadata.get("test_code") != test_data["test_code"]
            ]

            if similar_tests:
                response += format_similar_tests_with_links(similar_tests[:5])

            # ИЗМЕНЕНО: Отправляем с фото
            await send_test_info_with_photo(message, test_data, response)

            # # Показываем клавиатуру диалога
            # await message.answer(
            #     "Можете задать вопрос об этом тесте или выбрать действие:",
            #     reply_markup=get_dialog_kb()
            # )

        # Сохраняем последний найденный тест для диалога
        await state.set_state(QuestionStates.in_dialog)
        if selected_docs:
            last_test_data = format_test_data(selected_docs[0].metadata)
            await state.update_data(
                current_test=last_test_data,
                last_viewed_test=last_test_data["test_code"],
            )

    except Exception as e:
        print(f"[ERROR] Name search failed: {e}")
        import traceback

        traceback.print_exc()

        # Безопасная очистка при ошибке
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)

        error_msg = (
            "❌ Тесты не найдены"
            if str(e) == "Тесты не найдены"
            else "⚠️ Ошибка поиска. Попробуйте позже."
        )
        await message.answer(error_msg, reply_markup=get_back_to_menu_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)


@questions_router.message(QuestionStates.in_dialog)
async def handle_dialog(message: Message, state: FSMContext):
    """Обработчик диалога с автоматическим переключением на новый поиск."""
    text = message.text.strip()
    user_id = message.from_user.id

    if text == "🔄 Новый вопрос":
        await handle_new_question_in_dialog(message, state)
        return

    data = await state.get_data()
    test_data = data.get("current_test")

    text = expand_query_with_abbreviations(text)

    # Проверяем, не код ли теста введен
    if is_test_code_pattern(text):
        # Если это код - сразу ищем
        await state.set_state(QuestionStates.waiting_for_code)
        await handle_code_search(message, state)
        return

    # Проверяем, нужен ли новый поиск
    needs_new_search = await check_if_needs_new_search(text, test_data)

    if needs_new_search:
        # Автоматически запускаем новый поиск
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search(message, state)
        return

    if not test_data:
        await message.answer(
            "Контекст потерян. Задайте новый вопрос.",
            reply_markup=get_back_to_menu_kb(),
        )
        await state.set_state(QuestionStates.waiting_for_search_type)
        return

    # Если это вопрос про текущий тест - сначала пробуем обработать через LLM
    gif_msg = None
    loading_msg = None
    animation_task = None

    try:
        gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
        loading_msg = await message.answer(
            "Обрабатываю ваш запрос...\n⏳ Анализирую данные..."
        )
        animation_task = asyncio.create_task(animate_loading(loading_msg))

        system_msg = SystemMessage(
            content=f"""
            Ты - ассистент лаборатории VetUnion и отвечаешь только в области ветеринарии. 
            
            Текущий тест:
            Код: {test_data['test_code']}
            Название: {test_data['test_name']}
            
            ВАЖНОЕ ПРАВИЛО:
            Если пользователь спрашивает про ДРУГОЙ тест или анализ (упоминает другой код, название или тип анализа),
            ты ДОЛЖЕН ответить ТОЧНО так:
            "NEED_NEW_SEARCH: [запрос пользователя]"
            
            Если вопрос касается текущего теста или просто пользователь хочет поинтересоваться по другому вопросу, предоставляй всю необходимую информацию в области ветеринарии с пониманием профессионального сленга.
        """
        )

        response = await llm.agenerate([[system_msg, HumanMessage(content=text)]])
        answer = response.generations[0][0].text.strip()

        # Проверяем ответ LLM - нужен ли новый поиск
        if answer.startswith("NEED_NEW_SEARCH:"):
            # LLM определила что нужен новый поиск
            search_query = answer.replace("NEED_NEW_SEARCH:", "").strip()

            # Удаляем загрузочные сообщения
            if animation_task:
                animation_task.cancel()
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)

            # Автоматически запускаем новый поиск с извлеченным запросом
            if search_query:
                # Используем извлеченный запрос
                message.text = search_query

            # Определяем тип поиска и запускаем
            if is_test_code_pattern(message.text):
                await state.set_state(QuestionStates.waiting_for_code)
                await handle_code_search(message, state)
            else:
                await state.set_state(QuestionStates.waiting_for_name)
                await handle_name_search(message, state)
            return

        # Обычный ответ про текущий тест
        answer = fix_bold(answer)  # Добавляем конвертацию markdown
        await loading_msg.edit_text(answer, parse_mode="HTML")  # Добавляем parse_mode
        await message.answer("Выберите действие:", reply_markup=get_dialog_kb())

        # Статистика уже сохранена в handle_universal_search или при первоначальном входе

    except Exception as e:
        print(f"[ERROR] Dialog processing failed: {e}")
        # При ошибке пробуем определить автоматически
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)

        # Запускаем поиск как fallback
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search(message, state)
    finally:
        if animation_task and not animation_task.cancelled():
            animation_task.cancel()
        await safe_delete_message(gif_msg)


async def handle_context_switch(message: Message, state: FSMContext, new_query: str):
    """Обрабатывает переключение контекста на новый тест."""

    # Сохраняем историю
    data = await state.get_data()
    if "current_test" in data:
        last_test = data["current_test"]["test_code"]
        # Можно сохранить в историю диалога
        await state.update_data(
            previous_tests=data.get("previous_tests", []) + [last_test]
        )

    # Определяем тип поиска для нового запроса
    if is_test_code_pattern(new_query):
        await state.set_state(QuestionStates.waiting_for_code)
        message.text = new_query  # Подменяем текст для обработчика
        await handle_code_search(message, state)
    else:
        await state.set_state(QuestionStates.waiting_for_name)
        message.text = new_query
        await handle_name_search(message, state)


async def show_personalized_suggestions(message: Message, state: FSMContext):
    """Показывает персонализированные подсказки при начале поиска"""
    user_id = message.from_user.id

    try:
        # Получаем подсказки
        suggestions = await db.get_search_suggestions(user_id)

        if suggestions:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])

            # Группируем по типам
            frequent = [s for s in suggestions if s["type"] == "frequent"]
            recent = [s for s in suggestions if s["type"] == "recent"]

            if frequent:
                # Добавляем заголовок
                keyboard.inline_keyboard.append(
                    [
                        InlineKeyboardButton(
                            text="⭐ Часто используемые:", callback_data="ignore"
                        )
                    ]
                )

                for sug in frequent[:3]:
                    keyboard.inline_keyboard.append(
                        [
                            InlineKeyboardButton(
                                text=f"{sug['code']} - {sug['name'][:40]}... ({sug['frequency']}x)",
                                callback_data=f"quick_test:{sug['code']}",
                            )
                        ]
                    )

            if recent:
                keyboard.inline_keyboard.append(
                    [
                        InlineKeyboardButton(
                            text="🕐 Недавние поиски:", callback_data="ignore"
                        )
                    ]
                )

                for sug in recent[:2]:
                    keyboard.inline_keyboard.append(
                        [
                            InlineKeyboardButton(
                                text=f"{sug['code']} - {sug['name'][:40]}...",
                                callback_data=f"quick_test:{sug['code']}",
                            )
                        ]
                    )

            await message.answer(
                "💡 Быстрый доступ к вашим тестам:", reply_markup=keyboard
            )
    except Exception as e:
        print(f"[ERROR] Failed to show personalized suggestions: {e}")
        # Не показываем ошибку пользователю, просто не показываем подсказки


async def send_test_info_with_photo(
    message: Message, test_data: Dict, response_text: str
):
    """Отправляет информацию о тесте с кнопкой для показа фото контейнеров"""
    container_type_raw = str(test_data.get("container_type", "")).strip()

    # Проверяем, есть ли контейнеры для показа
    has_containers = container_type_raw and container_type_raw.lower() not in [
        "не указан",
        "нет",
        "-",
        "",
    ]

    keyboard = None

    if has_containers:
        # Создаем кнопку для показа фото
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📷 Показать фото контейнеров",
                        callback_data=f"show_container_photos:{test_data['test_code']}",
                    )
                ]
            ]
        )

    # Отправляем текстовую информацию с кнопкой
    await message.answer(
        response_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )
    return True


def create_similar_tests_keyboard(
    similar_tests: List[Tuple[Document, float]], current_test_code: str = None
) -> InlineKeyboardMarkup:
    """Создает компактную inline клавиатуру с похожими тестами."""
    keyboard = []
    row = []

    count = 0
    for doc, score in similar_tests:
        test_code = doc.metadata.get("test_code", "")

        # Пропускаем текущий тест
        if current_test_code and test_code == current_test_code:
            continue

        # Создаем компактную кнопку только с кодом
        button = InlineKeyboardButton(
            text=test_code, callback_data=TestCallback.pack("show_test", test_code)
        )

        row.append(button)
        count += 1

        # По 4 кнопки в ряд для компактности
        if len(row) >= 4:
            keyboard.append(row)
            row = []

        # Максимум 20 кнопок (5 рядов по 4)
        if count >= 20:
            break

    # Добавляем оставшиеся кнопки
    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def handle_general_question(
    message: Message, state: FSMContext, question_text: str
):
    """Обработка общих вопросов через LLM."""
    user_id = message.from_user.id

    loading_msg = await message.answer("🤔 Обрабатываю ваш вопрос...")

    try:
        system_prompt = """Ты - ассистент ветеринарной лаборатории VetUnion. 
        Ты отвечаешь на все вопросы в области ветеринарии исходя из вопроса, который тебе задали и ты знаешь профессиональный сленг. 
        Отвечай кратко и по существу на русском языке."""

        response = await llm.agenerate(
            [
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=question_text),
                ]
            ]
        )

        answer = response.generations[0][0].text.strip()
        answer = fix_bold(answer)  # Добавляем конвертацию markdown

        await loading_msg.delete()
        await message.answer(answer, parse_mode="HTML")

        # Клавиатура с опциями
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔢 Найти тест по коду", callback_data="search_by_code"
                    ),
                    InlineKeyboardButton(
                        text="📝 Найти по названию", callback_data="search_by_name"
                    ),
                ]
            ]
        )

        await message.answer("Что бы вы хотели сделать дальше?", reply_markup=keyboard)

    except Exception as e:
        print(f"[ERROR] General question handling failed: {e}")
        await loading_msg.delete()
        await message.answer(
            "⚠️ Не удалось обработать вопрос. Попробуйте переформулировать."
        )


async def check_if_needs_new_search(query: str, current_test_data: Dict) -> bool:
    """Улучшенная проверка - нужен ли новый поиск."""

    if not current_test_data:
        return True

    query_upper = query.upper().strip()
    query_lower = query.lower().strip()
    current_test_code = current_test_data.get("test_code", "").upper()
    current_test_name = current_test_data.get("test_name", "").lower()

    # Проверяем, не упоминается ли код другого теста
    # Паттерны для поиска кодов тестов в тексте
    code_patterns = [
        r"\b[AА][NН]\d+[А-ЯA-Z]*\b",  # AN с цифрами и возможным суффиксом
        r"\b\d{1,4}[А-ЯA-Z]+\b",  # Цифры с буквенным суффиксом
        r"\b[AА][NН]\s*\d+\b",  # AN с пробелом и цифрами
        r"\bан\s*\d+\b",  # ан в нижнем регистре
    ]

    for pattern in code_patterns:
        matches = re.findall(pattern, query_upper, re.IGNORECASE)
        for match in matches:
            normalized_match = normalize_test_code(match)
            if normalized_match != current_test_code:
                # Найден другой код теста
                return True

    # Ключевые слова для поиска другого теста
    search_keywords = [
        "покажи",
        "найди",
        "поиск",
        "информация о",
        "что за тест",
        "расскажи про",
        "а что насчет",
        "другой тест",
        "еще тест",
        "анализ на",
        "тест на",
        "найти тест",
        "код теста",
    ]

    # Проверяем наличие ключевых слов поиска
    for keyword in search_keywords:
        if keyword in query_lower:
            # Проверяем, не про текущий ли тест спрашивают
            if current_test_code.lower() not in query_lower and not any(
                word in current_test_name for word in query_lower.split()
            ):
                return True

    # Проверяем упоминание конкретных типов анализов
    test_categories = {
        "биохимия": ["биохим", "алт", "аст", "креатинин", "мочевина", "глюкоза"],
        "гематология": [
            "оак",
            "общий анализ крови",
            "гемоглобин",
            "эритроциты",
            "лейкоциты",
        ],
        "гормоны": ["ттг", "т3", "т4", "кортизол", "тестостерон"],
        "инфекции": ["пцр", "ифа", "антитела", "вирус", "бактерии"],
        "моча": ["моча", "оам", "общий анализ мочи"],
    }

    # Определяем категорию текущего теста
    current_category = None
    for category, keywords in test_categories.items():
        for keyword in keywords:
            if keyword in current_test_name:
                current_category = category
                break

    # Проверяем, не спрашивают ли про другую категорию
    for category, keywords in test_categories.items():
        if category != current_category:
            for keyword in keywords:
                if keyword in query_lower:
                    return True

    return False


__all__ = [
    "questions_router",
    "smart_test_search",
    "format_test_data",
    "format_test_info",
    "format_similar_tests_with_links",
    "QuestionStates",
    "get_dialog_kb",
    "create_test_link",
    "normalize_test_code",
]
