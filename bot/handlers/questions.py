from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from bot.keyboards import get_menu_by_role, get_dialog_kb, get_back_to_menu_kb, get_search_type_kb
from langchain.schema import SystemMessage, HumanMessage, Document
import pytz
import asyncio
import base64
import urllib.parse
import html
import re
from typing import Optional, Dict, List, Tuple
from fuzzywuzzy import fuzz, process
from datetime import datetime
from src.database.db_init import db
from src.data_vectorization import DataProcessor
from models.models_init import Google_Gemini_2_5_Flash_Lite as llm

BOT_USERNAME = "AI_VET_UNION_BOT"

LOADING_GIF_ID = "CgACAgIAAxkBAAMIaGr_qy1Wxaw2VrBrm3dwOAkYji4AAu54AAKmqHlJAtZWBziZvaA2BA"
# LOADING_GIF_ID = "CgACAgIAAxkBAAIBFGiBcXtGY7OZvr3-L1dZIBRNqSztAALueAACpqh5Scn4VmIRb4UjNgQ"
# LOADING_GIF_ID = "CgACAgIAAxkBAAMMaHSq3vqxq2RuMMj-DIMvldgDjfkAAu54AAKmqHlJCNcCjeoHRJI2BA"
questions_router = Router()

def fix_bold(text: str) -> str:
    """Заменяет markdown жирный текст на HTML."""
    import re
    # Заменяем **текст** на <b>текст</b>
    text = re.sub(r'\*\*([^\*]+)\*\*', r'<b>\1</b>', text)
    return text

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

# Словарь аббревиатур для расширения запросов
TEST_ABBREVIATIONS = {
    "ОАК": "общий анализ крови клинический анализ крови гемка гематология",
    "БХ": "биохимический анализ биохимия крови",
    "ОАМ": "общий анализ мочи",
    "СОЭ": "скорость оседания эритроцитов",
    "АЛТ": "аланинаминотрансфераза",
    "АСТ": "аспартатаминотрансфераза",
    "ТТГ": "тиреотропный гормон",
    "Т4": "тироксин",
    "ПЦР": "полимеразная цепная реакция",
    "ИФА": "иммуноферментный анализ",
    "ГЕМКА": "общий анализ крови клинический анализ крови оак гематология",
    "ГЕМАТОЛОГИЯ": "общий анализ крови клинический анализ крови оак гемка",
    "ГЕМАТКА": "общий анализ крови клинический анализ крови оак гемка гематология",
    "цитология": "Цитологическое исследование",
}

def is_test_code_pattern(text: str) -> bool:
    """Проверяет, соответствует ли текст паттерну кода теста."""
    text = text.strip().upper().replace(' ', '')
    
    patterns = [
        r'^[AА][NН]\d+',  # AN или АН + цифры
        r'^[AА][NН]\d+[A-ZА-Я\-]+',  # AN + цифры + суффикс
        r'^\d{1,4}$',  # Только цифры (до 4 знаков)
        r'^\d+[A-ZА-Я\-]+$',  # Цифры + буквенный суффикс
    ]
    
    for pattern in patterns:
        if re.match(pattern, text):
            return True
            
    return False

def simple_translit(text: str) -> str:
    """Простая транслитерация для deep links."""
    translit_map = {
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'YO',
        'Ж': 'ZH', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'KH', 'Ц': 'TS', 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH',
        'Ъ': '', 'Ы': 'YI', 'Ь': '', 'Э': 'EH', 'Ю': 'YU', 'Я': 'YA'
    }
    
    result = ''
    for char in text.upper():
        if char in translit_map:
            result += translit_map[char]
        else:
            result += char
    return result

def reverse_translit(text: str) -> str:
    """Обратная транслитерация для deep links."""
    # Добавляем проверку на None и пустую строку
    if not text:
        return ""
    
    text = text.upper()
    
    # Специальные случаи для полных кодов
    special_cases = {
        'ANDOKR': 'ANДОКР',
        'AN515GIEH': 'AN515ГИЭ',
        'AN506GIEH': 'AN506ГИЭ',
        'AN513GIEH': 'AN513ГИЭ',
        'AN515GIEH': 'AN515ГИЭ',
        'AN712BTK': 'AN712БТК'
    }
    
    if text in special_cases:
        return special_cases[text]
    
    # Общая обратная транслитерация для суффиксов
    import re
    match = re.match(r'^(AN\d+)(.+)$', text)
    if match:
        prefix = match.group(1)
        suffix = match.group(2)
        
        # Словарь суффиксов
        suffix_map = {
            'GIEH': 'ГИЭ',
            'GII': 'ГИИ', 
            'BTK': 'БТК',
            'BAL': 'БАЛ',
            'KLSCH': 'КЛЩ',
            'VPT': 'ВПТ',
            'GLZ': 'ГЛЗ',
            'GSK': 'ГСК',
            'KM': 'КМ',
            'KR': 'КР',
            'LIK': 'ЛИК',
            'NOS': 'НОС',
            'PRK': 'ПРК',
            'ROT': 'РОТ',
            'SIN': 'СИН',
            'FK': 'ФК',
            'ASP': 'АСП',
            'OBS': 'ОБС'
        }
        
        if suffix in suffix_map:
            return prefix + suffix_map[suffix]
    
    return text

def create_test_link(test_code: str) -> str:
    """Создает deep link для теста."""
    safe_code = simple_translit(test_code)
    return f"https://t.me/{BOT_USERNAME}?start=test_{safe_code}"

def normalize_test_code(text: str) -> str:
    """Нормализует введенный код теста."""
    # Добавляем проверку на None и пустую строку
    if not text:
        return ""
    
    text = text.strip().upper().replace(' ', '')
    
    # Заменяем кириллицу на латиницу в префиксе AN/АН
    text = text.replace('АН', 'AN').replace('АN', 'AN').replace('AН', 'AN')
    
    # Если только цифры - добавляем AN
    if text.isdigit():
        text = f"AN{text}"
    # Если начинается с цифр - добавляем AN в начало
    elif re.match(r'^\d', text):
        text = f"AN{text}"
    
    return text

async def get_test_container_photos(test_data: Dict) -> List[Dict]:
    """Получает все фото контейнеров для теста"""
    container_string = str(test_data.get('container_number', ''))
    
    # Парсим номера контейнеров
    container_numbers = db.parse_container_numbers(container_string)
    
    photos = []
    for num in container_numbers:
        file_id = await db.get_container_photo(num)
        if file_id:
            photos.append({
                'number': num,
                'file_id': file_id
            })
    
    return photos

async def show_container_photos(message: Message, test_data: Dict):
    """Показывает все фото контейнеров для теста"""
    photos = await get_test_container_photos(test_data)
    
    if photos:
        # Если одно фото
        if len(photos) == 1:
            photo = photos[0]
            caption = (
                f"🧪 <b>Контейнер №{photo['number']}</b>\n"
                f"❄️ Температура хранения: {test_data['storage_temp']}"
            )
            try:
                await message.answer_photo(
                    photo=photo['file_id'],
                    caption=caption,
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"[ERROR] Failed to send container photo: {e}")
        
        # Если несколько фото - отправляем медиа группу
        elif len(photos) > 1:
            media_group = []
            for i, photo in enumerate(photos):
                caption = f"🧪 <b>Контейнер №{photo['number']}</b>"
                if i == 0:  # Добавляем температуру только к первому фото
                    caption += f"\n❄️ Температура хранения: {test_data['storage_temp']}"
                
                media_group.append(
                    InputMediaPhoto(
                        media=photo['file_id'],
                        caption=caption,
                        parse_mode="HTML"
                    )
                )
            
            try:
                await message.answer_media_group(media_group)
            except Exception as e:
                print(f"[ERROR] Failed to send container photos: {e}")

def calculate_fuzzy_score(query: str, test_code: str, test_name: str = "") -> float:
    """Улучшенная функция для точного поиска по коду теста."""
    # Нормализуем оба значения
    query = normalize_test_code(query)
    test_code = test_code.upper().strip()
    
    # Точное совпадение
    if query == test_code:
        return 100.0
    
    # Извлекаем числа из запроса и кода
    query_digits = ''.join(c for c in query if c.isdigit())
    code_digits = ''.join(c for c in test_code if c.isdigit())
    
    # Если в запросе есть цифры
    if query_digits:
        # Проверяем точное совпадение цифр
        if code_digits == query_digits:
            return 90.0  # Высокий приоритет для точного совпадения цифр
        # Проверяем, начинается ли код с этих цифр
        elif code_digits.startswith(query_digits):
            # Чем ближе длина, тем выше score
            length_ratio = len(query_digits) / len(code_digits) if code_digits else 0
            return 70.0 + (length_ratio * 20)  # От 70 до 90
        # Если цифры не совпадают - низкий приоритет
        else:
            return 0.0
    
    # Проверяем, начинается ли код теста с запроса (префикс)
    if test_code.startswith(query):
        return 85.0
    
    # Базовый fuzzy score только если нет цифр в запросе
    if not query_digits:
        code_score = fuzz.ratio(query, test_code)
        
        # Бонус за совпадение префикса AN
        if query.startswith("AN") and test_code.startswith("AN"):
            code_score += 10
        
        return min(100, code_score)
    
    return 0.0 

async def fuzzy_test_search(processor: DataProcessor, query: str, threshold: float = 30) -> List[Tuple[Document, float]]:
    """Улучшенный fuzzy поиск с фильтрацией по цифрам."""
    # Нормализуем запрос
    query = normalize_test_code(query)
    
    # Извлекаем цифры из запроса для фильтрации
    query_digits = ''.join(c for c in query if c.isdigit())
    
    # Получаем тесты для анализа
    all_tests = processor.search_test(query="", top_k=2000)
    
    fuzzy_results = []
    seen_codes = set()
    
    for doc, _ in all_tests:
        test_code = doc.metadata.get('test_code', '')
        test_name = doc.metadata.get('test_name', '')
        
        if test_code in seen_codes:
            continue
        
        # Вычисляем score
        score = calculate_fuzzy_score(query, test_code, test_name)
        
        if score >= threshold:
            fuzzy_results.append((doc, score))
            seen_codes.add(test_code)
    
    # Сортируем по убыванию score
    fuzzy_results.sort(key=lambda x: x[1], reverse=True)
    
    # Если есть цифры в запросе, возвращаем только релевантные результаты
    if query_digits:
        # Фильтруем результаты - оставляем только с совпадающими или начинающимися цифрами
        filtered_results = []
        for doc, score in fuzzy_results:
            code_digits = ''.join(c for c in doc.metadata.get('test_code', '') if c.isdigit())
            if code_digits.startswith(query_digits):
                filtered_results.append((doc, score))
        return filtered_results[:30]
    
    return fuzzy_results[:30]

async def check_if_needs_new_search(query: str, current_test_data: Dict) -> bool:
    """Улучшенная проверка - нужен ли новый поиск."""
    
    if not current_test_data:
        return True
    
    query_upper = query.upper().strip()
    query_lower = query.lower().strip()
    current_test_code = current_test_data.get('test_code', '').upper()
    current_test_name = current_test_data.get('test_name', '').lower()
    
    # Проверяем, не упоминается ли код другого теста
    # Паттерны для поиска кодов тестов в тексте
    code_patterns = [
        r'\b[AА][NН]\d+[А-ЯA-Z]*\b',  # AN с цифрами и возможным суффиксом
        r'\b\d{1,4}[А-ЯA-Z]+\b',       # Цифры с буквенным суффиксом
        r'\b[AА][NН]\s*\d+\b',         # AN с пробелом и цифрами
        r'\bан\s*\d+\b',               # ан в нижнем регистре
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
        'покажи', 'найди', 'поиск', 'информация о', 'что за тест',
        'расскажи про', 'а что насчет', 'другой тест', 'еще тест',
        'анализ на', 'тест на', 'найти тест', 'код теста'
    ]
    
    # Проверяем наличие ключевых слов поиска
    for keyword in search_keywords:
        if keyword in query_lower:
            # Проверяем, не про текущий ли тест спрашивают
            if current_test_code.lower() not in query_lower and \
               not any(word in current_test_name for word in query_lower.split()):
                return True
    
    # Проверяем упоминание конкретных типов анализов
    test_categories = {
        'биохимия': ['биохим', 'алт', 'аст', 'креатинин', 'мочевина', 'глюкоза'],
        'гематология': ['оак', 'общий анализ крови', 'гемоглобин', 'эритроциты', 'лейкоциты'],
        'гормоны': ['ттг', 'т3', 'т4', 'кортизол', 'тестостерон'],
        'инфекции': ['пцр', 'ифа', 'антитела', 'вирус', 'бактерии'],
        'моча': ['моча', 'оам', 'общий анализ мочи'],
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

def create_similar_tests_keyboard(similar_tests: List[Tuple[Document, float]], current_test_code: str = None) -> InlineKeyboardMarkup:
    """Создает компактную inline клавиатуру с похожими тестами."""
    keyboard = []
    row = []
    
    count = 0
    for doc, score in similar_tests:
        test_code = doc.metadata.get('test_code', '')
        
        # Пропускаем текущий тест
        if current_test_code and test_code == current_test_code:
            continue
        
        # Создаем компактную кнопку только с кодом
        button = InlineKeyboardButton(
            text=test_code,
            callback_data=TestCallback.pack("show_test", test_code)
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

@questions_router.message(Command("test_link"))
async def test_link_generation(message: Message):
    """Тестовая команда для проверки генерации ссылок"""
    test_codes = ["AN506ГИЭ", "AN511", "AN512-A", "AN712БТК"]
    
    response = "🔗 Тестовые ссылки:\n\n"
    for code in test_codes:
        link = create_test_link(code)
        response += f"Код: <code>{code}</code>\nСсылка: <a href='{link}'>Нажмите здесь</a>\n\n"
    
    await message.answer(response, parse_mode="HTML", disable_web_page_preview=True)

@questions_router.callback_query(F.data == "close_keyboard")
async def handle_close_keyboard(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

def format_similar_tests_text(similar_tests: List[Tuple[Document, float]], max_display: int = 5) -> str:
    """Форматирует текст с информацией о похожих тестах."""
    if not similar_tests:
        return ""
    
    text = "\n<b>📋 Похожие тесты:</b>\n"
    for doc, score in similar_tests[:max_display]:
        test_code = doc.metadata.get('test_code', '')
        test_name = doc.metadata.get('test_name', '')
        # Сокращаем название если слишком длинное
        if len(test_name) > 50:
            test_name = test_name[:47] + "..."
        text += f"• <code>{test_code}</code> - {test_name}\n"
    
    if len(similar_tests) > max_display:
        text += f"\n<i>Показаны {max_display} из {len(similar_tests)} найденных</i>"
    
    return text

def format_similar_tests_with_links(similar_tests: List[Tuple[Document, float]], max_display: int = 5) -> str:
    """Форматирует текст с кликабельными ссылками на похожие тесты."""
    if not similar_tests:
        return ""
    
    text = "\n<b>📋 Похожие тесты (нажмите на код):</b>\n"
    for doc, score in similar_tests[:max_display]:
        test_code = doc.metadata.get('test_code', '')
        test_name = doc.metadata.get('test_name', '')
        if len(test_name) > 40:
            test_name = test_name[:37] + "..."
        
        # Создаем кликабельную ссылку
        link = create_test_link(test_code)
        text += f"• <a href='{link}'>{test_code}</a> - {test_name}\n"
    
    if len(similar_tests) > max_display:
        text += f"\n<i>Показаны {max_display} из {len(similar_tests)} найденных</i>"
    
    return text

def generate_test_code_variants(text: str) -> list[str]:
    """Генерирует различные варианты написания кода теста."""
    # Нормализуем входной текст
    text = normalize_test_code(text)
    variants = [text]  # Оригинал

    cyrillic_to_latin = {
        'А': 'A', 'Б': 'B', 'В': ['V', 'W', 'B'], 'Г': 'G', 'Д': 'D',
        'Е': ['E', 'I'], 'Ё': ['E', 'I'], 'Ж': ['J', 'ZH'], 'З': ['Z', 'S', 'C'],  
        'И': ['I', 'E', 'Y'], 'Й': ['Y', 'I'], 'К': ['K', 'C', 'Q'], 'Л': 'L',
        'М': 'M', 'Н': ['N', 'H'], 'О': 'O', 'П': 'P', 'Р': ['R', 'P'],
        'С': ['S', 'C'], 'Т': 'T', 'У': ['U', 'Y', 'W'], 'Ф': 'F',
        'Х': ['H', 'X'], 'Ц': ['C', 'TS'], 'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH',
        'Ы': ['Y', 'I'], 'Э': ['E', 'A'], 'Ю': ['U', 'YU'], 'Я': ['YA', 'A']
    }
    
    # Латиница -> кириллица (для обратного преобразования)
    latin_to_cyrillic = {
        'A': ['А', 'Я'], 'B': ['Б', 'В'], 'C': ['С', 'К', 'Ц'], 'D': 'Д',
        'E': ['Е', 'И', 'Э'], 'F': 'Ф', 'G': 'Г', 'H': ['Х', 'Н'],
        'I': ['И', 'Й'], 'J': 'Ж', 'K': 'К', 'L': 'Л', 'M': 'М', 'N': 'Н',
        'O': 'О', 'P': ['П', 'Р'], 'Q': 'К', 'R': 'Р', 'S': ['С', 'З'],
        'T': 'Т', 'U': ['У', 'Ю'], 'V': 'В', 'W': ['В', 'У'], 'X': 'Х',
        'Y': ['У', 'Й', 'Ы'], 'Z': 'З'
    }
    
    def convert_string(s, mapping, max_variants=5):
        """Конвертирует строку используя маппинг, генерируя варианты"""
        if not s:
            return ['']
        
        result_variants = []
        
        # Обрабатываем первый символ
        char = s[0]
        rest = s[1:]
        
        if char.isdigit() or char in ['-', '_']:
            # Цифры и спецсимволы оставляем как есть
            rest_variants = convert_string(rest, mapping, max_variants)
            for rv in rest_variants:
                result_variants.append(char + rv)
        elif char in mapping:
            replacements = mapping[char]
            if not isinstance(replacements, list):
                replacements = [replacements]
            
            rest_variants = convert_string(rest, mapping, max_variants)
            for replacement in replacements:
                for rv in rest_variants[:max_variants]:  # Ограничиваем комбинаторный взрыв
                    variant = replacement + rv
                    if variant not in result_variants:
                        result_variants.append(variant)
                        if len(result_variants) >= max_variants:
                            return result_variants
        else:
            # Неизвестный символ - оставляем как есть
            rest_variants = convert_string(rest, mapping, max_variants)
            for rv in rest_variants:
                result_variants.append(char + rv)
        
        return result_variants[:max_variants]
    
    # Генерируем основные варианты
    # 1. Полная конвертация в латиницу (приоритет)
    if any(char in cyrillic_to_latin for char in text):
        latin_variants = convert_string(text, cyrillic_to_latin, max_variants=3)
        for lv in latin_variants:
            if lv not in variants:
                variants.append(lv)
    
    # 2. Для смешанных кодов - частичная конвертация
    match = re.match(r'^([A-ZА-Я]+)(\d+)([A-ZА-Я\-]+)?$', text)
    if match:
        prefix, numbers, suffix = match.groups()
        suffix = suffix or ''
        
        # Конвертируем префикс в латиницу
        if any(char in cyrillic_to_latin for char in prefix):
            prefix_variants = convert_string(prefix, cyrillic_to_latin, max_variants=2)
        else:
            prefix_variants = [prefix]
        
        # Обрабатываем суффикс
        if suffix:
            # Для суффиксов пробуем оба направления конвертации
            suffix_variants = []
            
            # Если суффикс кириллический - конвертируем в латиницу
            if any(char in cyrillic_to_latin for char in suffix):
                suffix_variants.extend(convert_string(suffix, cyrillic_to_latin, max_variants=3))
            
            # Если суффикс латинский - пробуем конвертировать в кириллицу
            if any(char in latin_to_cyrillic for char in suffix):
                suffix_variants.extend(convert_string(suffix, latin_to_cyrillic, max_variants=2))
            
            # Добавляем оригинальный суффикс
            if suffix not in suffix_variants:
                suffix_variants.append(suffix)
            
            # Комбинируем варианты
            for pv in prefix_variants[:2]:
                for sv in suffix_variants[:3]:
                    variant = pv + numbers + sv
                    if variant not in variants and len(variants) < 20:
                        variants.append(variant)
        else:
            # Только префикс и числа
            for pv in prefix_variants[:3]:
                variant = pv + numbers
                if variant not in variants:
                    variants.append(variant)
    
    # 3. Специальная обработка для известных паттернов
    special_suffixes = ['ОБС', 'ГИЭ', 'ГИИ', 'БТК', 'БАЛ', 'КЛЩ', 'ВПТ', 'ГЛЗ', 'ГСК', 'КМ', 'КР', 'ЛИК', 'НОС', 'ПРК', 'РОТ', 'СИН', 'ФК', 'АСП']
    
    for suffix in special_suffixes:
        if text.endswith(suffix):
            # Получаем префикс без суффикса
            prefix_part = text[:-len(suffix)]
            if any(char in cyrillic_to_latin for char in prefix_part):
                prefix_converted = convert_string(prefix_part, cyrillic_to_latin, max_variants=1)[0]
                variant = prefix_converted + suffix
                if variant not in variants:
                    variants.append(variant)
    
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    unique_variants = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique_variants.append(v)
    
    print(f"[DEBUG] Variants for '{text}': {unique_variants[:10]}")
    return unique_variants[:20]

def calculate_phonetic_score(query: str, test_code: str) -> float:
    """Вычисляет фонетическое сходство между строками."""
    
    # Сначала проверяем совпадение цифр
    query_digits = ''.join(c for c in query if c.isdigit())
    code_digits = ''.join(c for c in test_code if c.isdigit())
    
    # Если цифры не совпадают, снижаем оценку
    digit_penalty = 0
    if query_digits != code_digits:
        # Считаем количество несовпадающих цифр
        diff_count = sum(1 for i in range(min(len(query_digits), len(code_digits))) 
                        if query_digits[i] != code_digits[i])
        diff_count += abs(len(query_digits) - len(code_digits))
        digit_penalty = diff_count * 20  # -20 баллов за каждую неправильную цифру
    
    # Фонетический маппинг
    phonetic_map = {
        # Латиница
        'A': 'A', 'B': 'B', 'C': 'K', 'D': 'D', 'E': 'I', 'F': 'F',
        'G': 'G', 'H': 'H', 'I': 'I', 'J': 'J', 'K': 'K', 'L': 'L',
        'M': 'M', 'N': 'N', 'O': 'O', 'P': 'P', 'Q': 'K', 'R': 'R',
        'S': 'S', 'T': 'T', 'U': 'U', 'V': 'V', 'W': 'V', 'X': 'H',
        'Y': 'U', 'Z': 'Z',
        # Кириллица
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'I',
        'Ё': 'I', 'Ж': 'J', 'З': 'Z', 'И': 'I', 'Й': 'I', 'К': 'K',
        'Л': 'L', 'М': 'M', 'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R',
        'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'H', 'Ц': 'S',
        'Ч': 'CH', 'Ш': 'SH', 'Щ': 'SCH', 'Ы': 'I', 'Э': 'I', 'Ю': 'U',
        'Я': 'A'
    }
    
    def to_phonetic(s):
        result = ''
        s = s.upper()
        i = 0
        while i < len(s):
            if i < len(s) - 1:
                two_char = s[i:i+2]
                if two_char in ['PH', 'TH', 'CH', 'SH']:
                    if two_char == 'PH':
                        result += 'F'
                    elif two_char == 'TH':
                        result += 'T'
                    else:
                        result += two_char
                    i += 2
                    continue
            
            char = s[i]
            if char in phonetic_map:
                result += phonetic_map[char]
            elif char.isdigit():
                result += char
            i += 1
        
        return result
    
    query_phonetic = to_phonetic(query)
    code_phonetic = to_phonetic(test_code)
    
    # Точное совпадение
    if query_phonetic == code_phonetic:
        return max(0, 100.0 - digit_penalty)
    
    # Проверка префикса
    min_len = min(len(query_phonetic), len(code_phonetic))
    if min_len >= 4:
        if query_phonetic[:4] == code_phonetic[:4]:
            return max(0, 85.0 - digit_penalty)
    
    # Расчет схожести по символам
    matches = 0
    for i in range(min(len(query_phonetic), len(code_phonetic))):
        if query_phonetic[i] == code_phonetic[i]:
            matches += 1
    
    max_len = max(len(query_phonetic), len(code_phonetic))
    if max_len == 0:
        return 0.0
    
    base_score = (matches / max_len) * 100
    return max(0, base_score - digit_penalty)

async def smart_test_search(processor, original_query: str) -> Optional[tuple]:
    """Умный поиск с учетом различных вариантов написания."""
    
    # Добавляем проверку на None и пустую строку
    if not original_query:
        return None, None, None
    
    # Нормализуем запрос
    normalized_query = normalize_test_code(original_query)
    
    # Если после нормализации получили пустую строку
    if not normalized_query:
        return None, None, None
    
    # 1. Точный поиск по нормализованному коду
    results = processor.search_test(filter_dict={"test_code": normalized_query})
    if results:
        return results[0], normalized_query, "exact"
    
    # 2. Генерируем варианты и ищем
    variants = generate_test_code_variants(normalized_query)
    for variant in variants[:5]:
        results = processor.search_test(filter_dict={"test_code": variant})
        if results:
            return results[0], variant, "variant"
    
    # 3. Текстовый поиск
    text_results = processor.search_test(query=normalized_query, top_k=50)
    
    if text_results and text_results[0][1] > 0.8:
        return text_results[0], text_results[0][0].metadata.get('test_code'), "text"
    
    return None, None, None

async def safe_delete_message(message):
    """Безопасное удаление сообщения"""
    try:
        if message:
            await message.delete()
    except Exception:
        pass  # Игнорируем ошибки удаления
    
def split_long_message(text: str, max_length: int = 4000) -> list[str]:
    """Разбивает длинное сообщение на части"""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    current_part = ""
    
    # Разбиваем по строкам
    lines = text.split('\n')
    
    for line in lines:
        if len(current_part) + len(line) + 1 > max_length:
            if current_part:
                parts.append(current_part.strip())
                current_part = line
            else:
                # Если одна строка слишком длинная, режем её
                while len(line) > max_length:
                    parts.append(line[:max_length])
                    line = line[max_length:]
                current_part = line
        else:
            current_part += '\n' + line if current_part else line
    
    if current_part:
        parts.append(current_part.strip())
    
    return parts

def expand_query_with_abbreviations(query: str) -> str:
    """Expand query with known test abbreviations."""
    query_upper = query.upper()
    for abbr, expansion in TEST_ABBREVIATIONS.items():
        if abbr in query_upper:
            return f"{query} {expansion}"
    return query

def safe_html(text: str) -> str:
    """Экранирует HTML символы в тексте"""
    return html.escape(text)

def get_time_based_farewell(user_name: str = None):
    """Возвращает персонализированное прощание в зависимости от времени суток"""
    tz = pytz.timezone('Europe/Minsk')
    current_hour = datetime.now(tz).hour
    
    name_part = f", {user_name}" if user_name and user_name != 'друг' else ""
    
    if 4 <= current_hour < 12:
        return f"Рад был помочь{name_part}! Хорошего утра ☀️"
    elif 12 <= current_hour < 17:
        return f"Рад был помочь{name_part}! Хорошего дня 🤝"
    elif 17 <= current_hour < 22:
        return f"Рад был помочь{name_part}! Хорошего вечера 🌆"
    else:
        return f"Рад был помочь{name_part}! Доброй ночи 🌙"
    
def get_user_first_name(user):
    if not user:
        return 'друг'
    # Совместимость с dict и aiosqlite.Row
    name = user['name'] if 'name' in user.keys() else None
    if not name:
        return 'друг'
    full_name = name.strip()
    name_parts = full_name.split()
    if len(name_parts) >= 2 and ('user_type' in user.keys() and user['user_type'] == 'employee'):
        return name_parts[1]  # Для сотрудников: Фамилия Имя
    return name_parts[0]  # Для клиентов или однословных имен

def format_test_data(metadata: Dict) -> Dict:
    """Extract and format test metadata into standardized dictionary."""
    return {
        'type': metadata['type'],
        'test_code': metadata['test_code'],
        'test_name': metadata['test_name'],
        'container_type': metadata['container_type'],
        'container_number': metadata['container_number'],
        'preanalytics': metadata['preanalytics'],
        'storage_temp': metadata['storage_temp'],
        'department': metadata['department']
    }

def format_test_info_brief(test_data: Dict) -> str:
    """Format brief test information for initial search results."""
    t_type = 'Тест' if test_data['type'] == 'Тесты' else 'Профиль'
    # Экранируем HTML символы в названии теста
    test_name = html.escape(test_data['test_name'])
    department = html.escape(test_data['department'])
    
    return (
        f"<b>{t_type}: {test_data['test_code']} - {test_name}</b>\n"
        f"🧬 <b>Вид исследования:</b> {department}\n"
    )

def format_test_info(test_data: Dict) -> str:
    """Format full test information from metadata using HTML tags."""
    t_type = 'Тест' if test_data['type'] == 'Тесты' else 'Профиль'
    
    # Экранируем HTML символы во всех полях
    test_name = html.escape(test_data['test_name'])
    container_type = html.escape(test_data['container_type'])
    container_number = html.escape(str(test_data['container_number']))
    storage_temp = html.escape(test_data['storage_temp'])
    department = html.escape(test_data['department'])
    preanalytics = html.escape(test_data['preanalytics'])
    
    return (
        f"<b>{t_type}: {test_data['test_code']} - {test_name}</b>\n\n"
        f"🧪 <b>Тип контейнера:</b> {container_type}\n"
        f"🔢 <b>Номер контейнера:</b> {container_number}\n"
        f"❄️ <b>Температура:</b> {storage_temp}\n"
        f"🧬 <b>Вид исследования:</b> {department}\n"
        f"📋 <b>Преаналитика:</b> {preanalytics}\n\n"
    )
    
async def handle_general_question(message: Message, state: FSMContext, question_text: str):
    """Обработка общих вопросов через LLM."""
    user_id = message.from_user.id
    
    loading_msg = await message.answer("🤔 Обрабатываю ваш вопрос...")
    
    try:
        system_prompt = """Ты - ассистент ветеринарной лаборатории VetUnion. 
        Ты отвечаешь на все вопросы в области ветеринарии исходя из вопроса, который тебе задали и ты знаешь профессиональный сленг. 
        Отвечай кратко и по существу на русском языке."""
        
        response = await llm.agenerate([[
            SystemMessage(content=system_prompt),
            HumanMessage(content=question_text)
        ]])
        
        answer = response.generations[0][0].text.strip()
        answer = fix_bold(answer)  # Добавляем конвертацию markdown
        
        await loading_msg.delete()
        await message.answer(answer, parse_mode="HTML")
        
        # Клавиатура с опциями
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔢 Найти тест по коду", callback_data="search_by_code"),
                InlineKeyboardButton(text="📝 Найти по названию", callback_data="search_by_name")
            ]
        ])
        
        await message.answer("Что бы вы хотели сделать дальше?", reply_markup=keyboard)
        
    except Exception as e:
        print(f"[ERROR] General question handling failed: {e}")
        await loading_msg.delete()
        await message.answer("⚠️ Не удалось обработать вопрос. Попробуйте переформулировать.")

# Также добавим обработчики для callback кнопок, которые могут быть не определены:
@questions_router.callback_query(F.data == "search_by_code")
async def handle_search_by_code_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Введите код теста (например, AN5):", reply_markup=get_back_to_menu_kb())
    await state.set_state(QuestionStates.waiting_for_code)

@questions_router.callback_query(F.data == "search_by_name")
async def handle_search_by_name_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Введите название или описание теста:", reply_markup=get_back_to_menu_kb())
    await state.set_state(QuestionStates.waiting_for_name)

async def animate_loading(loading_msg: Message):
    """Animate loading message (edit text, not caption)."""
    animations = [
        "Обрабатываю ваш запрос...\n⏳ Анализирую данные...",
        "Обрабатываю ваш запрос...\n🔍 Поиск в базе VetUnion...",
        "Обрабатываю ваш запрос...\n🧠 Формирую ответ...",
    ]
    i = 0
    try:
        while True:
            await asyncio.sleep(2)
            i = (i + 1) % len(animations)
            await loading_msg.edit_text(animations[i])
    except (asyncio.CancelledError, Exception):
        pass

async def select_best_match(query: str, docs: list[tuple[Document, float]]) -> list[Document]:
    """Select best matching tests using LLM from multiple options."""
    if len(docs) == 1:
        return [docs[0][0]]
    
    options = "\n".join([
        f"{i}. {doc.metadata['test_name']} ({doc.metadata['test_code']}) - score: {score:.2f}"
        for i, (doc, score) in enumerate(docs, 1)
    ])
    
    prompt = f"""
    Select relevant tests for: "{query}"
    Return ONLY numbers of matching options (1-{len(docs)}) separated by commas.
    
    Options:
    {options}
    """
    
    try:
        response = await llm.agenerate([[SystemMessage(content=prompt)]])
        selected = response.generations[0][0].text.strip()
        
        if not selected:
            return [docs[0][0]]  # Fallback to top result
            
        selected_indices = []
        for num in selected.split(','):
            num = num.strip()
            if num.isdigit() and 1 <= int(num) <= len(docs):
                selected_indices.append(int(num) - 1)
                
        if not selected_indices:
            return [docs[0][0]]
            
        # Получаем выбранные документы с сохранением порядка LLM
        selected_docs_with_order = [(docs[i][0], idx) for idx, i in enumerate(selected_indices)]
        
        # Сортируем: сначала "Тесты", потом "Профили", внутри каждой группы сохраняем порядок LLM
        sorted_docs = sorted(selected_docs_with_order, key=lambda x: (
            0 if x[0].metadata.get('type') == 'Тесты' else 1,  # Тесты первыми
            x[1]  # Сохраняем порядок LLM внутри каждой группы
        ))
        
        return [doc for doc, _ in sorted_docs]
        
    except Exception:
        return [docs[0][0]]  # Fallback on error

async def show_personalized_suggestions(message: Message, state: FSMContext):
    """Показывает персонализированные подсказки при начале поиска"""
    user_id = message.from_user.id
    
    try:
        # Получаем подсказки
        suggestions = await db.get_search_suggestions(user_id)
        
        if suggestions:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            
            # Группируем по типам
            frequent = [s for s in suggestions if s['type'] == 'frequent']
            recent = [s for s in suggestions if s['type'] == 'recent']
            
            if frequent:
                # Добавляем заголовок
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text="⭐ Часто используемые:", callback_data="ignore")
                ])
                
                for sug in frequent[:3]:
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(
                            text=f"{sug['code']} - {sug['name'][:40]}... ({sug['frequency']}x)",
                            callback_data=f"quick_test:{sug['code']}"
                        )
                    ])
            
            if recent:
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(text="🕐 Недавние поиски:", callback_data="ignore")
                ])
                
                for sug in recent[:2]:
                    keyboard.inline_keyboard.append([
                        InlineKeyboardButton(
                            text=f"{sug['code']} - {sug['name'][:40]}...",
                            callback_data=f"quick_test:{sug['code']}"
                        )
                    ])
            
            await message.answer(
                "💡 Быстрый доступ к вашим тестам:",
                reply_markup=keyboard
            )
    except Exception as e:
        print(f"[ERROR] Failed to show personalized suggestions: {e}")
        # Не показываем ошибку пользователю, просто не показываем подсказки

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
            print(f"[DEBUG] Test {test_code} not found with exact search. Trying fuzzy...")
            fuzzy_results = await fuzzy_test_search(processor, test_code, threshold=85)
            
            if fuzzy_results:
                # Ищем точное совпадение среди fuzzy результатов
                for doc, score in fuzzy_results:
                    if doc.metadata.get('test_code', '').upper() == test_code.upper():
                        results = [(doc, score)]
                        print(f"[DEBUG] Found exact match in fuzzy results: {doc.metadata.get('test_code')}")
                        break
                
                # Если точного не нашли - берем первый с высоким score
                if not results and fuzzy_results[0][1] >= 90:
                    results = [fuzzy_results[0]]
                    print(f"[DEBUG] Using best fuzzy match: {fuzzy_results[0][0].metadata.get('test_code')} (score: {fuzzy_results[0][1]})")
        
        # Последняя попытка - текстовый поиск
        if not results:
            print(f"[DEBUG] Trying text search for {test_code}")
            text_results = processor.search_test(query=test_code, top_k=50)
            
            # Ищем точное совпадение кода
            for doc, score in text_results:
                doc_code = doc.metadata.get('test_code', '')
                # Проверяем точное совпадение с учетом регистра и пробелов
                if doc_code.strip().upper() == test_code.strip().upper():
                    results = [(doc, score)]
                    print(f"[DEBUG] Found via text search: {doc_code}")
                    break
        
        # Если все еще не нашли - используем smart_test_search
        if not results:
            result, found_variant, match_type = await smart_test_search(processor, test_code)
            if result:
                results = [result]
                print(f"[DEBUG] Found via smart search: {found_variant} (type: {match_type})")
        
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
            found_test_code=test_data['test_code'],
            search_type='code',
            success=True
        )
        await db.update_user_frequent_test(
            user_id=user_id,
            test_code=test_data['test_code'],
            test_name=test_data['test_name']
        )
        
        # Обновляем связанные тесты
        data = await state.get_data()
        if 'last_viewed_test' in data and data['last_viewed_test'] != test_data['test_code']:
            await db.update_related_tests(
                user_id=user_id,
                test_code_1=data['last_viewed_test'],
                test_code_2=test_data['test_code']
            )
        
        # Получаем связанные тесты из истории пользователя
        related_tests = await db.get_user_related_tests(user_id, test_data['test_code'])
        
        # Ищем похожие тесты для этого теста
        similar_tests = await fuzzy_test_search(processor, test_data['test_code'], threshold=40)
        
        # Фильтруем, чтобы не показывать сам тест
        similar_tests = [(d, s) for d, s in similar_tests if d.metadata.get('test_code') != test_data['test_code']]
        
        # Создаем клавиатуру если есть похожие или связанные
        reply_markup = None
        if related_tests or similar_tests:
            keyboard = []
            row = []
            
            # Сначала связанные из истории (приоритет)
            for related in related_tests[:4]:
                row.append(InlineKeyboardButton(
                    text=f"⭐ {related['test_code']}",
                    callback_data=TestCallback.pack("show_test", related['test_code'])
                ))
                if len(row) >= 2:
                    keyboard.append(row)
                    row = []
            
            # Затем похожие
            for doc, _ in similar_tests[:4]:
                if len(keyboard) * 2 + len(row) >= 8:  # Максимум 8 кнопок
                    break
                code = doc.metadata.get('test_code')
                if not any(r['test_code'] == code for r in related_tests):
                    row.append(InlineKeyboardButton(
                        text=code,
                        callback_data=TestCallback.pack("show_test", code)
                    ))
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
                "🎯 Рекомендуем также:",
                reply_markup=reply_markup
            )
        
        # Обновляем состояние с текущим тестом
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(current_test=test_data, last_viewed_test=test_data['test_code'])
        
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
    test_code = callback.data.split(':')[1]
    
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
            print(f"[DEBUG] Test {test_code} not found with filter. Trying fuzzy search...")
            fuzzy_results = await fuzzy_test_search(processor, test_code, threshold=90)
            
            if fuzzy_results:
                # Берем первый результат с высоким score
                results = [fuzzy_results[0]]
                print(f"[DEBUG] Found via fuzzy search: {results[0][0].metadata.get('test_code')}")
            else:
                # Пробуем текстовый поиск
                print(f"[DEBUG] Trying text search for {test_code}")
                text_results = processor.search_test(query=test_code, top_k=10)
                
                # Фильтруем по точному совпадению кода
                for doc, score in text_results:
                    doc_code = doc.metadata.get('test_code', '')
                    if doc_code.upper() == test_code.upper() or doc_code.upper() == normalized_code.upper():
                        results = [(doc, score)]
                        print(f"[DEBUG] Found via text search: {doc_code}")
                        break
        
        if not results:
            # Последняя попытка - используем smart_test_search
            result, found_variant, match_type = await smart_test_search(processor, test_code)
            if result:
                results = [result]
                print(f"[DEBUG] Found via smart search: {found_variant} (type: {match_type})")
        
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
            found_test_code=test_data['test_code'],
            search_type='code',
            success=True
        )
        await db.update_user_frequent_test(
            user_id=user_id,
            test_code=test_data['test_code'],
            test_name=test_data['test_name']
        )
        
        # Обновляем связанные тесты
        data = await state.get_data()
        if 'last_viewed_test' in data and data['last_viewed_test'] != test_data['test_code']:
            await db.update_related_tests(
                user_id=user_id,
                test_code_1=data['last_viewed_test'],
                test_code_2=test_data['test_code']
            )
        
        # Получаем связанные тесты из истории пользователя
        related_tests = await db.get_user_related_tests(user_id, test_data['test_code'])
        
        # Ищем похожие тесты для этого теста
        similar_tests = await fuzzy_test_search(processor, test_data['test_code'], threshold=40)
        
        # Фильтруем, чтобы не показывать сам тест
        similar_tests = [(d, s) for d, s in similar_tests if d.metadata.get('test_code') != test_data['test_code']]
        
        # Создаем клавиатуру если есть похожие или связанные
        reply_markup = None
        if related_tests or similar_tests:
            keyboard = []
            row = []
            
            # Сначала связанные из истории (приоритет)
            for related in related_tests[:4]:
                row.append(InlineKeyboardButton(
                    text=f"⭐ {related['test_code']}",
                    callback_data=TestCallback.pack("show_test", related['test_code'])
                ))
                if len(row) >= 2:
                    keyboard.append(row)
                    row = []
            
            # Затем похожие
            for doc, _ in similar_tests[:4]:
                if len(keyboard) * 2 + len(row) >= 8:  # Максимум 8 кнопок
                    break
                code = doc.metadata.get('test_code')
                if not any(r['test_code'] == code for r in related_tests):
                    row.append(InlineKeyboardButton(
                        text=code,
                        callback_data=TestCallback.pack("show_test", code)
                    ))
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
                "🎯 Рекомендуем также:",
                reply_markup=reply_markup
            )
        
        # Обновляем состояние с текущим тестом
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(current_test=test_data, last_viewed_test=test_data['test_code'])
        
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
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return

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
    role = user['role'] if 'role' in user.keys() else 'staff'
    user_name = get_user_first_name(user)
    
    # Исключение: если пользователь нажал "задать вопрос ассистенту" и не ввел вопрос
    if current_state == QuestionStates.waiting_for_search_type:
        # Возвращаем в главное меню без прощания
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
    role = user['role'] if 'role' in user.keys() else 'staff'
    await message.answer("Операция отменена.", reply_markup=get_menu_by_role(role))
    return

@questions_router.message(QuestionStates.waiting_for_search_type)
async def handle_universal_search(message: Message, state: FSMContext):
    """Универсальный обработчик запросов - автоматически определяет тип поиска."""
    text = message.text.strip()
    user_id = message.from_user.id
    
    # Проверяем, не кнопка ли это возврата или завершения диалога
    if text == "🔙 Вернуться в главное меню" or text == "❌ Завершить диалог":
        return
    
    # Расширенная проверка для разных вариантов
    # Проверяем не только коды, но и явные запросы
    search_indicators = [
        'покажи', 'найди', 'поиск', 'информация',
        'что такое', 'расскажи про', 'анализ на'
    ]
    
    text_lower = text.lower()
    is_search_query = any(indicator in text_lower for indicator in search_indicators)
    
    # Определяем тип запроса
    if is_test_code_pattern(text):
        # Это похоже на код теста
        await state.set_state(QuestionStates.waiting_for_code)
        await handle_code_search(message, state)
    elif is_search_query or len(text.split()) <= 3:
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
                user_id=user_id,
                request_type='question',
                request_text=text
            )
            # Обрабатываем как общий вопрос
            await handle_general_question(message, state, text)

@questions_router.message(QuestionStates.waiting_for_code)
async def handle_code_search(message: Message, state: FSMContext):
    """Handle test code search with smart matching and fuzzy suggestions."""
    data = await state.get_data()
    if data.get('is_processing', False):
        await message.answer(
            "⏳ Подождите, идет обработка предыдущего запроса...",
            reply_markup=get_back_to_menu_kb()
        )
        return
    
    await state.update_data(is_processing=True)
    
    user_id = message.from_user.id
    original_input = message.text.strip()
    
    # Сохраняем статистику вопроса
    await db.add_request_stat(
        user_id=user_id,
        request_type='question',
        request_text=original_input
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
        
        loading_msg = await message.answer("🔍 Ищу тест по коду...\n⏳ Анализирую данные...")
        if loading_msg:
            animation_task = asyncio.create_task(animate_loading(loading_msg))
        
        if current_task and current_task.cancelled():
            raise asyncio.CancelledError()
        
        processor = DataProcessor()
        processor.load_vector_store()
        
        # Нормализуем входной код (с учетом кириллицы)
        normalized_input = normalize_test_code(original_input)
        
        # Используем умный поиск
        result, found_variant, match_type = await smart_test_search(processor, original_input)
        
        if current_task and current_task.cancelled():
            raise asyncio.CancelledError()
        
        if not result:
            # Ищем похожие тесты с улучшенной фильтрацией
            similar_tests = await fuzzy_test_search(processor, normalized_input, threshold=30)
            
            if animation_task:
                animation_task.cancel()
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)
            
            await db.add_search_history(
                user_id=user_id,
                search_query=original_input,
                search_type='code',
                success=False
            )
            
            if similar_tests:
                # Показываем найденные варианты
                response = f"❌ Тест с кодом '<code>{normalized_input}</code>' не найден.\n"
                response += format_similar_tests_with_links(similar_tests, max_display=10)
                
                keyboard = create_similar_tests_keyboard(similar_tests[:20])
                
                await message.answer(
                    response + "\n<i>Нажмите на код теста в сообщении выше или выберите из кнопок ниже:</i>", 
                    parse_mode="HTML", 
                    reply_markup=keyboard,
                    disable_web_page_preview=True
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
            found_test_code=test_data['test_code'],
            search_type='code',
            success=True
        )
        
        await db.update_user_frequent_test(
            user_id=user_id,
            test_code=test_data['test_code'],
            test_name=test_data['test_name']
        )
        
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        
        # ИЗМЕНЕНО: Отправляем информацию с фото
        await send_test_info_with_photo(message, test_data, response)
        
        await message.answer(
            "Можете задать вопрос об этом тесте или выбрать действие:", 
            reply_markup=get_dialog_kb()
        )
        
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(current_test=test_data, last_viewed_test=test_data['test_code'])
        
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
        
        await message.answer("⚠️ Ошибка при поиске. Попробуйте позже", reply_markup=get_back_to_menu_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)
    
    finally:
        await state.update_data(is_processing=False, current_task=None)

@questions_router.message(QuestionStates.in_dialog, F.text == "🔄 Новый вопрос")
async def handle_new_question_in_dialog(message: Message, state: FSMContext):
    """Обработчик для новых вопросов в режиме диалога."""
    # Сохраняем контекст последних тестов
    data = await state.get_data()
    last_viewed = data.get('last_viewed_test')
    
    await message.answer(
        "💡 Введите код теста (например: AN5) или опишите, что вы ищете:",
        reply_markup=get_back_to_menu_kb()
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
    last_viewed = data.get('last_viewed_test')
    
    await callback.message.answer(
        "💡 Введите код теста (например: AN5) или опишите, что вы ищете:",
        reply_markup=get_back_to_menu_kb()
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
    test_data = data.get('current_test')
    
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
        user_id=user_id,
        request_type='question',
        request_text=text
    )
    
    gif_msg = None
    loading_msg = None
    animation_task = None

    try:
        if LOADING_GIF_ID:
            gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
            loading_msg = await message.answer("Обрабатываю ваш запрос...\n⏳ Анализирую данные...")
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
                user_id=user_id,
                search_query=text,
                search_type='text',
                success=False
            )
            raise ValueError("Тесты не найдены")
            
        selected_docs = await select_best_match(text, rag_hits)
        
        # Записываем успешный поиск
        for doc in selected_docs[:1]:  # Записываем только первый найденный
            await db.add_search_history(
                user_id=user_id,
                search_query=text,
                found_test_code=doc.metadata['test_code'],
                search_type='text',
                success=True
            )
            
            await db.update_user_frequent_test(
                user_id=user_id,
                test_code=doc.metadata['test_code'],
                test_name=doc.metadata['test_name']
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
                test_code = test_data['test_code']
                test_name = html.escape(test_data['test_name'])
                department = html.escape(test_data['department'])
                
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
                response, 
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
            # Создаем компактную клавиатуру с кнопками (как дополнение к ссылкам)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            row = []
            
            for i, doc in enumerate(selected_docs[:15]):  # До 15 кнопок
                test_code = doc.metadata['test_code']
                row.append(InlineKeyboardButton(
                    text=test_code,
                    callback_data=TestCallback.pack("show_test", test_code)
                ))
                
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
                parse_mode="HTML"
            )

        else:
            # Один результат
            test_data = format_test_data(selected_docs[0].metadata)
            response = format_test_info(test_data)
            
            # Добавляем похожие тесты с кликабельными ссылками
            similar_tests = await fuzzy_test_search(processor, test_data['test_code'], threshold=40)
            similar_tests = [(d, s) for d, s in similar_tests if d.metadata.get('test_code') != test_data['test_code']]
            
            if similar_tests:
                response += format_similar_tests_with_links(similar_tests[:5])
            
            # ИЗМЕНЕНО: Отправляем с фото
            await send_test_info_with_photo(message, test_data, response)
            
            # Показываем клавиатуру диалога
            await message.answer(
                "Можете задать вопрос об этом тесте или выбрать действие:",
                reply_markup=get_dialog_kb()
            )
        
        # Сохраняем последний найденный тест для диалога
        await state.set_state(QuestionStates.in_dialog)
        if selected_docs:
            last_test_data = format_test_data(selected_docs[0].metadata)
            await state.update_data(current_test=last_test_data, last_viewed_test=last_test_data['test_code'])
            
    except Exception as e:
        print(f"[ERROR] Name search failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Безопасная очистка при ошибке
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        
        error_msg = "❌ Тесты не найдены" if str(e) == "Тесты не найдены" else "⚠️ Ошибка поиска. Попробуйте позже."
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
    test_data = data.get('current_test')
    
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
        await message.answer("Контекст потерян. Задайте новый вопрос.", reply_markup=get_back_to_menu_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)
        return
    
    # Если это вопрос про текущий тест - сначала пробуем обработать через LLM
    gif_msg = None
    loading_msg = None
    animation_task = None
    
    try:
        gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
        loading_msg = await message.answer("Обрабатываю ваш запрос...\n⏳ Анализирую данные...")
        animation_task = asyncio.create_task(animate_loading(loading_msg))
        
        system_msg = SystemMessage(content=f"""
            Ты - ассистент лаборатории VetUnion и отвечаешь только в области ветеринарии. 
            
            Текущий тест:
            Код: {test_data['test_code']}
            Название: {test_data['test_name']}
            
            ВАЖНОЕ ПРАВИЛО:
            Если пользователь спрашивает про ДРУГОЙ тест или анализ (упоминает другой код, название или тип анализа),
            ты ДОЛЖЕН ответить ТОЧНО так:
            "NEED_NEW_SEARCH: [запрос пользователя]"
            
            Если вопрос касается текущего теста или просто пользователь хочет поинтересоваться по другому вопросу, предоставляй всю необходимую информацию в области ветеринарии с пониманием профессионального сленга.
        """)
        
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
        
async def send_test_info_with_photo(message: Message, test_data: Dict, response_text: str):
    """Отправляет информацию о тесте с фото контейнера если оно есть"""
    # Получаем номера контейнеров
    container_numbers = db.parse_container_numbers(str(test_data.get('container_number', '')))
    
    if container_numbers:
        # Получаем фото первого контейнера
        first_photo = await db.get_container_photo(container_numbers[0])
        
        if first_photo:
            try:
                # Отправляем фото с полной информацией в подписи
                await message.answer_photo(
                    photo=first_photo,
                    caption=response_text,
                    parse_mode="HTML"
                )
                
                # Если есть еще контейнеры - отправляем их дополнительными фото
                if len(container_numbers) > 1:
                    for num in container_numbers[1:]:
                        photo_id = await db.get_container_photo(num)
                        if photo_id:
                            try:
                                await message.answer_photo(
                                    photo=photo_id,
                                    caption=f"🧪 Дополнительный контейнер №{num}",
                                    parse_mode="HTML"
                                )
                            except:
                                pass
                return True
            except Exception as e:
                print(f"[ERROR] Failed to send photo with caption: {e}")
    
    # Если фото нет - отправляем обычное текстовое сообщение
    await message.answer(response_text, parse_mode="HTML")
    return False

async def handle_context_switch(message: Message, state: FSMContext, new_query: str):
    """Обрабатывает переключение контекста на новый тест."""
    
    # Сохраняем историю
    data = await state.get_data()
    if 'current_test' in data:
        last_test = data['current_test']['test_code']
        # Можно сохранить в историю диалога
        await state.update_data(previous_tests=data.get('previous_tests', []) + [last_test])
    
    # Определяем тип поиска для нового запроса
    if is_test_code_pattern(new_query):
        await state.set_state(QuestionStates.waiting_for_code)
        message.text = new_query  # Подменяем текст для обработчика
        await handle_code_search(message, state)
    else:
        await state.set_state(QuestionStates.waiting_for_name)
        message.text = new_query
        await handle_name_search(message, state)

__all__ = [
    'questions_router',
    'smart_test_search',
    'format_test_data',
    'format_test_info',
    'fuzzy_test_search',
    'format_similar_tests_with_links',
    'QuestionStates',
    'get_dialog_kb',
    'create_test_link',
    'BOT_USERNAME',
    'normalize_test_code',
    'simple_translit',
    'reverse_translit'
]
