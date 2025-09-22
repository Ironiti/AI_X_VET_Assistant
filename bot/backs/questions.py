from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
    ReplyKeyboardRemove

)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from langchain.schema import SystemMessage, HumanMessage, Document
import asyncio
import html
from typing import Optional, Dict, List, Tuple
from fuzzywuzzy import fuzz
from typing import Dict, Set, Tuple, List
from datetime import datetime
import re

from bot.handlers.ultimate_classifier import ultimate_classifier
from bot.handlers.query_preprocessing import expand_query_with_abbreviations

from src.database.db_init import db
from src.data_vectorization import DataProcessor
from models.models_init import Google_Gemini_2_5_Flash_Lite as llm
from bot.handlers.utils import (
    fix_bold,
    safe_delete_message,
    create_test_link,
    is_test_code_pattern,
    normalize_test_code,
    check_profile_request,
    filter_results_by_type,
    is_profile_test
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
    get_search_type_clarification_kb,
    get_confirmation_kb
)


# LOADING_GIF_ID = (
#     "CgACAgIAAxkBAAMIaGr_qy1Wxaw2VrBrm3dwOAkYji4AAu54AAKmqHlJAtZWBziZvaA2BA"
# )
LOADING_GIF_ID = "CgACAgIAAxkBAAIBFGiBcXtGY7OZvr3-L1dZIBRNqSztAALueAACpqh5Scn4VmIRb4UjNgQ"
# LOADING_GIF_ID = "CgACAgIAAxkBAAMMaHSq3vqxq2RuMMj-DIMvldgDjfkAAu54AAKmqHlJCNcCjeoHRJI2BA"
# Назим
# LOADING_GIF_ID = "CgACAgIAAxkBAANPaMvCZEN3F6cNDG58zpcLZnhqiDsAAu54AAKmqHlJU1E65w2DvLo2BA"

questions_router = Router()


class TestCallback:
    @staticmethod
    def pack(action: str, test_code: str) -> str:
        # Обработка проблемного теста
        if "AN520" in test_code and "," in test_code:
            test_code = "AN520ГИЭ"
        
        # Ограничиваем длину
        if len(test_code) > 40:
            test_code = test_code[:40]
            
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
    confirming_search_type = State()


# Структура для хранения контекста поиска
class SearchContext:
    def __init__(self):
        self.original_query = ""
        self.search_attempts = []
        self.candidate_tests = []
        self.clarification_step = 0
        self.filters = {}
        
class PaginationCallback:
    """Класс для работы с callback данными пагинации"""
    @staticmethod
    def pack(action: str, page: int, search_id: str) -> str:
        return f"page:{action}:{page}:{search_id}"
    
    @staticmethod
    def unpack(callback_data: str) -> Tuple[str, int, str]:
        parts = callback_data.split(":", 3)
        action = parts[1] if len(parts) > 1 else ""
        page = int(parts[2]) if len(parts) > 2 else 0
        search_id = parts[3] if len(parts) > 3 else ""
        return action, page, search_id


def _rerank_hits_by_query(hits: List[Tuple[Document, float]], query: str) -> List[Tuple[Document, float]]:

    if not hits:
        return hits
    # Выделяем только буквы в верхнем регистре
    query_alpha = "".join(ch for ch in (query or "") if ch.isalpha()).upper()
    if len(query_alpha) < 2 or len(query_alpha) > 6:
        return hits

    rescored: List[Tuple[Document, float]] = []
    for doc, base_score in hits:
        code_upper = str(doc.metadata.get("test_code", "")).upper()
        bonus = 0.0

        if code_upper.startswith(query_alpha):
            bonus += 0.5
        elif query_alpha in code_upper:
            bonus += 0.25
        else:
            if base_score < 0.6:
                bonus -= 0.15

        new_score = max(0.0, min(1.0, base_score + bonus))
        rescored.append((doc, new_score))

    rescored.sort(key=lambda x: x[1], reverse=True)
    return rescored

def create_paginated_keyboard(
    tests: List[Document],
    current_page: int = 0,
    items_per_page: int = 6,
    search_id: str = None
) -> Tuple[InlineKeyboardMarkup, int, int]:
    """
    Создает клавиатуру с пагинацией для списка тестов
    
    Returns:
        Tuple[keyboard, total_pages, items_shown]
    """
    total_items = len(tests)
    total_pages = (total_items + items_per_page - 1) // items_per_page
    
    # Вычисляем индексы для текущей страницы
    start_idx = current_page * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    
    keyboard = []
    row = []
    
    # Добавляем кнопки тестов для текущей страницы
    for doc in tests[start_idx:end_idx]:
        test_code = doc.metadata.get("test_code", "")
        
        # Санитизируем код для кнопки
        button_text = sanitize_test_code_for_display(test_code)
        
        row.append(
            InlineKeyboardButton(
                text=button_text,
                callback_data=TestCallback.pack("show_test", test_code)  # pack сам обработает
            )
        )
        
        if len(row) >= 3:  # По 3 кнопки в ряд
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    # Добавляем навигационные кнопки
    nav_row = []
    
    # Кнопка "Назад"
    if current_page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=PaginationCallback.pack("prev", current_page - 1, search_id)
            )
        )
    
    # Индикатор страниц
    nav_row.append(
        InlineKeyboardButton(
            text=f"📄 {current_page + 1}/{total_pages}",
            callback_data="ignore"
        )
    )
    
    # Кнопка "Вперед"
    if current_page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton(
                text="Вперед ▶️",
                callback_data=PaginationCallback.pack("next", current_page + 1, search_id)
            )
        )
    
    if nav_row and total_pages > 1:
        keyboard.append(nav_row)
    
    # Кнопка закрытия
    keyboard.append([
        InlineKeyboardButton(
            text="❌ Закрыть",
            callback_data="close_keyboard"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard), total_pages, end_idx - start_idx

@questions_router.message(F.text == "🔄 Новый вопрос")
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

@questions_router.callback_query(F.data.startswith("page:"))
async def handle_pagination(callback: CallbackQuery, state: FSMContext):
    """Обработчик переключения страниц"""
    await callback.answer()
    
    action, page, search_id = PaginationCallback.unpack(callback.data)
    
    # Получаем сохраненные результаты поиска
    data = await state.get_data()
    search_results = data.get(f"search_results_{search_id}", [])
    
    if not search_results:
        await callback.answer("Результаты поиска устарели. Выполните новый поиск.", show_alert=True)
        return
    
    # Создаем новую клавиатуру для выбранной страницы
    keyboard, total_pages, items_shown = create_paginated_keyboard(
        search_results,
        current_page=page,
        items_per_page=6,
        search_id=search_id
    )
    
    # Формируем текст с результатами для текущей страницы
    start_idx = page * 6
    end_idx = start_idx + items_shown
    
    response = f"🔍 <b>Результаты поиска (страница {page + 1} из {total_pages}):</b>\n\n"
    
    for i, doc in enumerate(search_results[start_idx:end_idx], start=start_idx + 1):
        test_data = format_test_data(doc.metadata)
        test_code = sanitize_test_code_for_display(test_data["test_code"])
        test_name = html.escape(test_data["test_name"])
        department = html.escape(test_data.get("department", "Не указано"))
        
        # Метка для профилей
        type_label = "🔬 Профиль" if is_profile_test(test_code) else "🧪 Тест"
        
        link = create_test_link(test_code)
        
        response += (
            f"<b>{i}.</b> {type_label}: <a href='{link}'>{test_code}</a>\n"
            f"📝 {test_name}\n"
            f"📋 {department}\n\n"
        )
    
    response += "\n💡 <i>Нажмите на код теста или выберите из кнопок ниже</i>"
    
    # Обновляем сообщение
    try:
        await callback.message.edit_text(
            response,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"[ERROR] Failed to update message: {e}")
        await callback.answer("Ошибка обновления сообщения", show_alert=True)

@questions_router.callback_query(F.data.startswith("show_container_photos:"))
async def handle_show_container_photos_callback(callback: CallbackQuery):
    """Обработчик для показа фото контейнеров"""
    await callback.answer()
    
    test_code = callback.data.split(":", 1)[1]
    
    try:
        processor = DataProcessor()
        processor.load_vector_store()
        
        results = processor.search_test(filter_dict={"test_code": test_code})
        
        if not results:
            await callback.message.answer("❌ Тест не найден")
            return
        
        doc = results[0][0] if isinstance(results[0], tuple) else results[0]
        test_data = format_test_data(doc.metadata)
        
        # ✅ ИСПРАВЛЕНИЕ: Проверяем ОБА поля
        container_types_to_check = []
        
        # Сначала проверяем primary_container_type (приоритет)
        primary_container = str(test_data.get("primary_container_type", "")).strip()
        if primary_container and primary_container.lower() not in ["не указан", "нет", "-", ""]:
            primary_container = primary_container.replace('"', "").replace("\n", " ")
            primary_container = " ".join(primary_container.split())
            if "*I*" in primary_container:
                container_types_to_check.extend([ct.strip() for ct in primary_container.split("*I*")])
            else:
                container_types_to_check.append(primary_container)
        
        # Затем проверяем обычный container_type
        container_type_raw = str(test_data.get("container_type", "")).strip()
        if container_type_raw and container_type_raw.lower() not in ["не указан", "нет", "-", ""]:
            container_type_raw = container_type_raw.replace('"', "").replace("\n", " ")
            container_type_raw = " ".join(container_type_raw.split())
            if "*I*" in container_type_raw:
                container_types_to_check.extend([ct.strip() for ct in container_type_raw.split("*I*")])
            else:
                container_types_to_check.append(container_type_raw)
        
        # Убираем дубликаты
        container_types_to_check = list(dict.fromkeys(container_types_to_check))
        
        # Собираем все фото контейнеров
        found_photos = []
        
        for ct in container_types_to_check:
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

        # --- Блок рекомендаций закомментирован по запросу ---
        # # Получаем связанные тесты из истории пользователя
        # related_tests = await db.get_user_related_tests(user_id, test_data["test_code"])
        #
        # # Ищем похожие тесты для этого теста
        # similar_tests = await fuzzy_test_search(
        #     processor, test_data["test_code"], threshold=40
        # )
        #
        # # Фильтруем, чтобы не показывать сам тест
        # similar_tests = [
        #     (d, s)
        #     for d, s in similar_tests
        #     if d.metadata.get("test_code") != test_data["test_code"]
        # ]
        #
        # # Создаем клавиатуру если есть похожие или связанные
        # reply_markup = None
        # if related_tests or similar_tests:
        #     keyboard = []
        #     row = []
        #
        #     # Сначала связанные из истории (приоритет)
        #     for related in related_tests[:4]:
        #         row.append(
        #             InlineKeyboardButton(
        #                 text=f"⭐ {related['test_code']}",
        #                 callback_data=TestCallback.pack(
        #                     "show_test", related["test_code"]
        #                 ),
        #             )
        #         )
        #         if len(row) >= 2:
        #             keyboard.append(row)
        #             row = []
        #
        #     # Затем похожие
        #     for doc, _ in similar_tests[:4]:
        #         if len(keyboard) * 2 + len(row) >= 8:  # Максимум 8 кнопок
        #             break
        #         code = doc.metadata.get("test_code")
        #         if not any(r["test_code"] == code for r in related_tests):
        #             row.append(
        #                 InlineKeyboardButton(
        #                     text=code,
        #                     callback_data=TestCallback.pack("show_test", code),
        #                 )
        #             )
        #             if len(row) >= 2:
        #                 keyboard.append(row)
        #                 row = []
        #
        #     if row:
        #         keyboard.append(row)
        #
        #     reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        # --- Конец закомментированного блока ---

        # Отправляем информацию с фото ТОЛЬКО ОДИН РАЗ
        await send_test_info_with_photo(callback.message, test_data, response)

        # # Если есть рекомендации - отправляем их отдельным сообщением
        # if reply_markup:
        #     await callback.message.answer(
        #         "🎯 Рекомендуем также:", reply_markup=reply_markup
        #     )

        # Обновляем состояние с текущим тестом
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(
            current_test=test_data, last_viewed_test=test_data["test_code"]
        )

        # Показываем клавиатуру для продолжения диалога
        await callback.message.answer(
            "Можете задать вопрос об этом тесте или выбрать действие:",
            reply_markup=get_dialog_kb()
        )

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

        # --- Блок рекомендаций закомментирован по запросу ---
        # # Получаем связанные тесты из истории пользователя
        # related_tests = await db.get_user_related_tests(user_id, test_data["test_code"])
        #
        # # Ищем похожие тесты для этого теста
        # similar_tests = await fuzzy_test_search(
        #     processor, test_data["test_code"], threshold=40
        # )
        #
        # # Фильтруем, чтобы не показывать сам тест
        # similar_tests = [
        #     (d, s)
        #     for d, s in similar_tests
        #     if d.metadata.get("test_code") != test_data["test_code"]
        # ]
        #
        # # Создаем клавиатуру если есть похожие или связанные
        # reply_markup = None
        # if related_tests or similar_tests:
        #     keyboard = []
        #     row = []
        #
        #     # Сначала связанные из истории (приоритет)
        #     for related in related_tests[:4]:
        #         row.append(
        #             InlineKeyboardButton(
        #                 text=f"⭐ {related['test_code']}",
        #                 callback_data=TestCallback.pack(
        #                     "show_test", related["test_code"]
        #                 ),
        #             )
        #         )
        #         if len(row) >= 2:
        #             keyboard.append(row)
        #             row = []
        #
        #     # Затем похожие
        #     for doc, _ in similar_tests[:4]:
        #         if len(keyboard) * 2 + len(row) >= 8:  # Максимум 8 кнопок
        #             break
        #         code = doc.metadata.get("test_code")
        #         if not any(r["test_code"] == code for r in related_tests):
        #             row.append(
        #                 InlineKeyboardButton(
        #                     text=code,
        #                     callback_data=TestCallback.pack("show_test", code),
        #                 )
        #             )
        #             if len(row) >= 2:
        #                 keyboard.append(row)
        #                 row = []
        #
        #     if row:
        #         keyboard.append(row)
        #
        #     reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        # --- Конец закомментированного блока ---

        # Отправляем информацию с фото ТОЛЬКО ОДИН РАЗ
        await send_test_info_with_photo(callback.message, test_data, response)

        # # Если есть рекомендации - отправляем их отдельным сообщением
        # if reply_markup:
        #     await callback.message.answer(
        #         "🎯 Рекомендуем также:", reply_markup=reply_markup
        #     )

        # Обновляем состояние с текущим тестом
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(
            current_test=test_data, last_viewed_test=test_data["test_code"]
        )

        # Показываем клавиатуру для продолжения диалога
        await callback.message.answer(
            "Можете задать вопрос об этом тесте или выбрать действие:",
            reply_markup=get_dialog_kb()
        )

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

🔬 Я ассистент ветеринарной лаборатории VetUnion и помогу вам найти информацию о:

📋 <b>Лабораторных тестах и анализах:</b>
• По коду теста (например: AN116, ан116, АН116 или просто 116)
• По названию или описанию (например: "общий анализ крови", "биохимия")
• По профилям тестов (например: "профили биохимия")

🧪 <b>Преаналитических требованиях:</b>
• Подготовка пациента
• Правила взятия биоматериала
• Условия хранения и транспортировки
• Типы контейнеров для проб

💡 <b>Как мне задать вопрос:</b>
• Введите код теста: <code>AN116</code> или <code>116</code>
• Опишите, что ищете: "анализ на глюкозу"
• Для поиска профилей добавьте слово "профили"

Я автоматически определю тип вашего запроса и найду нужную информацию.

✏️ Просто напишите ваш вопрос или код теста:"""

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
    text = message.text.strip()
    user_id = message.from_user.id

    if text == "🔄 Новый вопрос":
        await handle_new_question_in_dialog(message, state)
        return

    expanded_query = expand_query_with_abbreviations(text)
    # Проверяем, не кнопка ли это возврата
    if text == "🔙 Вернуться в главное меню" or text == "❌ Завершить диалог":
        return

    # Используем классификатор для определения типа запроса
    query_type, confidence, metadata = await ultimate_classifier.classify_with_certainty(expanded_query)

    # Сохраняем информацию о классификации
    await state.update_data(
        query_classification={
            "type": query_type,
            "confidence": confidence,
            "metadata": metadata,
            "original_query": text
        }
    )

    # Если уверенность высокая (>0.85) - сразу обрабатываем
    if confidence > 0.85:
        await _process_confident_query(message, state, query_type, text, metadata)
    else:
        # Если уверенность средняя (0.7-0.85) - просим подтверждение
        await _ask_confirmation(message, state, query_type, expanded_query, confidence)

    # Если уверенность низкая (<0.7) - используем LLM для уточнения
    if confidence < 0.7:
        await _clarify_with_llm(message, state, expanded_query, query_type, confidence)

async def _process_confident_query(message: Message, state: FSMContext, query_type: str, text: str, metadata: Dict):
    user_id = message.from_user.id
    expanded_query = expand_query_with_abbreviations(text)
    
    # Дополнительная проверка для профилей
    profile_keywords = ['обс', 'профили', 'профиль', 'комплексы', 'комплекс', 'панели', 'панель']
    should_show_profiles = any(keyword in text.lower() for keyword in profile_keywords)
    
    if should_show_profiles:
        print(f"[PROFILES] Detected profile keywords, setting show_profiles=True")
        await state.update_data(show_profiles=True)
    
    if any(keyword in text.lower() for keyword in profile_keywords):
        query_type = "profile"
        print(f"[PROFILE DETECTED] Changed query_type to 'profile' for text: {text}")  # ДОБАВЬТЕ ЭТО

    if query_type == "code":
        await state.set_state(QuestionStates.waiting_for_code)
        await handle_code_search_with_text(message, state, expanded_query)
    elif query_type == "name":
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search_with_text(message, state, expanded_query)
    elif query_type == "profile":
        # ДОБАВЬТЕ ДИАГНОСТИКУ
        print(f"[PROFILE BRANCH] Setting show_profiles=True for query: {text}")
        await state.update_data(show_profiles=True)
        
        # Проверяем, что состояние сохранилось
        check_data = await state.get_data()
        print(f"[PROFILE BRANCH] State after update: show_profiles={check_data.get('show_profiles')}")
        
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search_with_text(message, state, expanded_query)
    else:  # general
        await db.add_request_stat(
            user_id=user_id, request_type="question", request_text=text
        )
        await handle_general_question(message, state, expanded_query)

async def _ask_confirmation(message: Message, state: FSMContext, query_type: str, text: str, confidence: float):
    """Запрос подтверждения типа поиска"""
    type_descriptions = {
        "code": "поиск по коду теста",
        "name": "поиск по названию теста",
        "profile": "поиск профиля тестов",
        "general": "общий вопрос"
    }

    confirmation_text = (
        f"🤔 Я понял ваш запрос как <b>{type_descriptions[query_type]}</b> "
        f"(уверенность: {confidence:.0%}).\n\n"
        f"Это правильный тип поиска?"
    )

    await message.answer(
        confirmation_text,
        parse_mode="HTML",
        reply_markup=get_confirmation_kb()
    )
    await state.set_state(QuestionStates.confirming_search_type)

async def _clarify_with_llm(message: Message, state: FSMContext, text: str, initial_type: str, confidence: float):
    clarification_text = (
        f"🔍 Я не совсем уверен, что вы ищете.\n\n"
        f"Ваш запрос: <b>{html.escape(text)}</b>\n\n"
        f"Пожалуйста, выберите тип поиска:"
    )

    await message.answer(
        clarification_text,
        parse_mode="HTML",
        reply_markup=get_search_type_clarification_kb()
    )
    await state.set_state(QuestionStates.clarifying_search)


@questions_router.message(QuestionStates.confirming_search_type)
async def handle_search_confirmation(message: Message, state: FSMContext):
    user_id = message.from_user.id

    text = message.text.strip()
    data = await state.get_data()
    classification = data.get("query_classification", {})

    if text == "✅ Да":
        # Пользователь подтвердил - обрабатываем запрос
        query_type = classification.get("type", "general")
        original_query = classification.get("original_query", "")
        expanded_query = expand_query_with_abbreviations(original_query)

        # Убираем клавиатуру подтверждения
        await message.answer("✅ Принято! Обрабатываю запрос...", reply_markup=get_dialog_kb())

        if query_type == "code":
            await state.set_state(QuestionStates.waiting_for_code)
            await handle_code_search_with_text(message, state, original_query)
        elif query_type == "name":
            await state.set_state(QuestionStates.waiting_for_name)
            await handle_name_search_with_text(message, state, expanded_query)
        elif query_type == "profile":
            await state.update_data(show_profiles=True)
            await state.set_state(QuestionStates.waiting_for_name)
            await handle_name_search_with_text(message, state, expanded_query)
        else:
            await db.add_request_stat(
                user_id=user_id, request_type="question", request_text=text
            )
            await handle_general_question(message, state, expanded_query)

    elif text == "❌ Нет":
        # Пользователь не подтвердил - предлагаем выбрать тип
        await message.answer("❌ Понятно! Уточните тип поиска:", reply_markup=get_dialog_kb())

        await state.set_state(QuestionStates.clarifying_search)

        await _clarify_with_llm(
            message, state,
            classification.get("original_query", ""),
            classification.get("type", "general"),
            classification.get("confidence", 0.5)
        )

    elif text == "❌ Завершить диалог":
        await handle_end_dialog(message, state)
    else:
        await message.answer("Пожалуйста, используйте кнопки для ответа.")



@questions_router.message(QuestionStates.clarifying_search, F.text)
async def handle_text_input_during_clarification(message: Message, state: FSMContext):
    """Обработчик текстового ввода во время уточнения типа поиска"""
    text = message.text.strip()

    # Если пользователь ввел текст вместо выбора кнопки, обрабатываем как новый запрос
    if text and text not in ["🔢 Поиск по коду теста", "📝 Поиск по названию",
                           "🔬 Поиск профиля тестов", "❓ Общий вопрос", "❌ Завершить диалог"]:

        # Очищаем состояние уточнения
        await state.set_state(QuestionStates.waiting_for_search_type)

        # Обрабатываем как новый запрос
        await handle_universal_search(message, state)
    else:
        # Если это одна из кнопок, передаем обработку основному обработчику
        await handle_search_clarification(message, state)

@questions_router.message(QuestionStates.clarifying_search)
async def handle_search_clarification(message: Message, state: FSMContext):
    user_id = message.from_user.id

    text = message.text.strip()
    data = await state.get_data()
    original_query = data.get("query_classification", {}).get("original_query", "")
    expanded_query = expand_query_with_abbreviations(original_query)


    if text == "🔢 Поиск по коду теста":
        await message.answer("✅ Ищу по коду...", reply_markup=get_dialog_kb())
        await state.set_state(QuestionStates.waiting_for_code)
        await handle_code_search_with_text(message, state, original_query)
    elif text == "📝 Поиск по названию":
        await message.answer("✅ Ищу по названию...", reply_markup=get_dialog_kb())
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search_with_text(message, state, expanded_query)
    elif text == "🔬 Поиск профиля тестов":
        await message.answer("✅ Ищу профили тестов...", reply_markup=get_dialog_kb())

        await state.update_data(show_profiles=True)
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search_with_text(message, state, expanded_query)
    elif text == "❓ Общий вопрос":
        await db.add_request_stat(
            user_id=user_id, request_type="question", request_text=text
        )
        await message.answer("✅ Отвечаю на вопрос...", reply_markup=get_dialog_kb())
        await handle_general_question(message, state, expanded_query)
    elif text == "❌ Завершить диалог":
        await handle_end_dialog(message, state)
    else:
        await message.answer("Пожалуйста, выберите тип поиска из предложенных вариантов.")


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
    await _handle_name_search_internal(message, state)


@questions_router.message(QuestionStates.in_dialog)
async def handle_dialog(message: Message, state: FSMContext):
    text = message.text.strip()
    user_id = message.from_user.id

    if text == "🔄 Новый вопрос":
        await handle_new_question_in_dialog(message, state)
        return

    data = await state.get_data()
    test_data = data.get("current_test")

    expanded_query = expand_query_with_abbreviations(text)
    # Используем классификатор для определения типа нового запроса
    query_type, confidence, metadata = await ultimate_classifier.classify_with_certainty(expanded_query)

    # Проверяем, нужен ли новый поиск (не общий вопрос о текущем тесте)
    needs_new_search = await _should_initiate_new_search(expanded_query, test_data, query_type, confidence)

    if needs_new_search:
        # Сохраняем информацию о классификации для последующих шагов
        await state.update_data(
            query_classification={
                "type": query_type,
                "confidence": confidence,
                "metadata": metadata,
                "original_query": text
            }
        )

        # Высокая уверенность — сразу маршрутизируем
        if confidence > 0.85:
            await _process_confident_query(message, state, query_type, expanded_query, metadata)
        else:
            # Средняя уверенность — спросить подтверждение
            await _ask_confirmation(message, state, query_type, expanded_query, confidence)
            # Низкая уверенность — дополнительное уточнение через LLM
            if confidence < 0.7:
                await _clarify_with_llm(message, state, expanded_query, query_type, confidence)
        return

    # Вопрос относится к текущему тесту — обрабатываем в контексте, остаёмся в in_dialog
    await _handle_contextual_question(message, state, expanded_query, test_data)


async def _should_initiate_new_search(text: str, current_test_data: Dict, query_type: str, confidence: float) -> bool:
    """Определяет, нужно ли начинать новый поиск"""
    if not current_test_data:
        return True

    # Если запрос явно указывает на новый поиск
    if query_type != "general" and confidence > 0.7:
        return True

    # Эвристики для определения нового поиска
    text_lower = text.lower()

    # Ключевые слова, указывающие на новый поиск
    new_search_keywords = [
        'найди', 'ищи', 'покажи', 'поиск', 'найти',
        'другой', 'еще', 'следующий', 'иной',
        'код', 'тест', 'анализ', 'профиль'
    ]

    # Проверяем, содержит ли запрос указание на новый поиск
    has_search_intent = any(keyword in text_lower for keyword in new_search_keywords)

    # Проверяем, не упоминается ли код другого теста
    has_other_code = await _contains_other_test_code(text, current_test_data.get("test_code", ""))

    return has_search_intent or has_other_code

async def _contains_other_test_code(text: str, current_test_code: str) -> bool:
    """Проверяет, содержит ли текст код другого теста"""
    # Извлекаем все возможные коды тестов из текста
    code_patterns = [
        r'[AА][NН]\d+[A-ZА-Я\-]*',
        r'\b\d+[A-ZА-Я\-]*',
        r'[A-ZА-Я]+\d+[A-ZА-Я\-]*',
    ]

    found_codes = set()
    for pattern in code_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            normalized = normalize_test_code(match)
            if normalized and normalized != current_test_code:
                found_codes.add(normalized)

    return len(found_codes) > 0

async def _ask_dialog_clarification(message: Message, state: FSMContext, text: str, query_type: str, confidence: float):
    """Запрос уточнения в режиме диалога"""
    clarification_text = (
        f"🔍 Вы хотите задать вопрос о текущем тесте или начать новый поиск?\n\n"
        f"Запрос: <b>{html.escape(text)}</b>"
    )

    keyboard = InlineKeyboardMarkup(
        keyboard=[
            [InlineKeyboardButton(text="❓ Вопрос о текущем тесте")],
            [InlineKeyboardButton(text="🔍 Новый поиск")],
            [InlineKeyboardButton(text="❌ Завершить диалог")]
        ],
        resize_keyboard=True
    )

    await message.answer(clarification_text, parse_mode="HTML", reply_markup=keyboard)
    await state.set_state(QuestionStates.clarifying_search)

async def _handle_contextual_question(message: Message, state: FSMContext, question: str, test_data: Dict):
    """Обработка вопроса о текущем тесте"""
    if not test_data:
        await message.answer("Контекст потерян. Задайте новый вопрос.")
        await state.set_state(QuestionStates.waiting_for_search_type)
        return

    # Обработка через LLM с контекстом текущего теста
    gif_msg = None
    loading_msg = None
    animation_task = None

    try:
        # Показ загрузки (не падаем, если GIF недоступен)
        try:
            gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
        except Exception:
            gif_msg = None
        loading_msg = await message.answer("Обрабатываю ваш вопрос...")
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

        # Запрашиваем ответ у LLM
        response = await llm.agenerate([[system_msg, HumanMessage(content=question)]])
        answer = response.generations[0][0].text.strip()

        # Проверка на необходимость нового поиска
        if answer.startswith("NEED_NEW_SEARCH:"):
            # Отменяем анимацию и удаляем лоадеры
            if animation_task:
                animation_task.cancel()
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)

            search_query = answer.replace("NEED_NEW_SEARCH:", "").strip() or question

            # Классифицируем новый запрос
            query_type, confidence, metadata = await ultimate_classifier.classify_with_certainty(search_query)

            await state.update_data(
                query_classification={
                    "type": query_type,
                    "confidence": confidence,
                    "metadata": metadata,
                    "original_query": search_query
                }
            )

            if confidence > 0.85:
                await _process_confident_query(message, state, query_type, search_query, metadata)
            else:
                await _ask_confirmation(message, state, query_type, search_query, confidence)
                if confidence < 0.7:
                    await _clarify_with_llm(message, state, search_query, query_type, confidence)
            return

        # Обычный ответ по текущему тесту
        answer = fix_bold(answer)
        await loading_msg.edit_text(answer, parse_mode="HTML")
        await message.answer("Выберите действие:", reply_markup=get_dialog_kb())

    except Exception as e:
        print(f"[ERROR] Dialog processing failed: {e}")
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)

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
        await handle_code_search_with_text(message, state, new_query)
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
    
    has_containers = False
    
    # Проверяем primary_container_type
    primary_container = str(test_data.get("primary_container_type", "")).strip()
    if primary_container and primary_container.lower() not in ["не указан", "нет", "-", ""]:
        has_containers = True
    
    # Если primary нет, проверяем обычный container_type
    if not has_containers:
        container_type_raw = str(test_data.get("container_type", "")).strip()
        if container_type_raw and container_type_raw.lower() not in ["не указан", "нет", "-", ""]:
            has_containers = True
    
    keyboard = None
    
    if has_containers:
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

def sanitize_test_code_for_display(test_code: str) -> str:
    """Обрезает слишком длинные коды тестов для корректного отображения"""
    if not test_code:
        return test_code
    
    # Специальная обработка для проблемного теста со сканированием
    if "AN520" in test_code and "," in test_code:
        # Берем только первый код из списка
        return "AN520ГИЭ"
    
    # Для остальных - если код слишком длинный, обрезаем
    if len(test_code) > 20:
        return test_code[:17] + "..."
    
    return test_code

def replace_test_codes_with_links(text: str, all_test_codes: set) -> tuple[str, dict]:
    """
    Заменяет коды тестов в тексте на HTML ссылки.
    
    Args:
        text: Исходный текст
        all_test_codes: Множество всех доступных кодов тестов
    
    Returns:
        Tuple[str, Dict]: Текст с маркерами и словарь замен
    """
    # Находим ВСЕ коды и их позиции
    all_matches = []
    
    patterns = [
        r'\b[AА][NН]\d+[A-ZА-Я\-]*\b',  # AN116, AN116-X
        r'\b[A-ZА-Я]+\d+[A-ZА-Я\-]*\b', # ABC123
        r'\b\d{2,4}[A-ZА-Я]+\b',        # 123ABC
    ]
    
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            found_code = match.group()
            normalized_code = normalize_test_code(found_code)
            
            # Проверяем что код валидный и существует
            if normalized_code and normalized_code.upper() in all_test_codes:
                all_matches.append({
                    'start': match.start(),
                    'end': match.end(),
                    'code': found_code,
                    'normalized': normalized_code
                })
    
    # Удаляем пересекающиеся совпадения (оставляем самые длинные)
    filtered_matches = []
    for match in all_matches:
        overlap = False
        for other in filtered_matches:
            # Проверяем пересечение
            if (match['start'] < other['end'] and match['end'] > other['start']):
                # Если текущий match короче - пропускаем его
                if len(match['code']) <= len(other['code']):
                    overlap = True
                    break
                else:
                    # Если текущий длиннее - удаляем короткий
                    filtered_matches = [m for m in filtered_matches if m != other]
        
        if not overlap:
            filtered_matches.append(match)
    
    # Сортируем по позиции с конца (чтобы не сбивать индексы)
    filtered_matches.sort(key=lambda x: x['start'], reverse=True)
    
    # Заменяем найденные коды на специальные маркеры
    result = text
    replacements = {}
    
    for i, match in enumerate(filtered_matches):
        marker = f"__TEST_LINK_{i}__{match['normalized']}__"  # Изменен формат маркера
        result = result[:match['start']] + marker + result[match['end']:]
        
        # Создаем ссылку и проверяем ее валидность
        link = create_test_link(match['normalized'])
        
        # Убеждаемся что ссылка корректная
        if link and 'https://t.me/' in link:
            # Экранируем только отображаемый текст, не саму ссылку
            display_text = html.escape(match["code"])
            replacements[marker] = f'<a href="{link}">{display_text}</a>'
        else:
            # Если ссылка не сгенерировалась - просто текст
            replacements[marker] = html.escape(match["code"])
    
    return result, replacements

async def handle_general_question(
    message: Message, state: FSMContext, question_text: str
):
    import re
    
    user = await db.get_user(message.from_user.id)
    
    loading_msg = await message.answer("🤔 Анализирую вопрос...")

    try:
        processor = DataProcessor()
        processor.load_vector_store()
        
        # 1. Сначала ищем релевантные тесты для КОНКРЕТНОГО вопроса
        relevant_docs = processor.search_test(query=question_text, top_k=50)
        relevant_tests = [doc for doc, score in relevant_docs if score > 0.3]
        
        # 2. Собираем ТОЛЬКО релевантную информацию
        context_info = ""
        all_test_codes = set()
        
        if relevant_tests:
            context_info = "\n\nРЕЛЕВАНТНАЯ ИНФОРМАЦИЯ ДЛЯ ВАШЕГО ВОПРОСА:\n"
            
            for doc in relevant_tests[:10]:  
                test_data = doc.metadata
                test_code = test_data.get('test_code', '')
                
                if test_code:
                    normalized_code = normalize_test_code(test_code)
                    if normalized_code:  # Проверяем что код не пустой
                        all_test_codes.add(normalized_code.upper())
                    
                    context_info += f"\n🔬 Тест {normalized_code} - {test_data.get('test_name', '')}:\n"
                    
                    # Добавляем только поля с данными
                    fields = [
                        ('type', 'Тип'),
                        ('specialization', 'Специализация'),
                        ('code_letters', 'Аббревиатура в коде теста'),
                        ('department', 'Вид исследования'),
                        ('patient_preparation', 'Подготовка'),
                        ('biomaterial_type', 'Биоматериал'),
                        ('container_type', 'Контейнер'),
                        ('container_number', 'Номер контейнера'),
                        ('storage_temp', 'Хранение'),
                        ('preanalytics', 'Преаналитика'),
                        ('animal_type', 'Виды животных'),
                        ('important_information', 'Важная информация'),
                        ('poss_postorder_container', 'Возможность дозаказа после взятия биоматериала'),
                    ]
                    
                    for field, label in fields:
                        value = test_data.get(field)
                        if value and str(value).strip().lower() not in ['не указан', 'нет', '-', '']:
                            value_str = str(value)
                            if len(value_str) > 100:
                                value_str = value_str[:97] + "..."
                            context_info += f"  {label}: {value_str}\n"
                    
                    context_info += "  ─────────────────────────\n"
        
        # 3. Добавляем общую статистику ТОЛЬКО если нужно
        if "сколько" in question_text.lower() or "статистик" in question_text.lower():
            all_docs = processor.search_test(query="", top_k=20)
            departments = set()
            
            for doc, score in all_docs:
                if dept := doc.metadata.get('department'):
                    departments.add(dept)
            
            context_info += f"\n📊 Общая статистика: {len(departments)} видов исследований\n"

        # Промпт для LLM
        system_prompt = f"""
            # Роль: Ассистент ветеринарной лаборатории VetUnion

            Ты - профессиональный консультант ветеринарной лаборатории, специализирующийся на лабораторной диагностике животных.

            ## Источники информации
            Контекст: {context_info}
            Постоянно обращайся к пользователю по его имени {user}, без фамилии (если она есть)

            ## Основные принципы работы

            **Точность и безопасность:**
            - Используй ТОЛЬКО информацию из предоставленного контекста
            - При недостатке данных честно сообщай об ограничениях
            - Никогда не давай экстренных медицинских советов - направляй к ветеринару
            - Не интерпретируй результаты анализов без достаточной информации

            **Качество ответов:**
            - Адаптируй детализацию к сложности вопроса
            - Используй профессиональную ветеринарную терминологию
            - Указывай коды тестов при упоминании конкретных исследований
            - Структурируй информацию логично
            - Добавляй в ответ много эмодзи по смыслу
            
            ## Ограничения
            - Не предоставляй информацию, отсутствующую в контексте
            - Не ставь диагнозы и не интерпретируй результаты
            - При критических вопросах направляй к специалисту нашей лаборатории
            - Не давай советы по лечению
            - Не задавай вопросов, старайся разобраться сам
        """

        # 5. Отправляем в LLM
        response = await llm.agenerate(
            [
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=question_text),
                ]
            ]
        )

        answer = response.generations[0][0].text.strip()
        
        # УПРОЩЕННАЯ ОБРАБОТКА:
        
        # 1. Находим все коды тестов и создаем словарь замен
        code_to_link = {}
        
        # Паттерны для поиска кодов
        patterns = [
            r'\b[AА][NН]\d+[A-ZА-Я\-]*\b',
            r'\b[A-ZА-Я]+\d+[A-ZА-Я\-]*\b',
            r'\b\d{2,4}[A-ZА-Я]+\b',
        ]
        
        # Находим все коды в тексте
        found_codes = set()
        for pattern in patterns:
            for match in re.finditer(pattern, answer, re.IGNORECASE):
                code = match.group()
                normalized = normalize_test_code(code)
                if normalized and normalized.upper() in all_test_codes:
                    found_codes.add((code, normalized))
        
        # Создаем ссылки для найденных кодов
        for original, normalized in found_codes:
            link = create_test_link(normalized)
            if link and 'https://t.me/' in link:
                code_to_link[original] = f'<a href="{link}">{html.escape(original)}</a>'
        
        # 2. Экранируем весь текст
        processed_text = html.escape(answer)
        
        # 3. Применяем форматирование markdown
        # **текст** -> <b>текст</b>
        processed_text = re.sub(r'\*\*([^\*]+)\*\*', r'<b>\1</b>', processed_text)
        
        # *текст* -> <i>текст</i>
        processed_text = re.sub(r'(?<!\*)\*([^\*]+)\*(?!\*)', r'<i>\1</i>', processed_text)
        
        # 4. Заменяем коды тестов на ссылки
        # Сортируем по длине (сначала длинные) чтобы избежать частичных замен
        sorted_codes = sorted(code_to_link.keys(), key=len, reverse=True)
        
        for code in sorted_codes:
            # Экранированная версия кода для поиска
            escaped_code = html.escape(code)
            # Заменяем только целые слова
            pattern = r'\b' + re.escape(escaped_code) + r'\b'
            processed_text = re.sub(pattern, code_to_link[code], processed_text)
        
        await loading_msg.delete()
        
        # Проверка длины и отправка
        if len(processed_text) > 4000:
            # Разбиваем на части по параграфам или строкам
            parts = []
            current = ""
            
            # Разбиваем по двойным переносам (параграфы)
            paragraphs = processed_text.split('\n\n')
            
            for para in paragraphs:
                if len(current) + len(para) + 2 < 3900:
                    current += para + '\n\n' if current else para
                else:
                    if current:
                        parts.append(current.rstrip())
                    current = para
            
            if current:
                parts.append(current.rstrip())
            
            # Отправляем части
            for i, part in enumerate(parts):
                try:
                    await message.answer(
                        part,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    if i < len(parts) - 1:
                        await asyncio.sleep(0.5)  # Небольшая задержка между частями
                except Exception as e:
                    print(f"[ERROR] Failed to send part {i+1}: {e}")
                    # Очищаем от HTML и отправляем
                    clean_part = re.sub(r'<[^>]+>', '', part)
                    await message.answer(clean_part)
        else:
            try:
                await message.answer(
                    processed_text,
                    parse_mode="HTML", 
                    disable_web_page_preview=True
                )
            except Exception as e:
                print(f"[ERROR] Failed to send HTML message: {e}")
                print(f"[ERROR] Text length: {len(processed_text)}")
                
                # Попробуем найти проблемное место
                if "can't parse entities" in str(e):
                    # Извлекаем позицию ошибки
                    import re
                    match = re.search(r'byte offset (\d+)', str(e))
                    if match:
                        offset = int(match.group(1))
                        print(f"[ERROR] Problem around position {offset}:")
                        print(f"[ERROR] Context: ...{processed_text[max(0, offset-50):offset+50]}...")
                
                # Fallback
                clean_text = re.sub(r'<[^>]+>', '', answer)
                await message.answer(clean_text, disable_web_page_preview=True)

        # Кнопки для дальнейших действий
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
        import traceback
        traceback.print_exc()
        
        await safe_delete_message(loading_msg)
        await message.answer(
            "⚠️ Не удалось обработать вопрос. Попробуйте переформулировать."
        )

async def handle_code_search_with_text(message: Message, state: FSMContext, search_text: str):
    """Wrapper для handle_code_search с передачей текста"""
    # Вызываем основной обработчик, но используем переданный текст
    await _handle_code_search_internal(message, state, search_text)
    
async def cleanup_old_search_results(state: FSMContext, keep_last: int = 3):
    """Очищает старые результаты поиска из состояния"""
    data = await state.get_data()
    search_keys = [k for k in data.keys() if k.startswith("search_results_")]
    
    # Если результатов больше, чем нужно хранить
    if len(search_keys) > keep_last:
        # Сортируем по времени (ID содержит timestamp)
        search_keys.sort()
        
        # Удаляем старые
        for key in search_keys[:-keep_last]:
            await state.update_data(**{key: None})

async def handle_name_search_with_text(message: Message, state: FSMContext, search_text: str):
    """Wrapper для handle_name_search с передачей текста"""
    await _handle_name_search_internal(message, state, search_text)

async def _handle_name_search_internal(message: Message, state: FSMContext, search_text: str = None):
    """Внутренняя функция обработки поиска по имени с пагинацией"""
    user_id = message.from_user.id

    # Получаем данные из состояния
    data = await state.get_data()
    show_profiles = data.get("show_profiles", False)
    original_query = data.get("original_query", message.text if not search_text else search_text)

    #Диагностика 
    print(f"[NAME SEARCH] show_profiles={show_profiles}, original_query={original_query}")
    # Используем переданный текст или текст из сообщения
    text = search_text if search_text else message.text.strip()
    text = expand_query_with_abbreviations(text)

    # Сохраняем статистику с оригинальным запросом
    await db.add_request_stat(
        user_id=user_id, request_type="question", request_text=original_query
    )

    gif_msg = None
    loading_msg = None
    animation_task = None

    try:
        # Определяем что ищем
        search_type = "профили" if show_profiles else "тесты"

        if LOADING_GIF_ID:
            gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
            loading_msg = await message.answer(
                f"🔍 Ищу {search_type} по запросу...\n⏳ Анализирую данные..."
            )
            animation_task = asyncio.create_task(animate_loading(loading_msg))
        else:
            loading_msg = await message.answer(f"🔍 Ищу {search_type}...")

        processor = DataProcessor()
        processor.load_vector_store()

        # Ищем по тексту
        rag_hits = processor.search_test(text, top_k=30)

        # Фильтруем по типу (профили или обычные тесты)
        filtered_hits = filter_results_by_type(rag_hits, show_profiles)

        # Универсальный реранж с учетом буквенного запроса/префикса
        filtered_hits = _rerank_hits_by_query(filtered_hits, original_query)

        if not filtered_hits:
            await db.add_search_history(
                user_id=user_id,
                search_query=original_query,
                search_type="text",
                success=False
            )

            # Безопасная очистка
            if animation_task:
                animation_task.cancel()
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)

            not_found_msg = f"❌ {search_type.capitalize()} по запросу '<b>{html.escape(text)}</b>' не найдены.\n\n"
            if show_profiles:
                not_found_msg += "💡 Попробуйте поиск без слова 'профили' для обычных тестов."
            else:
                not_found_msg += "💡 Добавьте слово 'профили' в запрос для поиска профилей тестов."

            await message.answer(
                not_found_msg,
                reply_markup=get_back_to_menu_kb(),
                parse_mode="HTML"
            )
            await state.set_state(QuestionStates.waiting_for_search_type)
            await state.update_data(show_profiles=False, search_text=None)
            return

        # Выбираем лучшие совпадения
        selected_docs = await select_best_match(text, filtered_hits[:20])

        # Записываем успешный поиск
        for doc in selected_docs[:1]:
            await db.add_search_history(
                user_id=user_id,
                search_query=original_query,
                found_test_code=doc.metadata["test_code"],
                search_type="text",
                success=True
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

        # Если найдено несколько результатов - показываем с пагинацией
        if len(selected_docs) > 1:
            # Генерируем уникальный ID для этого поиска
            import hashlib
            from datetime import datetime
            
            search_id = hashlib.md5(
                f"{user_id}_{datetime.now().isoformat()}_{text}".encode()
            ).hexdigest()[:8]
            
            # Сохраняем результаты в состоянии
            await state.update_data(**{f"search_results_{search_id}": selected_docs})
            
            # Очищаем старые результаты
            await cleanup_old_search_results(state)
            
            # Показываем первую страницу результатов
            keyboard, total_pages, items_shown = create_paginated_keyboard(
                selected_docs,
                current_page=0,
                items_per_page=6,
                search_id=search_id
            )
            
            # Формируем текст для первой страницы
            total_found = len(selected_docs)
            response = f"🔍 <b>Найдено {total_found} {search_type}</b>"
            if total_pages > 1:
                response += f" <b>(страница 1 из {total_pages}):</b>\n\n"
            else:
                response += ":\n\n"
            
            for i, doc in enumerate(selected_docs[:items_shown], 1):
                test_data = format_test_data(doc.metadata)
                test_code = sanitize_test_code_for_display(test_data["test_code"])
                test_name = html.escape(test_data["test_name"])
                department = html.escape(test_data.get("department", "Не указано"))
                
                # Добавляем метку для профилей
                type_label = "🔬 Профиль" if is_profile_test(test_code) else "🧪 Тест"
                
                link = create_test_link(test_code)
                
                response += (
                    f"<b>{i}.</b> {type_label}: <a href='{link}'>{test_code}</a> - {test_name}\n"
                    f"📋 <b>Вид исследования:</b> {department}\n\n"
                )
            
            # Добавляем подсказку
            response += "\n💡 <i>Нажмите на код теста в сообщении выше или выберите из кнопок</i>"
            
            # Если страниц больше одной, добавляем информацию о навигации
            if total_pages > 1:
                response += f"\n📄 <i>Используйте кнопки навигации для просмотра всех результатов</i>"
            
            await message.answer(
                response,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard
            )
            
            # Сохраняем последний найденный тест для контекста
            last_test_data = format_test_data(selected_docs[0].metadata)
            await state.update_data(
                current_test=last_test_data,
                last_viewed_test=last_test_data["test_code"],
                show_profiles=False,
                search_text=None
            )
            
        else:
            # Один результат - показываем подробную информацию
            test_data = format_test_data(selected_docs[0].metadata)

            # Добавляем информацию о типе
            type_info = ""
            if is_profile_test(test_data["test_code"]):
                type_info = "🔬 <b>Это профиль тестов</b>\n\n"

            response = type_info + format_test_info(test_data)

            # Добавляем похожие тесты того же типа
            similar_tests = await fuzzy_test_search(
                processor, test_data["test_code"], threshold=40
            )

            # Фильтруем похожие по типу
            is_profile = is_profile_test(test_data["test_code"])
            similar_tests = filter_results_by_type(similar_tests, is_profile)
            similar_tests = [
                (d, s)
                for d, s in similar_tests
                if d.metadata.get("test_code") != test_data["test_code"]
            ]

            # Если есть похожие тесты, показываем их с пагинацией
            if len(similar_tests) > 5:
                # Генерируем ID для похожих тестов
                import hashlib
                from datetime import datetime
                
                similar_search_id = hashlib.md5(
                    f"{user_id}_{datetime.now().isoformat()}_similar_{test_data['test_code']}".encode()
                ).hexdigest()[:8]
                
                # Сохраняем похожие тесты
                similar_docs = [doc for doc, _ in similar_tests]
                await state.update_data(**{f"search_results_{similar_search_id}": similar_docs})
                
                response += format_similar_tests_with_links(similar_tests[:5])
                response += f"\n\n<i>Всего найдено {len(similar_tests)} похожих тестов</i>"
            elif similar_tests:
                response += format_similar_tests_with_links(similar_tests)

            # Отправляем с фото
            await send_test_info_with_photo(message, test_data, response)

            # Обновляем связанные тесты
            if "last_viewed_test" in data and data["last_viewed_test"] != test_data["test_code"]:
                await db.update_related_tests(
                    user_id=user_id,
                    test_code_1=data["last_viewed_test"],
                    test_code_2=test_data["test_code"],
                )

            # Обновляем состояние
            await state.set_state(QuestionStates.in_dialog)
            await state.update_data(
                current_test=test_data,
                last_viewed_test=test_data["test_code"],
                show_profiles=False,
                search_text=None
            )

        # Показываем клавиатуру для продолжения диалога
        await message.answer(
            "Можете задать вопрос об этом тесте или выбрать действие:",
            reply_markup=get_dialog_kb()
        )

    except Exception as e:
        print(f"[ERROR] Name search failed: {e}")
        import traceback
        traceback.print_exc()

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
        await state.update_data(show_profiles=False, search_text=None)

async def _handle_code_search_internal(message: Message, state: FSMContext, search_text: str = None):
    """Внутренняя функция обработки поиска по коду с пагинацией"""
    data = await state.get_data()
    if data.get("is_processing", False):
        await message.answer(
            "⏳ Подождите, идет обработка предыдущего запроса...",
            reply_markup=get_back_to_menu_kb(),
        )
        return

    await state.update_data(is_processing=True)

    user_id = message.from_user.id

    # Используем переданный текст или текст из сообщения
    original_input = search_text if search_text else message.text.strip()

    # Получаем флаги из состояния
    show_profiles = data.get("show_profiles", False)
    original_query = data.get("original_query", original_input)

    # Сохраняем статистику
    await db.add_request_stat(
        user_id=user_id, request_type="question", request_text=original_query
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

        # Определяем что ищем
        search_type = "профили" if show_profiles else "тесты"
        loading_msg = await message.answer(
            f"🔍 Ищу {search_type} по коду...\n⏳ Анализирую данные..."
        )
        if loading_msg:
            animation_task = asyncio.create_task(animate_loading(loading_msg))

        if current_task and current_task.cancelled():
            raise asyncio.CancelledError()

        processor = DataProcessor()
        processor.load_vector_store()

        # Нормализуем входной код
        normalized_input = normalize_test_code(original_input)

        # Используем умный поиск
        result, found_variant, match_type = await smart_test_search(
            processor, original_input
        )

        # Фильтруем результат по типу
        if result:
            filtered = filter_results_by_type([result], show_profiles)
            if not filtered:
                result = None

        if current_task and current_task.cancelled():
            raise asyncio.CancelledError()

        if not result:
            # Ищем похожие тесты с фильтрацией по типу
            similar_tests = await fuzzy_test_search(
                processor, normalized_input, threshold=30
            )

            # Фильтруем по типу
            similar_tests = filter_results_by_type(similar_tests, show_profiles)

            if animation_task:
                animation_task.cancel()
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)

            await db.add_search_history(
                user_id=user_id,
                search_query=original_query,
                search_type="code",
                success=False,
            )

            if similar_tests:
                # Показываем найденные варианты с пагинацией
                import hashlib
                from datetime import datetime
                
                search_id = hashlib.md5(
                    f"{user_id}_{datetime.now().isoformat()}_similar_{normalized_input}".encode()
                ).hexdigest()[:8]
                
                # Сохраняем только Document объекты (без scores)
                similar_docs = [doc for doc, _ in similar_tests]
                await state.update_data(**{f"search_results_{search_id}": similar_docs})
                
                # Очищаем старые результаты
                await cleanup_old_search_results(state)
                
                # Создаем клавиатуру с пагинацией
                keyboard, total_pages, items_shown = create_paginated_keyboard(
                    similar_docs,
                    current_page=0,
                    items_per_page=6,
                    search_id=search_id
                )
                
                response = (
                    f"❌ {search_type.capitalize()} с кодом '<code>{normalized_input}</code>' не найден.\n\n"
                    f"🔍 <b>Найдены похожие {search_type} ({len(similar_tests)} шт.)</b>"
                )
                
                if total_pages > 1:
                    response += f" <b>(страница 1 из {total_pages}):</b>\n\n"
                else:
                    response += ":\n\n"
                
                # Показываем первые элементы
                for i, (doc, score) in enumerate(similar_tests[:items_shown], 1):
                    test_data = format_test_data(doc.metadata)
                    test_code = sanitize_test_code_for_display(test_data["test_code"])
                    test_name = html.escape(test_data["test_name"])
                    
                    link = create_test_link(test_code)
                    response += (
                        f"<b>{i}.</b> <a href='{link}'>{test_code}</a> - {test_name}\n"
                        f"   📊 Схожесть: {score}%\n\n"
                    )
                
                response += "\n💡 <i>Нажмите на код теста или используйте кнопки для выбора</i>"
                
                if total_pages > 1:
                    response += f"\n📄 <i>Используйте навигацию для просмотра всех результатов</i>"
                
                await message.answer(
                    response,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=keyboard
                )
            else:
                # Ничего не найдено
                error_msg = f"❌ {search_type.capitalize()} с кодом '{normalized_input}' не найден.\n"
                if show_profiles:
                    error_msg += "💡 Попробуйте поиск без указания 'профили' для обычных тестов."
                else:
                    error_msg += "💡 Добавьте слово 'профили' для поиска профилей тестов."
                await message.answer(error_msg, reply_markup=get_back_to_menu_kb())

            await state.set_state(QuestionStates.waiting_for_search_type)
            await state.update_data(show_profiles=False, search_text=None)
            return

        # Найден точный результат - показываем подробную информацию
        doc = result[0]
        test_data = format_test_data(doc.metadata)

        # Добавляем информацию о типе
        type_info = ""
        if is_profile_test(test_data["test_code"]):
            type_info = "🔬 <b>Это профиль тестов</b>\n\n"

        response = type_info + format_test_info(test_data)

        # Записываем в историю
        await db.add_search_history(
            user_id=user_id,
            search_query=original_query,
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

        # Добавляем похожие тесты
        similar_tests = await fuzzy_test_search(
            processor, test_data["test_code"], threshold=40
        )

        # Фильтруем по типу
        is_profile = is_profile_test(test_data["test_code"])
        similar_tests = filter_results_by_type(similar_tests, is_profile)
        similar_tests = [
            (d, s)
            for d, s in similar_tests
            if d.metadata.get("test_code") != test_data["test_code"]
        ]

        # Если похожих тестов много - готовим пагинацию
        if len(similar_tests) > 5:
            import hashlib
            from datetime import datetime
            
            similar_search_id = hashlib.md5(
                f"{user_id}_{datetime.now().isoformat()}_related_{test_data['test_code']}".encode()
            ).hexdigest()[:8]
            
            similar_docs = [doc for doc, _ in similar_tests]
            await state.update_data(**{f"search_results_{similar_search_id}": similar_docs})
            
            # Показываем первые 5 в основном сообщении
            response += format_similar_tests_with_links(similar_tests[:5])
            response += f"\n\n<i>Всего найдено {len(similar_tests)} похожих тестов</i>"
            
            # Можно добавить кнопку "Показать все похожие"
            # Это будет отдельное сообщение с пагинацией
        elif similar_tests:
            response += format_similar_tests_with_links(similar_tests)

        # Отправляем информацию с фото
        await send_test_info_with_photo(message, test_data, response)

        # Обновляем связанные тесты
        if "last_viewed_test" in data and data["last_viewed_test"] != test_data["test_code"]:
            await db.update_related_tests(
                user_id=user_id,
                test_code_1=data["last_viewed_test"],
                test_code_2=test_data["test_code"],
            )

        # Если есть много похожих тестов, показываем кнопку для их просмотра
        if len(similar_tests) > 5:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"📋 Показать все похожие тесты ({len(similar_tests)})",
                            callback_data=f"show_all_similar:{similar_search_id}"
                        )
                    ]
                ]
            )
            await message.answer(
                "Найдено больше похожих тестов:",
                reply_markup=keyboard
            )

        # Обновляем состояние
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(
            current_test=test_data,
            last_viewed_test=test_data["test_code"],
            show_profiles=False,
            search_text=None
        )

        # Показываем клавиатуру для продолжения диалога
        await message.answer(
            "Можете задать вопрос об этом тесте или выбрать действие:",
            reply_markup=get_dialog_kb()
        )

    except asyncio.CancelledError:
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        await message.answer("⏹ Поиск остановлен.", reply_markup=get_back_to_menu_kb())

    except Exception as e:
        print(f"[ERROR] Code search failed: {e}")
        import traceback
        traceback.print_exc()

        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)

        await message.answer(
            "⚠️ Ошибка при поиске. Попробуйте позже",
            reply_markup=get_back_to_menu_kb()
        )
        await state.set_state(QuestionStates.waiting_for_search_type)
        await state.update_data(show_profiles=False, search_text=None)

    finally:
        await state.update_data(is_processing=False, current_task=None)

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
