from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from langchain.schema import SystemMessage, HumanMessage, Document
import asyncio
import html
from typing import Dict, List, Tuple, Optional, Set
from datetime import datetime
import re
import hashlib
from collections import defaultdict
import logging

from bot.handlers.ultimate_classifier import ultimate_classifier
from bot.handlers.content import create_gallery_keyboard, create_blanks_keyboard
from bot.handlers.query_processing.query_preprocessing import expand_query_with_abbreviations
from bot.handlers.query_processing.animal_filter import animal_filter

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
    get_confirmation_kb, 
    get_search_type_switch_kb
)
from bot.handlers.utils import normalize_container_name, deduplicate_container_names
from bot.handlers.feedback import validate_phone_number, get_phone_kb, format_phone_number, send_callback_email
from bot.handlers.response_ratings import ResponseRatingManager


rating_manager = ResponseRatingManager(db)

# ============================================================================
# КОНСТАНТЫ
# ============================================================================

LOADING_GIF_ID = "CgACAgIAAxkBAAIBFGiBcXtGY7OZvr3-L1dZIBRNqSztAALueAACpqh5Scn4VmIRb4UjNgQ"

# Параметры поиска
FUZZY_SEARCH_THRESHOLD_MIN = 55  # Увеличен с 30 до 55
FUZZY_SEARCH_THRESHOLD_EXACT = 90
TEXT_SEARCH_TOP_K = 80

# Параметры пагинации
ITEMS_PER_PAGE = 6
MAX_SEARCH_RESULTS_IN_STATE = 3  # Количество хранимых поисков
SEARCH_RESULTS_TTL_SECONDS = 1800  # 30 минут

# Параметры LLM
LLM_TIMEOUT_SECONDS = 30

# Пороги уверенности классификатора
CONFIDENCE_HIGH = 0.85
CONFIDENCE_MEDIUM = 0.70

# Настройки логирования
logger = logging.getLogger(__name__)

# ============================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================================================

questions_router = Router()

# Lock'и для предотвращения race conditions
user_processing_locks = defaultdict(asyncio.Lock)

# Кеш для категорий тестов (оптимизация)
TEST_CATEGORY_KEYWORDS = {
    "биохимия": {"биохим", "алт", "аст", "креатинин", "мочевина", "глюкоза"},
    "гематология": {"оак", "общий анализ крови", "гемоглобин", "эритроциты", "лейкоциты"},
    "гормоны": {"ттг", "т3", "т4", "кортизол", "тестостерон"},
    "инфекции": {"пцр", "ифа", "антитела", "вирус", "бактерии"},
    "моча": {"моча", "оам", "общий анализ мочи"},
}

# Плоский set для быстрого поиска
ALL_TEST_KEYWORDS = set()
for keywords in TEST_CATEGORY_KEYWORDS.values():
    ALL_TEST_KEYWORDS.update(keywords)

# Ключевые слова для общих вопросов
GENERAL_QUESTION_KEYWORDS = {
    'как', 'что', 'где', 'когда', 'почему', 'зачем', 'сколько',
    'хранить', 'хранение', 'транспортировка', 'подготовка', 'правила',
    'можно ли', 'нужно ли', 'должен ли', 'следует ли',
    'температура', 'время', 'срок', 'условия',
    'рекомендации', 'советы', 'инструкция'
}

# Ключевые слова для нерелевантных вопросов
OFF_TOPIC_KEYWORDS = {
    'человек', 'люди', 'доктор', 'больница', 'поликлиника', 'терапевт',
    'цена', 'стоимость', 'купить', 'продать', 'заказ', 'доставка',
    'оплата', 'прайс', 'сколько стоит', 'тариф', 'услуг', 'заказать',
    'график работы', 'часы работы', 'адрес', 'ваканс', 'работа',
    'сайт', 'приложение', 'техническ', 'баг', 'ошибка',
    'погода', 'новости', 'политика', 'спорт', 'кино', 'музыка',
}

# ============================================================================
# FSM STATES
# ============================================================================

class QuestionStates(StatesGroup):
    waiting_for_search_type = State()
    waiting_for_code = State()
    waiting_for_name = State()
    processing = State()
    clarifying_search = State()
    confirming_search_type = State()
    waiting_for_phone = State()
    waiting_for_message = State()
    waiting_for_comment = State()



# ============================================================================
# CALLBACK HELPERS
# ============================================================================

class TestCallback:
    """Безопасная работа с callback data для тестов"""
    
    @staticmethod
    def pack(action: str, test_code: str) -> str:
        """Упаковка callback данных с защитой от превышения лимита"""
        # Обработка проблемного теста
        if "AN520" in test_code and "," in test_code:
            test_code = "AN520ГИЭ"
        
        # Формируем callback
        callback_data = f"{action}:{test_code}"
        
        # Telegram лимит: 64 байта
        if len(callback_data.encode('utf-8')) > 64:
            # Создаем короткий хеш
            test_hash = hashlib.md5(test_code.encode()).hexdigest()[:8]
            callback_data = f"{action}:h_{test_hash}"
            logger.warning(f"Test code too long, using hash: {test_code} -> {test_hash}")
        
        return callback_data

    @staticmethod
    def unpack(callback_data: str) -> Tuple[str, str]:
        """Распаковка callback данных"""
        parts = callback_data.split(":", 1)
        action = parts[0] if len(parts) > 0 else ""
        test_code = parts[1] if len(parts) > 1 else ""
        return action, test_code


class PaginationCallback:
    """Работа с callback данными пагинации"""
    
    @staticmethod
    def pack(action: str, page: int, search_id: str, view_type: str = "all") -> str:
        return f"page:{action}:{page}:{search_id}:{view_type}"
    
    @staticmethod
    def unpack(callback_data: str) -> Tuple[str, int, str, str]:
        parts = callback_data.split(":", 4)
        action = parts[1] if len(parts) > 1 else ""
        page = int(parts[2]) if len(parts) > 2 else 0
        search_id = parts[3] if len(parts) > 3 else ""
        view_type = parts[4] if len(parts) > 4 else "all"
        return action, page, search_id, view_type

# ============================================================================
# УТИЛИТЫ
# ============================================================================

def sanitize_test_code_for_display(test_code: str) -> str:
    """Обрезает слишком длинные коды тестов для корректного отображения"""
    if not test_code:
        return test_code
    
    # Специальная обработка проблемного теста
    if "AN520" in test_code and "," in test_code:
        return "AN520ГИЭ"
    
    # Обрезаем длинные коды
    if len(test_code) > 20:
        return test_code[:17] + "..."
    
    return test_code


def _rerank_hits_by_query(hits: List[Tuple[Document, float]], query: str) -> List[Tuple[Document, float]]:
    """Перераспределение результатов на основе соответствия запросу"""
    hits.sort(key=lambda x: x[1], reverse=True)
    return hits


async def apply_animal_filter(
    results: List[Tuple[Document, float]], 
    query: str
) -> Tuple[List[Tuple[Document, float]], Set[str]]:
    """
    Применяет фильтр по типам животных к результатам поиска
    
    Returns:
        Tuple[filtered_results, animal_types]
    """
    animal_types = animal_filter.extract_animals_from_query(query)
    
    if not animal_types:
        return results, set()
    
    logger.info(f"[ANIMAL FILTER] Found animals: {animal_types}")
    filtered = animal_filter.filter_tests_by_animals(results, animal_types)
    logger.info(f"[ANIMAL FILTER] Filtered: {len(results)} → {len(filtered)}")
    
    return filtered, animal_types


async def cleanup_old_search_results(
    state: FSMContext, 
    max_age_seconds: int = SEARCH_RESULTS_TTL_SECONDS,
    keep_last: int = MAX_SEARCH_RESULTS_IN_STATE
):
    """
    Очищает старые результаты поиска из состояния
    
    Args:
        state: FSM контекст
        max_age_seconds: Максимальный возраст результатов в секундах
        keep_last: Сколько последних результатов сохранять
    """
    data = await state.get_data()
    now = datetime.now().timestamp()
    
    search_results = {}
    
    # Собираем все результаты с их временем
    for key, value in data.items():
        if key.startswith("search_results_"):
            if isinstance(value, dict) and 'timestamp' in value:
                search_results[key] = value
    
    # Сортируем по времени
    sorted_results = sorted(
        search_results.items(),
        key=lambda x: x[1].get('timestamp', 0),
        reverse=True
    )
    
    # Определяем, что удалять
    to_delete = []
    
    for i, (key, value) in enumerate(sorted_results):
        # Удаляем старые результаты
        if now - value.get('timestamp', 0) > max_age_seconds:
            to_delete.append(key)
        # Удаляем лишние (сверх лимита)
        elif i >= keep_last:
            to_delete.append(key)
    
    # Удаляем
    if to_delete:
        logger.info(f"[CLEANUP] Removing {len(to_delete)} old search results")
        await state.update_data(**{k: None for k in to_delete})


def create_mock_message(original_message, text: str):
    """
    Создает полнофункциональный mock сообщение
    
    ВНИМАНИЕ: Используется для callback → текстовый обработчик
    В идеале нужно рефакторить и избегать mock объектов
    """
    bot = getattr(original_message, 'bot', None)
    
    class MockMessage:
        def __init__(self):
            self.text = text
            self.from_user = original_message.from_user
            self.chat = original_message.chat
            self.message_id = getattr(original_message, 'message_id', None)
            self.bot = bot
        
        async def answer_animation(self, animation, caption="", reply_markup=None):
            if self.bot:
                return await self.bot.send_animation(
                    chat_id=self.chat.id,
                    animation=animation,
                    caption=caption,
                    reply_markup=reply_markup
                )
        
        async def answer(self, text, reply_markup=None, parse_mode=None, 
                        disable_web_page_preview=None):
            if self.bot:
                return await self.bot.send_message(
                    chat_id=self.chat.id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
        
        async def answer_photo(self, photo, caption="", reply_markup=None, parse_mode=None):
            if self.bot:
                return await self.bot.send_photo(
                    chat_id=self.chat.id,
                    photo=photo,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        
        async def reply(self, text, reply_markup=None, parse_mode=None):
            if self.bot:
                return await self.bot.send_message(
                    chat_id=self.chat.id,
                    text=text,
                    reply_to_message_id=self.message_id,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        
        async def edit_text(self, text, reply_markup=None, parse_mode=None,
                           disable_web_page_preview=None):
            if self.bot and self.message_id:
                return await self.bot.edit_message_text(
                    chat_id=self.chat.id,
                    message_id=self.message_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
    
    return MockMessage()


async def safe_cancel_animation(animation_task: Optional[asyncio.Task]):
    """Безопасная отмена задачи анимации"""
    if animation_task and not animation_task.done():
        animation_task.cancel()
        try:
            await animation_task
        except asyncio.CancelledError:
            pass  # Ожидаемое исключение
        except Exception as e:
            logger.warning(f"[ANIMATION] Error during cancel: {e}")


async def find_container_photo_smart(db, container_type: str):
    """
    Умный поиск фото контейнера с учетом вариантов в БД
    """
    is_test_tube = "пробирк" in container_type.lower()
    is_container = "контейнер" in container_type.lower()
    
    # Сначала точный поиск
    photo = await db.get_container_photo(container_type)
    if photo:
        photo['display_name'] = photo.get('container_type', container_type)
        return photo
    
    # Генерируем варианты для поиска
    search_variants = []
    
    # Варианты с числами
    if not re.match(r'^\d+\s', container_type):
        search_variants.extend([
            f"2 {container_type.replace('Пробирка', 'Пробирки')}",
            f"3 {container_type.replace('Пробирка', 'Пробирки')}",
            container_type
        ])
    else:
        search_variants.append(container_type)
    
    # Варианты регистра для "с"
    for variant in search_variants[:]:
        upper_variant = re.sub(r'\bс\s+', 'С ', variant)
        if upper_variant != variant:
            search_variants.append(upper_variant)
        
        lower_variant = re.sub(r'\bС\s+', 'с ', variant)
        if lower_variant != variant:
            search_variants.append(lower_variant)
    
    # Пробуем все варианты
    for variant in search_variants:
        photo = await db.get_container_photo(variant)
        if photo:
            photo['display_name'] = photo.get('container_type', container_type)
            return photo
    
    return None

# ============================================================================
# КЛАВИАТУРЫ
# ============================================================================

def create_paginated_keyboard(
    tests: List[Dict],  # Изменено: теперь список Dict, а не Document
    current_page: int = 0,
    items_per_page: int = ITEMS_PER_PAGE,
    search_id: str = "",
    include_filters: bool = True,
    tests_count: int = 0,
    profiles_count: int = 0,
    total_count: int = 0,
    current_view: str = "all"
) -> Tuple[InlineKeyboardMarkup, int, int]:
    """
    Создает клавиатуру с пагинацией для результатов поиска
    
    Args:
        tests: Список словарей с metadata тестов
        current_page: Текущая страница
        items_per_page: Элементов на странице
        search_id: ID поиска для callback
        include_filters: Показывать ли фильтры
        tests_count: Количество обычных тестов
        profiles_count: Количество профилей
        total_count: Общее количество
        current_view: Текущий вид (all/tests/profiles)
    
    Returns:
        Tuple[клавиатура, количество_страниц, показано_элементов]
    """
    total_items = len(tests)
    total_pages = (total_items + items_per_page - 1) // items_per_page
    
    start_idx = current_page * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    
    keyboard = []
    
    # Кнопки фильтрации
    if include_filters and (tests_count + profiles_count + total_count) > 0:
        filter_row = [
            InlineKeyboardButton(
                text=f"🧪 Тесты ({tests_count})",
                callback_data=f"switch_view:tests:{search_id}"
            ),
            InlineKeyboardButton(
                text=f"🔬 Профили ({profiles_count})",
                callback_data=f"switch_view:profiles:{search_id}"
            ),
            InlineKeyboardButton(
                text=f"📋 Все ({total_count})",
                callback_data=f"switch_view:all:{search_id}"
            )
        ]
        keyboard.append(filter_row)
    
    # Кнопки тестов (по 3 в ряд)
    row = []
    for item in tests[start_idx:end_idx]:
        # Извлекаем test_code из metadata
        metadata = item.get('metadata', item)  # На случай разных структур
        test_code = metadata.get('test_code', '')
        
        if not test_code:
            continue
        
        button_text = sanitize_test_code_for_display(test_code)
        
        row.append(
            InlineKeyboardButton(
                text=button_text,
                callback_data=TestCallback.pack("show_test", test_code)
            )
        )
        
        if len(row) >= 3:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    # Навигация
    if total_pages > 1:
        nav_row = []
        
        if current_page > 0:
            nav_row.append(
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data=PaginationCallback.pack("prev", current_page - 1, search_id, current_view)
                )
            )
        
        nav_row.append(
            InlineKeyboardButton(
                text=f"📄 {current_page + 1}/{total_pages}",
                callback_data="ignore"
            )
        )
        
        if current_page < total_pages - 1:
            nav_row.append(
                InlineKeyboardButton(
                    text="Вперед ▶️",
                    callback_data=PaginationCallback.pack("next", current_page + 1, search_id, current_view)
                )
            )
        
        keyboard.append(nav_row)
    
    # # Кнопка закрытия
    # keyboard.append([
    #     InlineKeyboardButton(
    #         text="❌ Закрыть",
    #         callback_data="close_keyboard"
    #     )
    # ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard), total_pages, end_idx - start_idx


def _get_callback_support_keyboard(question: str = "") -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой для заказа звонка"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📞 Позвонить специалисту",
                    callback_data="redirect_to_callback"
                )
            ]
        ]
    )

# ============================================================================
# ПРОВЕРКИ И ВАЛИДАЦИЯ
# ============================================================================

async def _is_off_topic_question(question: str) -> bool:
    """Определяет, относится ли вопрос к нерелевантной тематике"""
    question_lower = question.lower()
    
    # Проверка на нерелевантные ключевые слова
    if any(keyword in question_lower for keyword in OFF_TOPIC_KEYWORDS):
        return True
    
    # Ветеринарные, но не лабораторные темы
    non_lab_vet_topics = {
        'корм', 'питание', 'лечение', 'препарат', 'лекарств', 'таблетк',
        'операция', 'хирург', 'прививк', 'вакцин', 'усыплен', 'стерилизация',
        'кастрация', 'диагноз', 'болезнь', 'симптом', 'ветеринар', 'клиник',
        'осмотр', 'консультация', 'рецепт'
    }
    
    # Лабораторные ключевые слова
    lab_keywords = {
        'анализ', 'тест', 'лаборатор', 'биоматериал', 'кров', 'моч', 'кал',
        'исследование', 'проба', 'образец', 'контейнер', 'транспортировка',
        'хранение', 'преаналитик', 'диагностик', 'an', 'ан'
    }
    
    if any(topic in question_lower for topic in non_lab_vet_topics):
        has_lab_context = any(word in question_lower for word in lab_keywords)
        return not has_lab_context
    
    return False


async def _is_unhelpful_answer(answer: str, question: str) -> bool:
    """Определяет, является ли ответ неинформативным"""
    answer_lower = answer.lower()
    
    unhelpful_phrases = {
        "не могу найти информацию", "не располагаю данными", 
        "не имею информации", "не могу ответить",
        "обратитесь к специалисту", "не уверен в ответе",
        "не могу дать точный ответ", "информация отсутствует",
        "не нашел данных", "не могу помочь с этим вопросом",
        "не входит в мою компетенцию", "не могу предоставить информацию",
        "не удалось найти ответ", "не понимаю вопрос",
        "уточните вопрос", "переформулируйте вопрос"
    }
    
    if any(phrase in answer_lower for phrase in unhelpful_phrases):
        return True
    
    # Слишком короткий ответ с упоминанием ограничений
    if len(answer.split()) < 25:
        limitation_words = {'ограничен', 'ограничения', 'контекст', 'специалист', 'уточнить'}
        if any(word in answer_lower for word in limitation_words):
            return True
    
    # Много извинений
    apology_words = ['извините', 'сожалею', 'к сожалению', 'unfortunately']
    apology_count = sum(1 for word in apology_words if word in answer_lower)
    if apology_count >= 2 and len(answer.split()) < 40:
        return True
    
    return False

async def _contains_specialist_recommendation(answer: str) -> bool:
    """Проверяет, содержит ли ответ рекомендацию обратиться к специалисту"""
    specialist_phrases = {
        'обратитесь к специалисту',
        'обратиться к специалисту',
        'свяжитесь со специалистом',
        'связаться со специалистом',
        'позвоните специалисту',
        'позвонить специалисту',
        'проконсультируйтесь',
        'консультация специалиста',
        'рекомендую обратиться',
        'рекомендую связаться',
        'рекомендую позвонить',
        'обратитесь в лабораторию',
        'свяжитесь с лабораторией',
        'направляю к специалисту',
        'необходима консультация',
    }
    
    answer_lower = answer.lower()
    return any(phrase in answer_lower for phrase in specialist_phrases)

async def _should_initiate_new_search(
    text: str, 
    current_test_data: Optional[Dict], 
    query_type: str, 
    confidence: float
) -> bool:
    """Всегда начинаем новый поиск"""
    return True  # Всегда True вместо сложной логики

async def _contains_other_test_code(text: str, current_test_code: str) -> bool:
    """Проверяет, содержит ли текст код другого теста"""
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
            if normalized and normalized.upper() != current_test_code.upper():
                found_codes.add(normalized)
    
    return len(found_codes) > 0

# ============================================================================
# ОСНОВНЫЕ ОБРАБОТЧИКИ СООБЩЕНИЙ
# ============================================================================

@questions_router.message(F.text == "🔬 Задать вопрос ассистенту")
async def start_question(message: Message, state: FSMContext):
    """Начало диалога с ассистентом"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)

    if not user:
        await message.answer(
            "Для использования этой функции необходимо пройти регистрацию.\n"
            "Используйте команду /start"
        )
        return

    user_name = get_user_first_name(user)

    prompt = f"""Привет, {user_name} 👋

🔬 Я ассистент ветеринарной лаборатории VetUnion и помогу вам найти информацию о:

📋 <b>Лабораторных тестах и анализах:</b>
• По коду теста (например: AN116, ан116, АН116 или просто 116)
• По названию или описанию (например: "общий анализ крови", "биохимия")

🧪 <b>Преаналитических требованиях:</b>
• Подготовка пациента
• Правила взятия биоматериала
• Условия хранения и транспортировки
• Типы контейнеров для проб

💡 <b>Как мне задать вопрос:</b>
• Введите код теста: <code>AN116</code> или <code>116</code>
• Опишите, что ищете: "анализ на глюкозу"

Я автоматически определю тип вашего запроса и найду нужную информацию.

✏️ Просто напишите ваш вопрос или код теста:"""

    await db.clear_buffer(user_id)
    await message.answer(prompt, reply_markup=get_back_to_menu_kb(), parse_mode="HTML")
    await state.set_state(QuestionStates.waiting_for_search_type)


@questions_router.message(F.text == "❌ Завершить диалог")
async def handle_end_dialog(message: Message, state: FSMContext):
    """Завершение диалога с ботом"""
    await state.clear()
    user = await db.get_user(message.from_user.id)
    role = user.get("role", "user") if user else "user"
    user_name = get_user_first_name(user)
    
    farewell = get_time_based_farewell(user_name)
    await message.answer(farewell, reply_markup=get_menu_by_role(role))

@questions_router.message(QuestionStates.waiting_for_search_type, F.text == "🖼️ Галерея пробирок и контейнеров")
async def show_gallery_in_dialog(message: Message, state: FSMContext):
    """Показывает галерею во время диалога"""
    items = await db.get_all_gallery_items()
    
    if not items:
        # Отправляем временное сообщение, которое само исчезнет
        temp_msg = await message.answer(
            "📭 Галерея пока пуста.\n"
            "Администратор скоро добавит фотографии."
        )
        # Удаляем временное сообщение через 3 секунды
        await asyncio.sleep(3)
        try:
            await temp_msg.delete()
        except:
            pass
        return
    
    # Отправляем галерею как отдельное сообщение с inline клавиатурой
    await message.answer(
        "🖼️ <b>Галерея пробирок и контейнеров</b>\n\n"
        "Выберите интересующий вас элемент:",
        parse_mode="HTML",
        reply_markup=create_gallery_keyboard(items)
    )
    # Не меняем состояние и не отправляем дополнительные сообщения

@questions_router.message(QuestionStates.waiting_for_search_type, F.text == "📄 Ссылки на бланки")
async def show_blanks_in_dialog(message: Message, state: FSMContext):
    """Показывает ссылки на бланки во время диалога"""
    items = await db.get_all_blank_links()
    
    if not items:
        # Отправляем временное сообщение
        temp_msg = await message.answer(
            "📭 Список бланков пока пуст.\n"
            "Администратор скоро добавит ссылки."
        )
        # Удаляем через 3 секунды
        await asyncio.sleep(3)
        try:
            await temp_msg.delete()
        except:
            pass
        return
    
    # Формируем текст с описаниями
    text = "📄 <b>Ссылки на бланки и документы</b>\n\n"
    
    has_descriptions = any(item.get('description') for item in items)
    
    if has_descriptions:
        for i, item in enumerate(items, 1):
            text += f"<b>{html.escape(item['title'])}</b>"
            if item.get('description'):
                text += f"\n📝 {html.escape(item['description'])}"
            text += "\n\n"
    
    text += "👆 <i>Нажмите на кнопку для перехода к документу</i>"
    
    # Отправляем список бланков
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=create_blanks_keyboard(items),
        disable_web_page_preview=True
    )
    # Не отправляем дополнительные сообщения

# Аналогично обновите обработчики для других состояний:
@questions_router.message(QuestionStates.waiting_for_code, F.text == "🖼️ Галерея пробирок и контейнеров")
async def show_gallery_in_code_state(message: Message, state: FSMContext):
    """Показывает галерею при поиске по коду"""
    await show_gallery_in_dialog(message, state)
    # НЕ меняем состояние автоматически

@questions_router.message(QuestionStates.waiting_for_code, F.text == "📄 Ссылки на бланки")
async def show_blanks_in_code_state(message: Message, state: FSMContext):
    """Показывает бланки при поиске по коду"""
    await show_blanks_in_dialog(message, state)
    # НЕ меняем состояние автоматически

@questions_router.message(QuestionStates.waiting_for_name, F.text == "🖼️ Галерея пробирок и контейнеров")
async def show_gallery_in_name_state(message: Message, state: FSMContext):
    """Показывает галерею при поиске по названию"""
    await show_gallery_in_dialog(message, state)
    # НЕ меняем состояние автоматически

@questions_router.message(QuestionStates.waiting_for_name, F.text == "📄 Ссылки на бланки")
async def show_blanks_in_name_state(message: Message, state: FSMContext):
    """Показывает бланки при поиске по названию"""
    await show_blanks_in_dialog(message, state)

@questions_router.message(QuestionStates.waiting_for_search_type)
async def handle_universal_search(message: Message, state: FSMContext):
    """Универсальный обработчик запросов - автоматически определяет тип поиска"""
    text = message.text.strip()
    user_id = message.from_user.id

    # Игнорируем служебные кнопки
    if text in ("🔙 Вернуться в главное меню", "❌ Завершить диалог"):
        return

    # ============================================================
    # Сохраняем флаг того, что это запрос с классификацией
    # ============================================================
    await state.update_data(
        is_classification_flow=True,  # Флаг что это запрос с определением типа
        original_user_query=text      # Сохраняем оригинальный запрос
    )

    # ============================================================
    # ПРИОРИТЕТ 1: Проверка на явный общий вопрос
    # ============================================================
    
    text_lower = text.lower()
    
    # Проверяем, является ли это явным вопросом
    is_obvious_question = (
        text.strip().endswith('?') or 
        any(text_lower.startswith(q + ' ') or f' {q} ' in text_lower for q in [
            'как', 'что', 'где', 'когда', 'почему', 'зачем', 
            'какой', 'какая', 'какие', 'можно ли', 'нужно ли',
            'должен ли', 'следует ли', 'сколько'
        ])
    )
    
    # Проверяем наличие вопросительных ключевых слов
    has_question_keywords = any(keyword in text_lower for keyword in GENERAL_QUESTION_KEYWORDS)
    
    # Если это явный вопрос ИЛИ содержит вопросительные слова
    # то обрабатываем как общий вопрос, ДАЖЕ если там есть код теста
    if is_obvious_question or has_question_keywords:
        logger.info(f"[PRE-CHECK] General question with context detected: {text}")
        
        expanded_query = expand_query_with_abbreviations(text)
        await db.add_request_stat(
            user_id=user_id, request_type="question", request_text=text
        )
        await handle_general_question(message, state, expanded_query)
        return
    
    # ============================================================
    # ПРИОРИТЕТ 2: Проверка на код теста (ТОЛЬКО если нет вопросительного контекста)
    # ============================================================
    
    if is_test_code_pattern(text):
        logger.info(f"[PRE-CHECK] Pure test code pattern detected: {text}")
        expanded_query = expand_query_with_abbreviations(text)
        
        await state.update_data(
            query_classification={
                "type": "code",
                "confidence": 1.0,
                "metadata": {"detected_by": "pattern_match"},
                "original_query": text
            }
        )
        
        await db.add_request_stat(
            user_id=user_id, request_type="code_search", request_text=text
        )
        
        await state.set_state(QuestionStates.waiting_for_code)
        await handle_code_search_with_text(message, state, expanded_query)
        return

    # ============================================================
    # ПРИОРИТЕТ 3: Классификация через ML
    # ============================================================

    expanded_query = expand_query_with_abbreviations(text)

    # Классификация запроса
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

    logger.info(
        f"[CLASSIFIER] Query: '{text}' | Type: {query_type} | "
        f"Confidence: {confidence:.2f}"
    )

    # Высокая уверенность - сразу обрабатываем
    if confidence > CONFIDENCE_HIGH:
        await _process_confident_query(message, state, query_type, text, metadata)
    # Средняя уверенность - запрашиваем подтверждение
    elif confidence > CONFIDENCE_MEDIUM:
        await _ask_confirmation(message, state, query_type, expanded_query, confidence)
    # Низкая уверенность - нужно уточнение
    else:
        await _clarify_with_llm(message, state, expanded_query, query_type, confidence)



@questions_router.message(QuestionStates.confirming_search_type)
async def handle_search_confirmation(message: Message, state: FSMContext):
    """Обработчик подтверждения типа поиска (для текстовых команд)"""
    await message.answer("Пожалуйста, используйте кнопки выше для выбора действия.")


@questions_router.message(QuestionStates.clarifying_search, F.text)
async def handle_text_input_during_clarification(message: Message, state: FSMContext):
    """Обработчик текстового ввода во время уточнения типа поиска"""
    text = message.text.strip()

    # Служебные кнопки игнорируем
    service_buttons = {
        "🔢 Поиск по коду теста", "📝 Поиск по названию", "❓ Общий вопрос", "❌ Завершить диалог"
    }

    if text and text not in service_buttons:
        # Обрабатываем как новый запрос
        await state.set_state(QuestionStates.waiting_for_search_type)
        await handle_universal_search(message, state)
    else:
        await message.answer("Пожалуйста, используйте кнопки выше для выбора типа поиска.")


@questions_router.message(QuestionStates.clarifying_search)
async def handle_search_clarification(message: Message, state: FSMContext):
    """Обработчик уточнения типа поиска"""
    await message.answer("Пожалуйста, используйте кнопки выше для выбора типа поиска.")

# ============================================================================
# ОБРАБОТЧИКИ CALLBACK QUERIES
# ============================================================================

@questions_router.callback_query(F.data == "new_search")
async def handle_new_search(callback: CallbackQuery, state: FSMContext):
    """Начать новый поиск"""
    await callback.answer()
    await callback.message.answer(
        "💡 Введите код теста или опишите, что вы ищете:",
        reply_markup=get_back_to_menu_kb(),
    )
    await state.set_state(QuestionStates.waiting_for_search_type)

@questions_router.callback_query(F.data == "search_by_code")
async def handle_search_by_code_callback(callback: CallbackQuery, state: FSMContext):
    """Поиск по коду теста"""
    await callback.answer()
    await callback.message.answer(
        "Введите код теста (например, AN5):", 
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(QuestionStates.waiting_for_code)


@questions_router.callback_query(F.data == "search_by_name")
async def handle_search_by_name_callback(callback: CallbackQuery, state: FSMContext):
    """Поиск по названию"""
    await callback.answer()
    await callback.message.answer(
        "Введите название или описание теста:", 
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(QuestionStates.waiting_for_name)


@questions_router.callback_query(F.data.startswith("confirm_search:"))
async def handle_confirm_search_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик inline кнопок подтверждения типа поиска"""
    await callback.answer()
    
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    data = await state.get_data()
    classification = data.get("query_classification", {})
    
    if action == "yes":
        # Очищаем флаги классификации перед обработкой
        await state.update_data(
            requires_confirmation=False,
            requires_clarification=False
        )
        
        query_type = classification.get("type", "general")
        original_query = classification.get("original_query", "")
        expanded_query = original_query

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "✅ Принято! Обрабатываю запрос...", 
            reply_markup=get_dialog_kb()
        )

        mock_msg = create_mock_message(callback.message, original_query)

        if query_type == "code":
            await state.set_state(QuestionStates.waiting_for_code)
            await handle_code_search_with_text(mock_msg, state, original_query)
        elif query_type == "name":
            await state.set_state(QuestionStates.waiting_for_name)
            await handle_name_search_with_text(mock_msg, state, expanded_query)
        elif query_type == "profile":
            await state.set_state(QuestionStates.waiting_for_name)
            await handle_name_search_with_text(mock_msg, state, expanded_query)
        else:
            await db.add_request_stat(
                user_id=user_id, 
                request_type="question", 
                request_text=original_query
            )
            await handle_general_question(mock_msg, state, expanded_query)

    elif action == "no":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("❌ Понятно! Уточните тип поиска:")
        await state.set_state(QuestionStates.clarifying_search)

        original_query = classification.get("original_query", "")
        mock_msg = create_mock_message(callback.message, original_query)
        
        await _clarify_with_llm(
            mock_msg, state,
            original_query,
            classification.get("type", "general"),
            classification.get("confidence", 0.5)
        )


@questions_router.callback_query(F.data.startswith("clarify_search:"))
async def handle_clarify_search_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик inline кнопок уточнения типа поиска"""
    await callback.answer()
    
    search_type = callback.data.split(":")[1]
    user_id = callback.from_user.id
    data = await state.get_data()
    original_query = data.get("query_classification", {}).get("original_query", "")
    expanded_query = original_query

    # Очищаем флаги классификации перед обработкой
    await state.update_data(
        requires_confirmation=False,
        requires_clarification=False
    )

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Ищу как {search_type}...", 
        reply_markup=get_dialog_kb()
    )

    mock_msg = create_mock_message(callback.message, original_query)

    if search_type == "code":
        await state.set_state(QuestionStates.waiting_for_code)
        await handle_code_search_with_text(mock_msg, state, original_query)
    elif search_type == "name":
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search_with_text(mock_msg, state, expanded_query)
    elif search_type == "profile":
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search_with_text(mock_msg, state, expanded_query)
    else:  # general
        await db.add_request_stat(
            user_id=user_id, 
            request_type="question", 
            request_text=original_query
        )
        await handle_general_question(mock_msg, state, expanded_query)



@questions_router.callback_query(F.data.startswith("show_test:"))
async def handle_show_test_callback(callback: CallbackQuery, state: FSMContext):
    """Показать информацию о выбранном тесте"""
    action, test_code = TestCallback.unpack(callback.data)
    await callback.answer()

    try:
        processor = DataProcessor()
        processor.load_vector_store()

        # Поиск теста
        results = processor.search_test(filter_dict={"test_code": test_code})

        if not results:
            normalized_code = normalize_test_code(test_code)
            if normalized_code:
                results = processor.search_test(filter_dict={"test_code": normalized_code})

        if not results:
            logger.warning(f"[CALLBACK] Test {test_code} not found with filter search")
            fuzzy_results = await fuzzy_test_search(
                processor, test_code, threshold=FUZZY_SEARCH_THRESHOLD_EXACT
            )

            if fuzzy_results:
                for doc, score in fuzzy_results:
                    if doc.metadata.get("test_code", "").upper() == test_code.upper():
                        results = [(doc, score)]
                        break

                if not results and fuzzy_results[0][1] >= 90:
                    results = [fuzzy_results[0]]

        if not results:
            result, found_variant, match_type = await smart_test_search(processor, test_code)
            if result:
                results = [result]

        if not results:
            await callback.message.answer(f"❌ Тест {test_code} не найден в базе данных")
            return

        doc = results[0][0] if isinstance(results[0], tuple) else results[0]
        test_data = format_test_data(doc.metadata)

        response = f"<b>Информация о выбранном тесте:</b>\n\n"
        response += format_test_info(test_data)

        # Статистика
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

        # Связанные тесты
        data = await state.get_data()
        if "last_viewed_test" in data and data["last_viewed_test"] != test_data["test_code"]:
            await db.update_related_tests(
                user_id=user_id,
                test_code_1=data["last_viewed_test"],
                test_code_2=test_data["test_code"],
            )

        # Отправляем информацию
        await send_test_info_with_photo(callback.message, test_data, response)
        
        try:
            # Логируем выбор теста из списка
            log_response = f"✅ Выбран тест из списка: {test_data['test_code']} - {test_data['test_name']}"
            
            await db.log_chat_interaction(
                user_id=user_id,
                user_name=callback.from_user.full_name or f"ID{user_id}",
                question=f"Выбор из списка: {test_code}",
                bot_response=log_response,
                request_type='callback_selection',
                search_success=True,
                found_test_code=test_data['test_code']
            )
            logger.info(f"[LOGGING] Callback selection logged for user {user_id}")
        except Exception as e:
            logger.error(f"[LOGGING] Failed to log callback selection: {e}")

        await state.set_state(QuestionStates.waiting_for_search_type)
        await callback.message.answer(
            "Готов к новому вопросу! Введите код теста или опишите, что ищете:",
            reply_markup=get_dialog_kb()
        )

    except Exception as e:
        logger.error(f"[CALLBACK] Failed to show test: {e}", exc_info=True)
        await callback.message.answer("⚠️ Ошибка при загрузке информации о тесте")


@questions_router.callback_query(F.data.startswith("quick_test:"))
async def handle_quick_test_selection(callback: CallbackQuery, state: FSMContext):
    """Быстрый выбор теста из подсказок"""
    test_code = callback.data.split(":")[1]
    
    # Переиспользуем логику show_test
    await handle_show_test_callback(callback, state)


@questions_router.callback_query(F.data.startswith("page:"))
async def handle_pagination(callback: CallbackQuery, state: FSMContext):
    """Обработчик переключения страниц с сохранением фильтрации"""
    await callback.answer()
    
    action, page, search_id, current_view = PaginationCallback.unpack(callback.data)
    
    data = await state.get_data()
    search_data = data.get(f"search_results_{search_id}")
    
    if not search_data:
        await callback.answer("Результаты поиска устарели. Выполните новый поиск.", show_alert=True)
        return
    
    # Извлекаем результаты
    all_results = search_data.get('data', [])
    
    if not all_results:
        await callback.answer("Результаты не найдены", show_alert=True)
        return
    
    # Фильтрация по типу
    if current_view == "tests":
        display_results = [
            item for item in all_results 
            if not is_profile_test(item.get('metadata', {}).get("test_code", ""))
        ]
        view_name = "тесты"
    elif current_view == "profiles":
        display_results = [
            item for item in all_results 
            if is_profile_test(item.get('metadata', {}).get("test_code", ""))
        ]
        view_name = "профили"
    else:
        display_results = all_results
        view_name = "результаты"
    
    # Считаем для кнопок фильтров
    tests_count = sum(
        1 for item in all_results 
        if not is_profile_test(item.get('metadata', {}).get("test_code", ""))
    )
    profiles_count = sum(
        1 for item in all_results 
        if is_profile_test(item.get('metadata', {}).get("test_code", ""))
    )
    total_count = len(all_results)
    
    # Клавиатура
    keyboard, total_pages, items_shown = create_paginated_keyboard(
        display_results,
        current_page=page,
        items_per_page=ITEMS_PER_PAGE,
        search_id=search_id,
        include_filters=True,
        tests_count=tests_count,
        profiles_count=profiles_count,
        total_count=total_count,
        current_view=current_view
    )
    
    # Формируем текст
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + items_shown
    
    response = f"🔍 <b>Найдено {len(display_results)} {view_name}</b>"
    
    if total_pages > 1:
        response += f" <b>(страница {page + 1} из {total_pages}):</b>\n\n"
    else:
        response += ":\n\n"
    
    for i, item in enumerate(display_results[start_idx:end_idx], start=start_idx + 1):
        metadata = item.get('metadata', {})
        score = item.get('score', 0)
        
        test_code = sanitize_test_code_for_display(metadata.get("test_code", ""))
        test_name = html.escape(metadata.get("test_name", ""))
        department = html.escape(metadata.get("department", "Не указано"))
        
        type_label = "🔬 Профиль" if is_profile_test(test_code) else "🧪 Тест"
        link = create_test_link(test_code)
        
        response += (
            f"<b>{i}.</b> {type_label}: <a href='{link}'>{test_code}</a>\n"
            f"📝 {test_name}\n"
            f"📋 {department}\n"
        )
        
        # Показываем score если есть
        if score > 0:
            response += f"📊 Схожесть: {score:.2f}%\n"
        
        response += "\n"
    
    response += "\n💡 <i>Нажмите на код теста или выберите из кнопок ниже</i>"
    
    try:
        await callback.message.edit_text(
            response,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"[PAGINATION] Failed to update message: {e}")
        await callback.answer("Ошибка обновления сообщения", show_alert=True)


@questions_router.callback_query(F.data.startswith("switch_view:"))
async def handle_switch_view(callback: CallbackQuery, state: FSMContext):
    """Переключение между тестами/профилями/все"""
    await callback.answer()
    
    parts = callback.data.split(":")
    view_type = parts[1]
    search_id = parts[2] if len(parts) > 2 else ""
    
    data = await state.get_data()
    search_data = data.get(f"search_results_{search_id}")
    
    if not search_data:
        await callback.answer("Результаты поиска устарели", show_alert=True)
        return
    
    all_results = search_data.get('data', [])
    
    # Фильтрация
    if view_type == "tests":
        filtered_results = [
            item for item in all_results 
            if not is_profile_test(item.get('metadata', {}).get("test_code", ""))
        ]
        view_name = "тесты"
    elif view_type == "profiles":
        filtered_results = [
            item for item in all_results 
            if is_profile_test(item.get('metadata', {}).get("test_code", ""))
        ]
        view_name = "профили"
    else:
        filtered_results = all_results
        view_name = "результаты"
    
    if not filtered_results:
        await callback.answer(f"❌ {view_name.capitalize()} не найдены", show_alert=True)
        return
    
    # Считаем для фильтров
    tests_count = sum(
        1 for item in all_results 
        if not is_profile_test(item.get('metadata', {}).get("test_code", ""))
    )
    profiles_count = sum(
        1 for item in all_results 
        if is_profile_test(item.get('metadata', {}).get("test_code", ""))
    )
    total_count = len(all_results)
    
    # Клавиатура (первая страница)
    keyboard, total_pages, items_shown = create_paginated_keyboard(
        filtered_results,
        current_page=0,
        items_per_page=ITEMS_PER_PAGE,
        search_id=search_id,
        include_filters=True,
        tests_count=tests_count,
        profiles_count=profiles_count,
        total_count=total_count,
        current_view=view_type
    )
    
    # Формируем ответ
    response = f"🔍 <b>Найдено {len(filtered_results)} {view_name}</b>"
    
    if total_pages > 1:
        response += f" <b>(страница 1 из {total_pages}):</b>\n\n"
    else:
        response += ":\n\n"
    
    for i, item in enumerate(filtered_results[:items_shown], 1):
        metadata = item.get('metadata', {})
        score = item.get('score', 0)
        
        test_code = sanitize_test_code_for_display(metadata.get("test_code", ""))
        test_name = html.escape(metadata.get("test_name", ""))
        department = html.escape(metadata.get("department", "Не указано"))
        
        type_label = "🔬 Профиль" if is_profile_test(test_code) else "🧪 Тест"
        link = create_test_link(test_code)
        
        response += (
            f"<b>{i}.</b> {type_label}: <a href='{link}'>{test_code}</a>\n"
            f"📝 {test_name}\n"
            f"📋 {department}\n"
        )
        
        if score > 0:
            response += f"📊 Схожесть: {score:.2f}%\n"
        
        response += "\n"
    
    response += "\n💡 <i>Нажмите на код теста или выберите из кнопок ниже</i>"
    
    try:
        await callback.message.edit_text(
            response,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"[SWITCH_VIEW] Failed: {e}")
        await callback.answer("Ошибка переключения", show_alert=True)


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
        raw_metadata = doc.metadata
        test_data = format_test_data(doc.metadata)

        # Собираем все контейнеры
        all_containers = []
        
        # Функция для разделения контейнеров по "или"
        def split_by_or(container_str: str) -> List[str]:
            """Разделяет строку контейнера по 'или' """
            if " или " in container_str.lower():
                # Разделяем по "или" (учитываем разный регистр)
                parts = re.split(r'\s+или\s+', container_str, flags=re.IGNORECASE)
                return [part.strip() for part in parts if part.strip()]
            return [container_str]
        
        # Парсим primary_container_type
        primary_container = str(raw_metadata.get("primary_container_type", "")).strip()
        if primary_container and primary_container.lower() not in ["не указан", "нет", "-", "", "none", "null"]:
            primary_container = primary_container.replace('"', "").replace("\n", " ")
            primary_container = " ".join(primary_container.split())
            
            if "*I*" in primary_container:
                parts = [ct.strip() for ct in primary_container.split("*I*")]
            else:
                parts = [primary_container]
            
            # Обрабатываем "или" в каждой части
            for part in parts:
                all_containers.extend(split_by_or(part))
        
        # Парсим container_type
        container_type_raw = str(raw_metadata.get("container_type", "")).strip()
        if container_type_raw and container_type_raw.lower() not in ["не указан", "нет", "-", "", "none", "null"]:
            container_type_raw = container_type_raw.replace('"', "").replace("\n", " ")
            container_type_raw = " ".join(container_type_raw.split())
            
            if "*I*" in container_type_raw:
                parts = [ct.strip() for ct in container_type_raw.split("*I*")]
            else:
                parts = [container_type_raw]
            
            # Обрабатываем "или" в каждой части
            for part in parts:
                all_containers.extend(split_by_or(part))
        
        # Функция для нормализации контейнера для сравнения дубликатов
        def normalize_for_comparison(container: str) -> str:
            """Нормализует контейнер для проверки дубликатов"""
            norm = container.lower().strip()
            # Убираем числа в начале (2 пробирки -> пробирки)
            norm = re.sub(r'^\d+\s+', '', norm)
            # Заменяем разные варианты написания на единый формат
            norm = norm.replace(" / ", " ").replace(" + ", " ")
            # Приводим к единственному числу
            norm = norm.replace("пробирки", "пробирка")
            # Убираем множественные пробелы
            norm = " ".join(norm.split())
            return norm
        
        # Дедупликация с учетом эквивалентности
        unique_containers = []
        seen_normalized = set()
        
        for container in all_containers:
            if not container:
                continue
                
            # Для дедупликации используем нормализованную версию
            normalized = normalize_for_comparison(container)
            
            if normalized not in seen_normalized:
                seen_normalized.add(normalized)
                unique_containers.append(container)  # Сохраняем оригинальное написание
        
        if not unique_containers:
            await callback.message.answer("❌ Для этого теста не указаны типы контейнеров")
            return
        
        # Ищем фото для каждого уникального контейнера
        found_photos = []
        already_shown_file_ids = set()
        not_found_containers = []
        
        for container in unique_containers:
            # Варианты для поиска в БД
            search_variants = [
                container,  # Оригинал
                container.replace(" / ", " + "),  # Меняем / на +
                container.replace(" + ", " / "),  # Меняем + на /
            ]
            
            # Добавляем варианты без чисел
            container_no_number = re.sub(r'^\d+\s+', '', container)
            if container_no_number != container:
                search_variants.extend([
                    container_no_number,
                    container_no_number.replace(" / ", " + "),
                    container_no_number.replace(" + ", " / "),
                ])
            
            # Добавляем варианты с единственным числом
            if "пробирки" in container.lower():
                singular = container.replace("пробирки", "пробирка").replace("Пробирки", "Пробирка")
                search_variants.append(singular)
                search_variants.append(re.sub(r'^\d+\s+', '', singular))
            
            photo_data = None
            for variant in search_variants:
                # Сначала точный поиск
                photo_data = await db.get_container_photo(variant)
                if photo_data:
                    break
                    
                # Если не нашли - умный поиск
                if not photo_data:
                    photo_data = await find_container_photo_smart(db, variant)
                    if photo_data:
                        break
            
            if photo_data:
                file_id = photo_data.get("file_id")
                
                # Проверяем дубликаты по file_id
                if file_id not in already_shown_file_ids:
                    already_shown_file_ids.add(file_id)
                    found_photos.append({
                        "container_type": container,  # Используем оригинальное название
                        "file_id": file_id,
                        "description": photo_data.get("description")
                    })
            else:
                # Сохраняем контейнеры, для которых не нашли фото
                not_found_containers.append(container)
        
        # Отправляем найденные фото
        if found_photos:
            if len(found_photos) == 1:
                # Одно фото
                photo_info = found_photos[0]
                container_name = html.escape(photo_info['container_type'])
                caption = f"📦 Контейнер: {container_name}"
                if photo_info.get('description'):
                    description = html.escape(photo_info['description'])
                    caption += f"\n📝 {description}"
                
                hide_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🙈 Скрыть фото",
                                callback_data=f"hide_single:{test_code}",
                            )
                        ]
                    ]
                )
                
                await callback.message.answer_photo(
                    photo=photo_info['file_id'],
                    caption=caption,
                    reply_markup=hide_keyboard
                )
            else:
                # Несколько фото - отправляем каждое отдельно
                sent_messages = []
                
                for i, photo_info in enumerate(found_photos):
                    container_name = html.escape(photo_info['container_type'])
                    
                    # Только название контейнера как подпись
                    caption = f"📦 {container_name}"
                    
                    # Отправляем каждое фото отдельно без кнопок
                    sent_msg = await callback.message.answer_photo(
                        photo=photo_info['file_id'],
                        caption=caption,
                        parse_mode="HTML"
                    )
                    sent_messages.append(sent_msg)
                    
                    # Небольшая задержка между отправками для избежания спама
                    if i < len(found_photos) - 1:
                        await asyncio.sleep(0.3)
                
                # Отправляем общую кнопку для скрытия всех фото
                message_ids = [msg.message_id for msg in sent_messages]
                message_ids_str = ",".join(map(str, message_ids))
                
                hide_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🙈 Скрыть все фото",
                                callback_data=f"hide_multiple:{message_ids_str}",
                            )
                        ]
                    ]
                )
                
                await callback.message.answer(
                    f"Показано {len(found_photos)} фото контейнеров",
                    reply_markup=hide_keyboard
                )
            
            # Если есть контейнеры без фото, сообщаем об этом
            if not_found_containers:
                not_found_msg = "\n⚠️ Не найдены фото для:\n"
                for ct in not_found_containers[:5]:
                    not_found_msg += f"• {ct}\n"
                if len(not_found_containers) > 5:
                    not_found_msg += f"... и еще {len(not_found_containers) - 5}"
                
                await callback.message.answer(not_found_msg)
                
        else:
            # Все контейнеры не найдены
            not_found_msg = "❌ Фото контейнеров не найдены в базе\n\n"
            not_found_msg += "🔍 Искали типы:\n"
            for ct in unique_containers[:10]:
                not_found_msg += f"• {ct}\n"
            if len(unique_containers) > 10:
                not_found_msg += f"... и еще {len(unique_containers) - 10}"
            
            await callback.message.answer(not_found_msg)

    except Exception as e:
        print(f"[ERROR] Failed to show container photos: {e}")
        import traceback
        traceback.print_exc()
        await callback.message.answer("❌ Ошибка при загрузке фото")


@questions_router.callback_query(F.data.startswith("hide_single:"))
async def handle_hide_single_photo(callback: CallbackQuery):
    """Скрыть одиночное фото"""
    await callback.answer("Фото скрыто")
    
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"[HIDE_PHOTO] Failed: {e}")


@questions_router.callback_query(F.data.startswith("hide_multiple:"))
async def handle_hide_multiple_photos(callback: CallbackQuery):
    """Скрыть несколько фото"""
    await callback.answer("Фото скрыты")
    
    try:
        parts = callback.data.split(":")
        if len(parts) > 1:
            message_ids_str = parts[1]
            message_ids = [int(mid) for mid in message_ids_str.split(",") if mid.isdigit()]
            
            for message_id in message_ids:
                try:
                    await callback.bot.delete_message(
                        chat_id=callback.message.chat.id,
                        message_id=message_id
                    )
                except Exception:
                    continue
        
        await callback.message.delete()
        
    except Exception as e:
        logger.error(f"[HIDE_MULTIPLE] Failed: {e}")
        await callback.answer("Ошибка при скрытии фото", show_alert=True)


@questions_router.callback_query(F.data == "close_keyboard")
async def handle_close_keyboard(callback: CallbackQuery):
    """Закрыть клавиатуру"""
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@questions_router.callback_query(F.data == "ignore")
async def handle_ignore_callback(callback: CallbackQuery):
    """Информационная кнопка"""
    await callback.answer()


@questions_router.callback_query(F.data == "redirect_to_callback")
async def handle_redirect_to_callback(callback: CallbackQuery, state: FSMContext):
    """Перенаправление на заказ звонка"""
    await callback.answer()
    
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.message.answer(
            "Для заказа звонка необходимо пройти регистрацию.\n"
            "Используйте команду /start"
        )
        return

    # Сохраняем контекст диалога для возврата
    
    country = user.get('country', 'BY')
    
    # Обновляем данные, сохраняя предыдущий контекст
    await state.update_data(
        user_country=country,
     )
    
    phone_formats = {
        'BY': "+375 (XX) XXX-XX-XX",
        'RU': "+7 (XXX) XXX-XX-XX", 
        'KZ': "+7 (7XX) XXX-XX-XX",
        'AM': "+374 (XX) XXX-XXX"
    }
    
    format_hint = phone_formats.get(country, phone_formats['BY'])
    
    # Добавляем кнопку отмены для возврата в диалог
    cancel_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отменить и вернуться",
                    callback_data="cancel_callback_return_to_dialog"
                )
            ]
        ]
    )
    
    await callback.message.answer(
        f"📞 Заказ обратного звонка\n\n"
        f"Пожалуйста, отправьте ваш номер телефона или введите вручную.\n"
        f"Формат для вашей страны: {format_hint}",
        reply_markup=get_phone_kb()
    )
    
    # Показываем кнопку отмены
    await callback.message.answer(
        "Или нажмите кнопку ниже, чтобы вернуться в диалог:",
        reply_markup=cancel_keyboard
    )
    
    await state.set_state(QuestionStates.waiting_for_phone)


@questions_router.message(QuestionStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        return

    data = await state.get_data()
    country = data.get('user_country', 'BY')
    phone = ""

    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone
    else:
        phone = message.text
        if not validate_phone_number(phone, country):
            phone_examples = {
                'BY': "375291234567 или +375 29 123-45-67",
                'RU': "79123456789 или +7 912 345-67-89",
                'KZ': "77012345678 или +7 701 234-56-78",
                'AM': "37477123456 или +374 77 123-456"
            }
            example = phone_examples.get(country, phone_examples['BY'])
            
            await message.answer(
                f"❌ Неверный формат номера телефона.\n"
                f"Пожалуйста, введите номер в формате:\n"
                f"{example}",
                reply_markup=get_phone_kb()
            )
            return
        
        phone = format_phone_number(phone, country)

    await state.update_data(phone=phone)
    await message.answer(
        "Отлично! Теперь напишите ваше сообщение.\n"
        "Опишите причину обращения, удобное время для звонка и любую другую важную информацию:",
        reply_markup=get_back_to_menu_kb()
    )
    await state.set_state(QuestionStates.waiting_for_message)


@questions_router.message(QuestionStates.waiting_for_message)
async def process_callback_message(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_dialog_kb())
        print(f"[INFO] User {user_id} cancelled callback message")
        return

    data = await state.get_data()
    phone = data.get('phone')
    user = await db.get_user(user_id)
    
    # Преобразуем Row в словарь
    user_dict = dict(user) if user else {}

    print(f"[INFO] Sending callback email for user {user_id}")
    email_sent = await send_callback_email(user_dict, phone, message.text)

    if email_sent:
        print(f"[INFO] Callback email sent for user {user_id}")
    else:
        print(f"[WARN] Callback email failed for user {user_id}, fallback to acceptance message")

    await db.add_request_stat(user_id, "callback_request", f"Телефон: {phone}, Сообщение: {message.text[:100]}...")
    print(f"[INFO] Callback stat saved for user {user_id}")

    # Обычный flow - если не нужно возвращаться в диалог
    user_role = user['role'] if user else 'user'
    await message.answer(
        "✅ Ваша заявка на обратный звонок успешно отправлена!\n\n"
        f"📞 Телефон: {phone}\n💬 Сообщение: {message.text}\n\n"
        "Наш специалист свяжется с вами в ближайшее время.",
        reply_markup=get_dialog_kb()
    )
    await state.set_state(QuestionStates.waiting_for_search_type)
    print(f"[INFO] State cleared for user {user_id}")


# ============================================================================
# ПОИСК ПО КОДУ
# ============================================================================

@questions_router.callback_query(F.data == "cancel_callback_return_to_dialog")
async def handle_cancel_callback(callback: CallbackQuery, state: FSMContext):
    """Отмена заказа звонка и возврат в диалог"""
    await callback.answer("Возвращаемся в диалог")
    
    data = await state.get_data()
    previous_state = data.get('previous_state')
    current_test = data.get('current_test') or data.get('previous_test_data')
    
    # Возвращаем предыдущее состояние
    if previous_state and previous_state.startswith('QuestionStates:'):
        await state.set_state(previous_state)
    else:
        await state.set_state(QuestionStates.waiting_for_search_type)
    
    try:
        await callback.message.edit_text("❌ Заказ звонка отменен")
    except Exception:
        await callback.message.answer("❌ Заказ звонка отменен")
    
    if current_test:
        await callback.message.answer(
            "✅ Продолжаем диалог.\n\n"
            "Можете задать вопрос об этом тесте или выбрать действие:",
            reply_markup=get_dialog_kb()
        )
    else:
        await callback.message.answer(
            "💡 Что бы вы хотели сделать?",
            reply_markup=get_back_to_menu_kb()
        )

@questions_router.message(QuestionStates.waiting_for_code)
async def handle_code_search(message: Message, state: FSMContext):
    """Обработчик поиска по коду теста"""
    await handle_code_search_with_text(message, state, message.text.strip())


async def handle_code_search_with_text(
    message: Message, 
    state: FSMContext, 
    search_text: str
):
    """Wrapper для поиска по коду"""
    await _handle_code_search_internal(message, state, search_text)


async def _handle_code_search_internal(
    message: Message, 
    state: FSMContext, 
    search_text: Optional[str] = None
):
    """
    Внутренняя функция поиска по коду теста
    
    Исправлено:
    - Добавлен Lock для предотвращения race conditions
    - Корректная обработка animation_task
    - Сохранение минимизированных данных в state
    - Увеличен threshold для fuzzy search
    - Проверка на None после normalize_test_code
    """
    user_id = message.from_user.id
    
    # FIX #18: Атомарная блокировка
    async with user_processing_locks[user_id]:
        data = await state.get_data()
        original_input = search_text if search_text else message.text.strip()
        original_query = data.get("original_query", original_input)

        await db.add_request_stat(
            user_id=user_id, 
            request_type="question", 
            request_text=original_query
        )

        gif_msg = None
        loading_msg = None
        animation_task = None

        try:
            # Загрузка GIF
            try:
                if LOADING_GIF_ID:
                    gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
            except Exception:
                gif_msg = None

            loading_msg = await message.answer("🔍 Ищу по коду...\n⏳ Анализирую данные...")
            
            if loading_msg:
                animation_task = asyncio.create_task(animate_loading(loading_msg))

            processor = DataProcessor()
            processor.load_vector_store()

            # FIX #21: Проверка нормализации
            normalized_input = normalize_test_code(original_input)
            if not normalized_input:
                await safe_cancel_animation(animation_task)
                await safe_delete_message(loading_msg)
                await safe_delete_message(gif_msg)
                
                await message.answer(
                    f"❌ Не удалось распознать код теста: {html.escape(original_input[:50])}",
                    reply_markup=get_back_to_menu_kb(),
                    parse_mode="HTML"
                )
                return

            # Умный поиск
            result, found_variant, match_type = await smart_test_search(
                processor, original_input
            )

            # Фильтр по животным
            animal_types = set()
            if not result:
                animal_types = animal_filter.extract_animals_from_query(original_query)

            # Если не нашли - fuzzy поиск
            if not result:
                # FIX #25: Увеличен threshold
                similar_tests = await fuzzy_test_search(
                    processor, normalized_input, threshold=FUZZY_SEARCH_THRESHOLD_MIN
                )

                # Применяем фильтр по животным
                if animal_types:
                    similar_tests, _ = await apply_animal_filter(similar_tests, original_query)

                await safe_cancel_animation(animation_task)
                await safe_delete_message(loading_msg)
                await safe_delete_message(gif_msg)

                await db.add_search_history(
                    user_id=user_id,
                    search_query=original_query,
                    search_type="code",
                    success=False,
                )

                if similar_tests:
                    # FIX #17 & #19: Сохраняем минимизированные данные СО score
                    search_id = hashlib.md5(
                        f"{user_id}_{datetime.now().timestamp()}_{normalized_input}".encode()
                    ).hexdigest()[:8]
                    
                    simplified_results = [
                        {
                            'metadata': {
                                'test_code': doc.metadata.get('test_code'),
                                'test_name': doc.metadata.get('test_name'),
                                'department': doc.metadata.get('department')
                            },
                            'score': score
                        }
                        for doc, score in similar_tests
                    ]
                    
                    await state.update_data(**{
                        f"search_results_{search_id}": {
                            'data': simplified_results,
                            'timestamp': datetime.now().timestamp(),
                            'query': normalized_input
                        }
                    })
                    
                    await cleanup_old_search_results(state)
                    
                    # Считаем типы
                    tests_count = sum(
                        1 for item in simplified_results 
                        if not is_profile_test(item['metadata'].get('test_code', ''))
                    )
                    profiles_count = sum(
                        1 for item in simplified_results 
                        if is_profile_test(item['metadata'].get('test_code', ''))
                    )
                    
                    keyboard, total_pages, items_shown = create_paginated_keyboard(
                        simplified_results,
                        current_page=0,
                        items_per_page=ITEMS_PER_PAGE,
                        search_id=search_id,
                        include_filters=True,
                        tests_count=tests_count,
                        profiles_count=profiles_count,
                        total_count=len(simplified_results),
                        current_view="all"
                    )
                    
                    response = (
                        f"❌ Точное совпадение для кода '<code>{html.escape(normalized_input)}</code>' не найдено.\n\n"
                    )
                    
                    if animal_types:
                        animal_display = animal_filter.get_animal_display_names(animal_types)
                        response += f"🐾 <b>Фильтр по животным:</b> {animal_display}\n\n"
                    
                    response += f"🔍 <b>Найдены похожие результаты ({len(similar_tests)} шт.)</b>"
                    
                    if total_pages > 1:
                        response += f" <b>(страница 1 из {total_pages}):</b>\n\n"
                    else:
                        response += ":\n\n"
                    
                    # FIX #17: Правильное использование данных со score
                    for i, item in enumerate(simplified_results[:items_shown], 1):
                        metadata = item['metadata']
                        score = item['score']
                        
                        test_code = sanitize_test_code_for_display(metadata['test_code'])
                        test_name = html.escape(metadata['test_name'])
                        
                        type_label = "🔬 Профиль" if is_profile_test(test_code) else "🧪 Тест"
                        link = create_test_link(test_code)
                        
                        response += (
                            f"<b>{i}.</b> {type_label}: <a href='{link}'>{test_code}</a> - {test_name}\n"
                            f"   📊 Схожесть: {score:.2f}%\n\n"
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
                    error_msg = f"❌ Код '<code>{html.escape(normalized_input)}</code>' не найден в базе данных.\n"
                    
                    if animal_types:
                        animal_display = animal_filter.get_animal_display_names(animal_types)
                        error_msg += f"🐾 <b>Фильтр по животным:</b> {animal_display}\n\n"
                    
                    error_msg += "💡 Попробуйте проверить правильность написания кода."
                    
                    await message.answer(
                        error_msg, 
                        reply_markup=get_back_to_menu_kb(), 
                        parse_mode="HTML"
                    )

                await state.set_state(QuestionStates.waiting_for_search_type)
                return

            # Найден точный результат
            doc = result[0]
            test_data = format_test_data(doc.metadata)

            type_info = ""
            if is_profile_test(test_data["test_code"]):
                type_info = "🔬 <b>Это профиль тестов</b>\n\n"

            response = type_info + format_test_info(test_data)

            # Статистика
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

            await safe_cancel_animation(animation_task)
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)

            # Отправляем информацию
            await send_test_info_with_photo(message, test_data, response)
            
            try:
                # Формируем текст ответа для логирования
                log_response = f"✅ Найден тест: {test_data['test_code']}\n\n{response}"
                
                await db.log_chat_interaction(
                    user_id=user_id,
                    user_name=message.from_user.full_name or f"ID{user_id}",
                    question=original_query,
                    bot_response=log_response,
                    request_type='code_search',
                    search_success=True,
                    found_test_code=test_data['test_code']
                )
            except Exception as e:
                logger.error(f"[LOGGING] Failed to log code search: {e}")

            # Связанные тесты
            if "last_viewed_test" in data and data["last_viewed_test"] != test_data["test_code"]:
                await db.update_related_tests(
                    user_id=user_id,
                    test_code_1=data["last_viewed_test"],
                    test_code_2=test_data["test_code"],
                )

            # Обновляем состояние
            await state.set_state(QuestionStates.waiting_for_search_type)
            await message.answer(
                "Готов к новому запросу! Введите код теста или опишите, что ищете:",
                reply_markup=get_dialog_kb()
            )

        except asyncio.CancelledError:
            await safe_cancel_animation(animation_task)
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)
            await message.answer("⏹ Поиск остановлен.", reply_markup=get_back_to_menu_kb())

        except Exception as e:
            logger.error(f"[CODE_SEARCH] Failed: {e}", exc_info=True)
            
            await safe_cancel_animation(animation_task)
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)

            await message.answer(
                "⚠️ Ошибка при поиске. Попробуйте позже",
                reply_markup=get_back_to_menu_kb()
            )
            await state.set_state(QuestionStates.waiting_for_search_type)

# ============================================================================
# ПОИСК ПО НАЗВАНИЮ
# ============================================================================

@questions_router.message(QuestionStates.waiting_for_name)
async def handle_name_search(message: Message, state: FSMContext):
    """Обработчик поиска по названию"""
    await handle_name_search_with_text(message, state, message.text.strip())


async def handle_name_search_with_text(
    message: Message, 
    state: FSMContext, 
    search_text: Optional[str] = None
):
    """Wrapper для поиска по названию"""
    await _handle_name_search_internal(message, state, search_text)


async def _handle_name_search_internal(
    message: Message, 
    state: FSMContext, 
    search_text: Optional[str] = None
):
    """
    Внутренняя функция поиска по названию
    
    Исправлено:
    - Добавлен Lock для предотвращения race conditions
    - Минимизированные данные в state
    - Применение фильтра по животным
    - Корректная обработка animation_task
    """
    user_id = message.from_user.id

    # FIX #18: Атомарная блокировка
    async with user_processing_locks[user_id]:
        data = await state.get_data()
        original_query = data.get("original_query", message.text if not search_text else search_text)
        text = search_text if search_text else message.text.strip()

        await db.add_request_stat(
            user_id=user_id, 
            request_type="question", 
            request_text=original_query
        )

        gif_msg = None
        loading_msg = None
        animation_task = None

        try:
            search_description = "🔍 Ищу тесты по запросу..."

            if LOADING_GIF_ID:
                try:
                    gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
                except Exception:
                    gif_msg = None
                
                loading_msg = await message.answer(
                    f"{search_description}\n⏳ Анализирую данные..."
                )
                animation_task = asyncio.create_task(animate_loading(loading_msg))
            else:
                loading_msg = await message.answer(search_description)

            processor = DataProcessor()
            processor.load_vector_store()

            # Поиск
            rag_hits = processor.search_test(text, top_k=TEXT_SEARCH_TOP_K)

            # Реранжирование
            rag_hits = _rerank_hits_by_query(rag_hits, original_query)

            # Применяем фильтр по животным
            rag_hits, animal_types = await apply_animal_filter(rag_hits, original_query)

            if not rag_hits:
                await db.add_search_history(
                    user_id=user_id,
                    search_query=original_query,
                    search_type="text",
                    success=False
                )

                await safe_cancel_animation(animation_task)
                await safe_delete_message(loading_msg)
                await safe_delete_message(gif_msg)

                not_found_msg = f"❌ Тесты по запросу '<b>{html.escape(text)}</b>' не найдены.\n\n"
                
                if animal_types:
                    animal_display = animal_filter.get_animal_display_names(animal_types)
                    not_found_msg += f"🐾 <b>Фильтр по животным:</b> {animal_display}\n\n"

                await message.answer(
                    not_found_msg,
                    reply_markup=get_back_to_menu_kb(),
                    parse_mode="HTML"
                )

                await state.set_state(QuestionStates.waiting_for_search_type)
                return

            # Выбираем лучшие совпадения
            selected_docs = await select_best_match(text, rag_hits)

            # Записываем статистику
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

            await safe_cancel_animation(animation_task)
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)

            # FIX #17 & #19: Минимизированные данные
            search_id = hashlib.md5(
                f"{user_id}_{datetime.now().timestamp()}_{text}".encode()
            ).hexdigest()[:8]
            
            simplified_results = [
                {
                    'metadata': {
                        'test_code': doc.metadata.get('test_code'),
                        'test_name': doc.metadata.get('test_name'),
                        'department': doc.metadata.get('department')
                    },
                    'score': 0  # Для name search score не так важен
                }
                for doc in selected_docs
            ]
            
            await state.update_data(**{
                f"search_results_{search_id}": {
                    'data': simplified_results,
                    'timestamp': datetime.now().timestamp(),
                    'query': text
                }
            })
            
            await cleanup_old_search_results(state)
            
            # Считаем типы
            tests_count = sum(
                1 for item in simplified_results 
                if not is_profile_test(item['metadata'].get('test_code', ''))
            )
            profiles_count = sum(
                1 for item in simplified_results 
                if is_profile_test(item['metadata'].get('test_code', ''))
            )
            total_count = len(simplified_results)
            
            keyboard, total_pages, items_shown = create_paginated_keyboard(
                simplified_results,
                current_page=0,
                items_per_page=ITEMS_PER_PAGE,
                search_id=search_id,
                include_filters=True,
                tests_count=tests_count,
                profiles_count=profiles_count,
                total_count=total_count,
                current_view="all"
            )
            
            # Формируем ответ
            response = f"🔍 <b>Найдено {total_count} результаты</b>"
            
            if animal_types:
                animal_display = animal_filter.get_animal_display_names(animal_types)
                response += f" <b>(фильтр: {animal_display})</b>"
            
            if total_pages > 1:
                response += f" <b>(страница 1 из {total_pages}):</b>\n\n"
            else:
                response += ":\n\n"
            
            for i, item in enumerate(simplified_results[:items_shown], 1):
                metadata = item['metadata']
                
                test_code = sanitize_test_code_for_display(metadata['test_code'])
                test_name = html.escape(metadata['test_name'])
                department = html.escape(metadata.get('department', 'Не указано'))
                
                type_label = "🔬 Профиль" if is_profile_test(test_code) else "🧪 Тест"
                link = create_test_link(test_code)
                
                response += (
                    f"<b>{i}.</b> {type_label}: <a href='{link}'>{test_code}</a>\n"
                    f"📝 {test_name}\n"
                    f"📋 {department}\n\n"
                )
            
            response += "\n💡 <i>Нажмите на код теста в сообщении выше или выберите из кнопок</i>"
            
            if total_pages > 1:
                response += f"\n📄 <i>Используйте кнопки навигации для просмотра всех результатов</i>"
            
            await message.answer(
                response,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard
            )
            
            should_ask, rating_id = await rating_manager.should_ask_for_rating(
                user_id=message.from_user.id,
                response_type="name_search"
            )

            if should_ask:
                # Сохраняем информацию о запросе и результатах
                rating_response = response
            
                await state.update_data({
                    f"last_question_{rating_id}": text,
                    f"last_response_{rating_id}": rating_response
                })
                
                # Запрашиваем оценку через 1 секунду
                await asyncio.sleep(1)
                rating_keyboard = rating_manager.create_rating_keyboard(rating_id)
                
                await message.answer(
                    "📊 <b>Оцените, пожалуйста, результаты поиска:</b>",
                    parse_mode="HTML",
                    reply_markup=rating_keyboard
                )


            # Сохраняем последний тест
            await state.set_state(QuestionStates.waiting_for_search_type)
            await message.answer(
                "Готов к новому запросу! Введите код теста или опишите, что ищете:",
                reply_markup=get_dialog_kb()
            )

        except Exception as e:
            logger.error(f"[NAME_SEARCH] Failed: {e}", exc_info=True)

            await safe_cancel_animation(animation_task)
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)

            error_msg = (
                "❌ Тесты не найдены"
                if str(e) == "Тесты не найдены"
                else "⚠️ Ошибка поиска. Попробуйте позже."
            )
            await message.answer(error_msg, reply_markup=get_back_to_menu_kb())
            await state.set_state(QuestionStates.waiting_for_search_type)


# ============================================================================
# ОБРАБОТКА ОБЩИХ ВОПРОСОВ
# ============================================================================

async def handle_general_question(
    message: Message, 
    state: FSMContext, 
    question_text: str
):
    """
    Обработка общих вопросов через LLM
    
    Исправлено:
    - Проверка на off-topic вопросы
    - Проверка на неинформативные ответы LLM
    - Timeout для LLM
    - Корректная обработка длинных ответов
    """
    user = await db.get_user(message.from_user.id)
    

    if LOADING_GIF_ID:
        try:
            gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
        except Exception:
            gif_msg = None
        
        loading_msg = await message.answer(
            f"🤔 Анализирую вопрос..."
        )
        animation_task = asyncio.create_task(animate_loading(loading_msg))
    else:
        loading_msg = await message.answer("🤔 Анализирую вопрос...")

    try:
        # 1. Проверка на нерелевантность
        if await _is_off_topic_question(question_text):

            await safe_cancel_animation(animation_task)
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)
            
            await message.answer(
                f"🔍 <b>Этот вопрос не относится к лабораторной диагностике</b>\n\n"
                f"❓ <i>Ваш вопрос:</i> \"{html.escape(question_text[:200])}{'...' if len(question_text) > 200 else ''}\"\n\n"
                "🩺 <b>Я специализируюсь на:</b>\n"
                "• Лабораторных тестах и анализах\n"
                "• Преаналитических требованиях\n" 
                "• Контейнерах для биоматериалов\n"
                "• Подготовке пациентов к исследованиям\n\n"
                "💡 <b>Для других вопросов обратитесь к специалисту:</b>",
                parse_mode="HTML",
                reply_markup=_get_callback_support_keyboard(question_text)
            )
            return

        processor = DataProcessor()
        processor.load_vector_store()
        
        # 2. Поиск релевантных тестов
        relevant_docs = processor.search_test(query=question_text, top_k=70)
        relevant_tests = [doc for doc, score in relevant_docs if score > 0.3]
        
        # 3. Если нет результатов и вопрос сложный
        question_words = len(question_text.split())
        if not relevant_tests and question_words > 3:
            await safe_cancel_animation(animation_task)
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)
            
            await message.answer(
                f"🔍 <b>Не нашлось релевантной информации в базе данных</b>\n\n"
                f"❓ <i>Ваш вопрос:</i> \"{html.escape(question_text[:200])}{'...' if len(question_text) > 200 else ''}\"\n\n"
                "💡 <b>Попробуйте:</b>\n"
                "• Использовать коды тестов (например: <code>AN116</code>)\n"
                "• Уточнить формулировку вопроса\n"
                "• Обратиться с вопросом о конкретном анализе\n\n"
                "📞 <b>Или позвоните специалисту для консультации:</b>",
                parse_mode="HTML",
                reply_markup=_get_callback_support_keyboard(question_text)
            )
            return

        # 4. Собираем контекст
        context_info = ""
        all_test_codes = set()
        
        if relevant_tests:
            context_info = "\n\nРЕЛЕВАНТНАЯ ИНФОРМАЦИЯ ДЛЯ ВАШЕГО ВОПРОСА:\n"
            
            for doc in relevant_tests[:10]:
                test_data = doc.metadata
                test_code = test_data.get('test_code', '')
                
                if test_code:
                    normalized_code = normalize_test_code(test_code)
                    if normalized_code:
                        all_test_codes.add(normalized_code.upper())
                    
                    context_info += f"\n🔬 Тест {normalized_code} - {test_data.get('test_name', '')}:\n"
                    
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
                    ]
                    
                    for field, label in fields:
                        value = test_data.get(field)
                        if value and str(value).strip().lower() not in ['не указан', 'нет', '-', '']:
                            value_str = str(value)
                            if len(value_str) > 100:
                                value_str = value_str[:97] + "..."
                            context_info += f"  {label}: {value_str}\n"
                    
                    context_info += "  ─────────────────────────\n"

        user_name = get_user_first_name(user)

        # 5. Промпт для LLM
        system_prompt = f"""
# Роль: Ассистент ветеринарной лаборатории VetUnion

Ты - профессиональный консультант ветеринарной лаборатории, специализирующийся на лабораторной диагностике животных.

## Источники информации
Контекст: {context_info}
В начале общения обращайся к пользователю без приветствия. Его зовут: {user_name}

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
- Если вопрос требует индивидуальной консультации, прямо укажи: "Рекомендую обратиться к специалисту нашей лаборатории"

## Важно!
Если информации в контексте недостаточно для полноценного ответа, 
честно скажи об этом и предложи обратиться к специалисту.
"""

        # 6. Отправляем в LLM с timeout
        try:
            response = await asyncio.wait_for(
                llm.agenerate([
                    [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=question_text),
                    ]
                ]),
                timeout=LLM_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            await safe_cancel_animation(animation_task)
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)
            
            await message.answer(
                "⏱ Превышено время ожидания ответа. Попробуйте упростить вопрос или обратитесь к специалисту:",
                reply_markup=_get_callback_support_keyboard(question_text)
            )
            return

        answer = response.generations[0][0].text.strip()
        
        # 7. Проверка качества ответа
        if await _is_unhelpful_answer(answer, question_text):
            await safe_cancel_animation(animation_task)
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)
            
            await message.answer(
                f"🔍 <b>Не удалось найти точный ответ в доступных источниках</b>\n\n"
                f"❓ <i>Ваш вопрос:</i> \"{html.escape(question_text[:200])}{'...' if len(question_text) > 200 else ''}\"\n\n"
                "💡 <b>Рекомендую:</b>\n"
                "• Позвонить специалисту для детальной консультации\n" 
                "• Уточнить формулировку вопроса\n"
                "• Использовать коды тестов (например: <code>AN116</code>)\n\n"
                "📞 <b>Для получения точного ответа обратитесь к специалисту:</b>",
                parse_mode="HTML",
                reply_markup=_get_callback_support_keyboard(question_text)
            )
            return

        # 8. Обработка успешного ответа
        # Находим коды тестов и создаем ссылки
        code_patterns = [
            r'\b[AА][NН]\d+[A-ZА-Я\-]*\b',
            r'\b[A-ZА-Я]+\d+[A-ZА-Я\-]*\b',
            r'\b\d{2,4}[A-ZА-Я]+\b',
        ]
        
        found_codes = set()
        for pattern in code_patterns:
            for match in re.finditer(pattern, answer, re.IGNORECASE):
                code = match.group()
                normalized = normalize_test_code(code)
                if normalized and normalized.upper() in all_test_codes:
                    found_codes.add((code, normalized))
        
        # Создаем словарь замен
        code_to_link = {}
        for original, normalized in found_codes:
            link = create_test_link(normalized)
            if link and 'https://t.me/' in link:
                code_to_link[original] = f'<a href="{link}">{html.escape(original)}</a>'
        
        # Обрабатываем форматирование
        processed_text = html.escape(answer)
        processed_text = re.sub(r'\*\*([^\*]+)\*\*', r'<b>\1</b>', processed_text)
        processed_text = re.sub(r'(?<!\*)\*([^\*]+)\*(?!\*)', r'<i>\1</i>', processed_text)
        
        # Заменяем коды на ссылки (от длинных к коротким)
        sorted_codes = sorted(code_to_link.keys(), key=len, reverse=True)
        for code in sorted_codes:
            escaped_code = html.escape(code)
            pattern = r'\b' + re.escape(escaped_code) + r'\b'
            processed_text = re.sub(pattern, code_to_link[code], processed_text)
        
        await safe_cancel_animation(animation_task)
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        
        # 9. Отправка ответа (с разбивкой если длинный)
        if len(processed_text) > 4000:
            parts = []
            current = ""
            
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
            
            for i, part in enumerate(parts):
                try:
                    await message.answer(
                        part,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    if i < len(parts) - 1:
                        await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"[GENERAL_Q] Failed to send part {i+1}: {e}")
                    clean_part = re.sub(r'<[^>]+>', '', part)
                    await message.answer(clean_part)
        else:
            try:
                await message.answer(
                    processed_text,
                    parse_mode="HTML", 
                    disable_web_page_preview=True
                )

                logger.info(f"[RATING] Checking if should ask for rating for user {message.from_user.id}")

                should_ask, rating_id = await rating_manager.should_ask_for_rating(
                    user_id=message.from_user.id,
                    response_type="general"
                )

                logger.info(f"[RATING] Should ask: {should_ask}, rating_id: {rating_id}")

                if should_ask:
                    # Сохраняем информацию о вопросе и ответе
                    await state.update_data({
                        f"last_question_{rating_id}": question_text,
                        f"last_response_{rating_id}": answer[:1000]  # сохраняем часть ответа
                    })
                    
                    # Запрашиваем оценку через 1 секунду (не сразу)
                    await asyncio.sleep(1)
                    rating_keyboard = rating_manager.create_rating_keyboard(rating_id)
                    
                    await message.answer(
                        "📊 <b>Оцените, пожалуйста, насколько полезным был ответ:</b>",
                        parse_mode="HTML",
                        reply_markup=rating_keyboard
                    )
                    logger.info(f"[RATING] Rating requested for user {message.from_user.id}")

            except Exception as e:
                logger.error(f"[GENERAL_Q] Failed to send HTML: {e}")
                clean_text = re.sub(r'<[^>]+>', '', answer)
                await message.answer(clean_text, disable_web_page_preview=True)


        # 10. Проверка на рекомендацию обратиться к специалисту
        if await _contains_specialist_recommendation(answer):
            # Показываем кнопку заказа звонка
            await message.answer(
                "📞 <b>Для получения детальной консультации вы можете заказать звонок специалиста:</b>",
                parse_mode="HTML",
                reply_markup=_get_callback_support_keyboard(question_text)
            )
        else:
            # Обычные кнопки для дальнейших действий
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔢 Найти тест по коду", 
                            callback_data="search_by_code"
                        ),
                        InlineKeyboardButton(
                            text="📝 Найти по названию", 
                            callback_data="search_by_name"
                        ),
                    ]
                ]
            )
            await message.answer("Что бы вы хотели сделать дальше?", reply_markup=keyboard)
        
        try:
            # Извлекаем коды тестов из ответа (если есть)
            found_codes = list(found_codes) if 'found_codes' in locals() else []
            primary_test_code = found_codes[0][1] if found_codes else None
            
            await db.log_chat_interaction(
                user_id=message.from_user.id,
                user_name=message.from_user.full_name or f"ID{message.from_user.id}",
                question=question_text,
                bot_response=answer,  # Оригинальный ответ LLM
                request_type='general',
                search_success=len(relevant_tests) > 0,
                found_test_code=primary_test_code
            )
        except Exception as e:
            logger.error(f"[LOGGING] Failed to log general question: {e}")

    except Exception as e:
        logger.error(f"[GENERAL_Q] Failed: {e}", exc_info=True)
        
        await safe_cancel_animation(animation_task)
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        
        await message.answer(
            "⚠️ <b>Произошла техническая ошибка при обработке запроса</b>\n\n"
            "💡 <b>Попробуйте:</b>\n"
            "• Повторить вопрос позже\n"
            "• Использовать коды тестов\n"
            "• Обратиться к специалисту\n\n"
            "📞 <b>Для срочной консультации позвоните специалисту:</b>",
            parse_mode="HTML",
            reply_markup=_get_callback_support_keyboard(question_text)
        )

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ МАРШРУТИЗАЦИИ
# ============================================================================

async def _process_confident_query(
    message: Message, 
    state: FSMContext, 
    query_type: str, 
    text: str, 
    metadata: Dict
):
    """Обработка запроса с высокой уверенностью классификатора"""
    await state.update_data(
        requires_confirmation=False,
        requires_clarification=False
    )

    user_id = message.from_user.id
    expanded_query = expand_query_with_abbreviations(text)
    
    # ============================================================
    # FIX: Улучшенная проверка для общих вопросов с аббревиатурами
    # ============================================================
    
    text_lower = text.lower()
    
    # Проверяем наличие вопросительных слов
    has_general_keywords = any(keyword in text_lower for keyword in GENERAL_QUESTION_KEYWORDS)
    
    # Проверяем наличие ЯВНЫХ кодов тестов (AN123, 1234ABC и т.п.)
    has_explicit_test_code = bool(re.search(
        r'\b[AА][NН]\d+[A-ZА-Я\-]*\b|\b\d{2,4}[A-ZА-Я\-]+\b', 
        text, 
        re.IGNORECASE
    ))
    
    # Проверяем, является ли это вопросом (начинается с вопросительного слова или содержит '?')
    is_question = text.strip().endswith('?') or any(
        text_lower.startswith(q) for q in ['как', 'что', 'где', 'когда', 'почему', 'зачем', 'какой', 'какая', 'какие']
    )
    
    # Определяем, содержит ли запрос ТОЛЬКО аббревиатуру (без контекста)
    # Убираем вопросительные слова и знаки препинания
    clean_text = text_lower
    for keyword in GENERAL_QUESTION_KEYWORDS:
        clean_text = clean_text.replace(keyword, '')
    clean_text = re.sub(r'[^\w\s]', '', clean_text).strip()
    
    # Если после очистки осталось мало слов - это может быть просто код
    words_after_cleanup = [w for w in clean_text.split() if len(w) > 1]
    is_short_query = len(words_after_cleanup) <= 2
    
    # ============================================================
    # ЛОГИКА ПЕРЕОПРЕДЕЛЕНИЯ НА ОБЩИЙ ВОПРОС
    # ============================================================
    
    should_be_general = False
    
    # Случай 1: Вопросительные слова + нет явного кода + это вопрос
    if has_general_keywords and not has_explicit_test_code and is_question:
        should_be_general = True
        logger.info(f"[CLASSIFICATION] General question with keywords detected: {text}")
    
    # Случай 2: Расширенный запрос сильно отличается от оригинала (аббревиатура была расширена)
    # И при этом есть контекст вопроса
    elif expanded_query != text and len(expanded_query) > len(text) * 1.5 and has_general_keywords:
        should_be_general = True
        logger.info(f"[CLASSIFICATION] Abbreviation in general question detected: '{text}' -> '{expanded_query}'")
    
    # Случай 3: Это НЕ короткий запрос и есть вопросительные слова
    elif not is_short_query and (has_general_keywords or is_question):
        should_be_general = True
        logger.info(f"[CLASSIFICATION] Complex general question detected: {text}")
    
    # Применяем переопределение
    if should_be_general:
        logger.info(f"[CLASSIFICATION] Overriding '{query_type}' to 'general' for: {text}")
        await db.add_request_stat(
            user_id=user_id, request_type="question", request_text=text
        )
        await handle_general_question(message, state, expanded_query)
        return
    
    # ============================================================
    # ОРИГИНАЛЬНАЯ ЛОГИКА ПРОДОЛЖАЕТСЯ
    # ============================================================
    
    # Проверка на профили
    profile_keywords = ['профили', 'профиль', 'комплексы', 'комплекс', 'панели', 'панель']
    if any(keyword in text.lower() for keyword in profile_keywords):
        query_type = "profile"
        logger.info(f"[PROFILE] Detected profile keywords in: {text}")

    # Маршрутизация
    if query_type == "code":
        await state.set_state(QuestionStates.waiting_for_code)
        await handle_code_search_with_text(message, state, expanded_query)
    elif query_type in ("name", "profile"):
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search_with_text(message, state, expanded_query)
    else:  # general
        await db.add_request_stat(
            user_id=user_id, request_type="question", request_text=text
        )
        await handle_general_question(message, state, expanded_query)


async def _ask_confirmation(
    message: Message, 
    state: FSMContext, 
    query_type: str, 
    text: str, 
    confidence: float
):
    """Запрос подтверждения типа поиска"""
    
    # Устанавливаем флаг что это запрос с подтверждением типа
    await state.update_data(
        requires_confirmation=True,  # Флаг что требуется подтверждение
        requires_clarification=False,
        confirmation_query_type=query_type
    )
    
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

    inline_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да", 
                    callback_data="confirm_search:yes"
                ),
                InlineKeyboardButton(
                    text="❌ Нет", 
                    callback_data="confirm_search:no"
                )
            ]
        ]
    )

    await message.answer(
        confirmation_text,
        parse_mode="HTML",
        reply_markup=inline_keyboard
    )
    
    await state.set_state(QuestionStates.confirming_search_type)


async def _clarify_with_llm(
    message: Message, 
    state: FSMContext, 
    text: str, 
    initial_type: str, 
    confidence: float
):
    """Уточнение типа поиска через inline кнопки"""
    
    # Устанавливаем флаг что это запрос с уточнением типа
    await state.update_data(
        requires_confirmation=False,
        requires_clarification=True  # Флаг что требуется уточнение типа
    )

    clarification_text = (
        f"🔍 Я не совсем уверен, что вы ищете.\n\n"
        f"Ваш запрос: <b>{html.escape(text)}</b>\n\n"
        f"Пожалуйста, выберите тип поиска:"
    )

    inline_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔢 Поиск по коду",
                    callback_data="clarify_search:code"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📝 Поиск по названию", 
                    callback_data="clarify_search:name"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔬 Поиск профиля",
                    callback_data="clarify_search:profile"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❓ Общий вопрос",
                    callback_data="clarify_search:general"
                )
            ]
        ]
    )

    await message.answer(
        clarification_text,
        parse_mode="HTML",
        reply_markup=inline_keyboard
    )
    
    await state.set_state(QuestionStates.clarifying_search)

# ============================================================================
# ОТПРАВКА ИНФОРМАЦИИ О ТЕСТЕ
# ============================================================================

async def send_test_info_with_photo(
    message: Message, 
    test_data: Dict, 
    response_text: str
):
    """Отправляет информацию о тесте с кнопкой для показа фото контейнеров"""
    
    # Собираем все типы контейнеров
    raw_container_types = []
    
    primary_container = str(test_data.get("primary_container_type", "")).strip()
    if primary_container and primary_container.lower() not in ["не указан", "нет", "-", "", "none", "null"]:
        primary_container = primary_container.replace('"', "").replace("\n", " ")
        primary_container = " ".join(primary_container.split())
        
        if "*I*" in primary_container:
            parts = [ct.strip() for ct in primary_container.split("*I*")]
            raw_container_types.extend(parts)
        else:
            raw_container_types.append(primary_container)
    
    container_type_raw = str(test_data.get("container_type", "")).strip()
    if container_type_raw and container_type_raw.lower() not in ["не указан", "нет", "-", "", "none", "null"]:
        container_type_raw = container_type_raw.replace('"', "").replace("\n", " ")
        container_type_raw = " ".join(container_type_raw.split())
        
        if "*I*" in container_type_raw:
            parts = [ct.strip() for ct in container_type_raw.split("*I*")]
            raw_container_types.extend(parts)
        else:
            raw_container_types.append(container_type_raw)
    
    # Дедуплицируем
    unique_containers = deduplicate_container_names(raw_container_types)
    has_containers = len(unique_containers) > 0
    
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

# ============================================================================
# ОБРАБОТЧИКИ ОЦЕНОК И КОММЕНТАРИЕВ
# ============================================================================

@questions_router.callback_query(F.data.startswith("rating:"))
async def handle_rating_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик оценок ответов"""
    await callback.answer()
    
    try:
        parts = callback.data.split(":")
        rating_id = parts[1]
        rating = int(parts[2])
        
        data = await state.get_data()
        question = data.get(f"last_question_{rating_id}", "")
        response = data.get(f"last_response_{rating_id}", "")
        
        # Сохраняем оценку
        await rating_manager.save_rating(
            user_id=callback.from_user.id,
            rating_id=rating_id,
            rating=rating,
            question=question,
            response=response
        )
        
        if rating <= 3:
            # Для плохих оценок (1-3) - сохраняем данные и предлагаем комментарий
            await state.update_data({
                f"pending_rating_{rating_id}": {
                    "rating": rating,
                    "question": question,
                    "response": response,
                    "user_name": callback.from_user.full_name
                }
            })
            
            feedback_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💬 Написать комментарий", 
                            callback_data=f"add_comment:{rating_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🚫 Пропустить комментарий", 
                            callback_data=f"skip_comment:{rating_id}"
                        )
                    ]
                ]
            )
            
            await callback.message.edit_text(
                f"❌ Спасибо за оценку {rating} ⭐\n\n"
                "Мы сожалеем, что ответ не соответствовал ожиданиям. "
                "Пожалуйста, помогите нам улучшить бота - напишите, что можно улучшить?",
                parse_mode="HTML",
                reply_markup=feedback_keyboard
            )
        else:
            # Для хороших оценок (4-5) - благодарим и УБИРАЕМ кнопки оценки
            await callback.message.edit_text(
                f"✅ Спасибо за оценку {rating} ⭐!\n\n"
                "Мы рады, что смогли помочь! 🎉",
                parse_mode="HTML",
                reply_markup=None  # Убираем кнопки оценки
            )
            
            # Восстанавливаем обычное состояние
            await state.set_state(QuestionStates.waiting_for_search_type)
            
    except Exception as e:
        logger.error(f"[RATING] Error: {e}")
        await callback.answer("Ошибка при обработке оценки", show_alert=True)



@questions_router.callback_query(F.data.startswith("add_comment:"))
async def handle_add_comment(callback: CallbackQuery, state: FSMContext):
    """Обработчик для добавления комментария к плохой оценке"""
    await callback.answer()
    
    rating_id = callback.data.split(":")[1]
    
    # Сохраняем текущие данные о состоянии перед переходом в режим комментария
    current_data = await state.get_data()
    await state.update_data({
        "current_rating_id": rating_id,
        "previous_state_data": current_data  # Сохраняем предыдущее состояние
    })
    
    # Устанавливаем специальное состояние для комментария
    await state.set_state(QuestionStates.waiting_for_comment)
    
    # УДАЛЯЕМ кнопки "Что бы вы хотели сделать дальше?" и показываем интерфейс комментария
    await callback.message.edit_text(
        "💬 <b>Пожалуйста, напишите ваш комментарий:</b>\n\n"
        "Что именно не устроило в ответе? Что можно улучшить?\n"
        "Ваши замечания помогут нам сделать бота лучше!\n\n"
        "<i>Просто напишите ваш комментарий в этом чате...</i>",
        parse_mode="HTML",
        reply_markup=None  # Убираем все кнопки
    )

@questions_router.callback_query(F.data.startswith("skip_comment:"))
async def handle_skip_comment(callback: CallbackQuery, state: FSMContext):
    """Пропуск комментария для плохой оценки"""
    await callback.answer()
    
    rating_id = callback.data.split(":")[1]
    data = await state.get_data()
    
    rating_data = data.get(f"pending_rating_{rating_id}")
    if rating_data:
        # Отправляем плохую оценку БЕЗ комментария в группу
        success = await rating_manager.send_rating_to_group(
            bot=callback.bot,
            user_id=callback.from_user.id,
            rating=rating_data["rating"],
            question=rating_data["question"],
            response=rating_data["response"],
            user_name=rating_data["user_name"]
        )
        
        if success:
            logger.info(f"[RATING] Successfully sent rating {rating_data['rating']} to group")
        else:
            logger.error(f"[RATING] Failed to send rating to group")
    
    # УДАЛЯЕМ кнопки оценки и показываем финальное сообщение
    await callback.message.edit_text(
        "📢 Оценка отправлена разработчикам!\n\n"
        "💡 <b>Присоединяйтесь к нашей группе</b> - там вы можете:\n"
        "• 🗣️ Участвовать в обсуждении улучшений\n"
        "• 💡 Предлагать новые идеи\n"
        "• ❓ Задавать сложные вопросы\n\n"
        "Ваше мнение важно для нас! 🙏",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💬 Присоединиться к группе обсуждения", 
                        url=rating_manager.feedback_group_link
                    )
                ]
            ]
        )
    )
    
    # ВОССТАНАВЛИВАЕМ обычное состояние
    await state.set_state(QuestionStates.waiting_for_search_type)
    

    
    # Очищаем временные данные
    await state.update_data({
        f"pending_rating_{rating_id}": None,
        "current_rating_id": None,
        "previous_state_data": None
    })



@questions_router.message(QuestionStates.waiting_for_comment, F.text)
async def handle_comment_text(message: Message, state: FSMContext):
    """Обработчик текстовых комментариев к плохим оценкам (в специальном состоянии)"""
    try:
        data = await state.get_data()
        rating_id = data.get("current_rating_id")
        
        if not rating_id:
            await message.answer("❌ Ошибка: не найден ID оценки. Возвращаюсь в обычный режим.")
            await state.set_state(QuestionStates.waiting_for_search_type)

            return
        
        rating_data = data.get(f"pending_rating_{rating_id}")
        
        if rating_data and message.text:
            # Отправляем плохую оценку С комментарием в группу
            success = await rating_manager.send_rating_to_group(
                bot=message.bot,
                user_id=message.from_user.id,
                rating=rating_data["rating"],
                question=rating_data["question"],
                response=rating_data["response"],
                user_name=rating_data["user_name"],
                comment=message.text
            )
            
            if success:
                logger.info(f"[RATING] Successfully sent rating with comment to group")
            else:
                logger.error(f"[RATING] Failed to send rating with comment to group")
            
            # Показываем сообщение о успешной отправке с кнопкой группы
            await message.answer(
                "📢 Ваш комментарий отправлен разработчикам!\n\n"
                "💡 <b>Спасибо за обратную связь!</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="💬 Присоединиться к группе обсуждения", 
                                url=rating_manager.feedback_group_link
                            )
                        ]
                    ]
                )
            )
            
        else:
            await message.answer("❌ Не удалось обработать комментарий.")
        
        # ВОССТАНАВЛИВАЕМ обычное состояние бота
        await state.set_state(QuestionStates.waiting_for_search_type)
        

        
        # Очищаем временные данные
        await state.update_data({
            "current_rating_id": None,
            f"pending_rating_{rating_id}": None,
            "previous_state_data": None
        })
        
    except Exception as e:
        logger.error(f"[COMMENT] Error processing comment: {e}")
        await message.answer("❌ Ошибка при обработке комментария.")
        # Все равно восстанавливаем состояние и ВОЗВРАЩАЕМ кнопки
        await state.set_state(QuestionStates.waiting_for_search_type)
        await message.answer(
            reply_markup=get_dialog_kb()  # ВОЗВРАЩАЕМ кнопки
        )


# ============================================================================
# ЭКСПОРТЫ
# ============================================================================

__all__ = [
    "questions_router",
    "smart_test_search",
    "format_test_data",
    "format_test_info",
    "QuestionStates",
    "get_dialog_kb",
    "create_test_link",
    "normalize_test_code",
]

