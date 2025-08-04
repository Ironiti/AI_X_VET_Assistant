from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_menu_by_role, get_dialog_kb, get_back_to_menu_kb, get_search_type_kb
from langchain.schema import SystemMessage, HumanMessage, Document
import pytz
import asyncio
import html
import re
from typing import Optional, Dict, List, Tuple
from fuzzywuzzy import fuzz, process
from datetime import datetime
from src.database.db_init import db
from src.data_vectorization import DataProcessor
from models.models_init import qwen3_32b_instruct as llm

# LOADING_GIF_ID = "CgACAgIAAxkBAAMIaGr_qy1Wxaw2VrBrm3dwOAkYji4AAu54AAKmqHlJAtZWBziZvaA2BA"
LOADING_GIF_ID = "CgACAgIAAxkBAAIBFGiBcXtGY7OZvr3-L1dZIBRNqSztAALueAACpqh5Scn4VmIRb4UjNgQ"
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
}

def is_test_code_pattern(text: str) -> bool:
    """Проверяет, соответствует ли текст паттерну кода теста."""
    # Убираем пробелы и приводим к верхнему регистру
    text = text.strip().upper().replace(' ', '')
    
    # Паттерны для разных вариантов
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

def normalize_test_code(text: str) -> str:
    """Нормализует введенный код теста."""
    # Убираем пробелы
    text = text.strip().upper().replace(' ', '')
    
    # Если только цифры - добавляем AN
    if text.isdigit():
        text = f"AN{text}"
    
    # Если начинается с цифр - добавляем AN в начало
    elif re.match(r'^\d', text):
        text = f"AN{text}"
    
    return text

def calculate_fuzzy_score(query: str, test_code: str, test_name: str = "") -> float:
    """Вычисляет fuzzy score для теста."""
    query = query.upper()
    test_code = test_code.upper()
    
    # Проверяем точное совпадение
    if query == test_code:
        return 100.0
    
    # Проверяем совпадение цифр
    query_digits = ''.join(c for c in query if c.isdigit())
    code_digits = ''.join(c for c in test_code if c.isdigit())
    
    # Базовый fuzzy score для кода
    code_score = fuzz.ratio(query, test_code)
    
    # Дополнительные баллы за совпадение цифр
    digit_bonus = 0
    if query_digits and code_digits and query_digits == code_digits:
        digit_bonus = 20
    
    # Проверяем префикс
    prefix_bonus = 0
    if len(query) >= 3 and len(test_code) >= 3:
        if test_code.startswith(query[:3]):
            prefix_bonus = 15
    
    # Если есть название теста, проверяем и его
    name_score = 0
    if test_name:
        name_score = fuzz.partial_ratio(query.lower(), test_name.lower()) * 0.3
    
    # Комбинированный score
    total_score = min(100, code_score + digit_bonus + prefix_bonus + name_score)
    
    return total_score

async def fuzzy_test_search(processor: DataProcessor, query: str, threshold: float = 50) -> List[Tuple[Document, float]]:
    """Fuzzy поиск похожих тестов."""
    query = query.upper()
    
    # Получаем больше результатов для анализа
    all_tests = processor.search_test(query="", top_k=2000)
    
    fuzzy_results = []
    seen_codes = set()
    
    for doc, _ in all_tests:
        test_code = doc.metadata.get('test_code', '')
        test_name = doc.metadata.get('test_name', '')
        
        if test_code in seen_codes:
            continue
            
        # Вычисляем fuzzy score
        score = calculate_fuzzy_score(query, test_code, test_name)
        
        if score >= threshold:
            fuzzy_results.append((doc, score))
            seen_codes.add(test_code)
    
    # Сортируем по убыванию score
    fuzzy_results.sort(key=lambda x: x[1], reverse=True)
    
    # Возвращаем топ-30 результатов
    return fuzzy_results[:30]

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
    
    # Добавляем служебные кнопки
    keyboard.append([
        InlineKeyboardButton(text="🔄 Новый поиск", callback_data="new_search"),
        InlineKeyboardButton(text="❌ Закрыть", callback_data="close_keyboard")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

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
    
    # Генерируем варианты
    variants = generate_test_code_variants(original_query)
    
    # 1. Точный поиск по всем вариантам
    for variant in variants:
        results = processor.search_test(filter_dict={"test_code": variant})
        if results:
            print(f"[DEBUG] Found exact match with variant: {variant}")
            return results[0], variant, "exact"
    
    # 2. Текстовый поиск с фильтрацией
    text_results = processor.search_test(query=original_query.upper(), top_k=50)
    
    best_match = None
    best_score = 0
    best_variant = None
    
    for doc, base_score in text_results:
        test_code = doc.metadata.get('test_code', '')
        
        # Проверяем все варианты
        for variant in variants:
            if test_code == variant:
                return (doc, base_score), variant, "text_exact"
            
            # Проверяем префикс
            if test_code.startswith(variant[:3]):
                phonetic_score = calculate_phonetic_score(variant, test_code)
                combined_score = base_score * 0.3 + phonetic_score * 0.7
                
                if combined_score > best_score:
                    best_score = combined_score
                    best_match = (doc, base_score)
                    best_variant = test_code
    
    # 3. Возвращаем лучшее совпадение, если оно достаточно хорошее
    if best_match and best_score > 50:
        print(f"[DEBUG] Found phonetic match: {best_variant} (score: {best_score:.1f})")
        return best_match, best_variant, "phonetic"
    
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

def format_test_info(test_data: Dict) -> str:
    """Format test information from metadata using HTML tags."""
    t_type = 'Тест' if test_data['type'] == 'Тесты' else 'Профиль'
    return (
        f"<b>{t_type}: {test_data['test_code']} - {test_data['test_name']}</b>\n\n"
        f"📋 <b>Преаналитика:</b> {test_data['preanalytics']}\n"
        f"🧪 <b>Тип контейнера:</b> {test_data['container_type']}\n"
        f"🔢 <b>Номер контейнера:</b> {test_data['container_number']}\n"
        f"❄️ <b>Температура:</b> {test_data['storage_temp']}\n"
        f"🧬 <b>Вид исследования:</b> {test_data['department']}\n\n"
    )
    
async def handle_general_question(message: Message, state: FSMContext, question_text: str):
    """Обработка общих вопросов через LLM."""
    user_id = message.from_user.id
    
    loading_msg = await message.answer("🤔 Обрабатываю ваш вопрос...")
    
    try:
        system_prompt = """Ты - ассистент лаборатории VetUnion. 
        Отвечай на вопросы о лабораторных исследованиях, преаналитике, условиях хранения образцов.
        Если вопрос касается конкретного теста, предложи воспользоваться поиском по коду или названию.
        Отвечай кратко и по существу на русском языке."""
        
        response = await llm.agenerate([[
            SystemMessage(content=system_prompt),
            HumanMessage(content=question_text)
        ]])
        
        answer = response.generations[0][0].text.strip()
        
        await db.add_request_stat(
            user_id=user_id,
            request_type='general_question',
            request_text=question_text
        )
        
        await loading_msg.delete()
        await message.answer(answer, parse_mode="HTML")
        
        # Клавиатура с опциями
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔢 Найти тест по коду", callback_data="search_by_code"),
                InlineKeyboardButton(text="📝 Найти по названию", callback_data="search_by_name")
            ],
            [InlineKeyboardButton(text="🔄 Новый вопрос", callback_data="new_search")]
        ])
        
        await message.answer("Что бы вы хотели сделать дальше?", reply_markup=keyboard)
        
    except Exception as e:
        print(f"[ERROR] General question handling failed: {e}")
        await loading_msg.delete()
        await message.answer("⚠️ Не удалось обработать вопрос. Попробуйте переформулировать.")

async def check_if_needs_new_search(query: str, current_test_data: Dict) -> bool:
    """Проверяет, требуется ли новый поиск вместо ответа о текущем тесте."""
    
    if not current_test_data:
        return True
    
    query_lower = query.lower()
    current_test_name = current_test_data['test_name'].lower() if current_test_data else ""
    
    # Ключевые слова, указывающие на поиск другого теста
    other_test_indicators = [
        'другой тест', 'другой анализ', 'еще один', 'а что насчет',
        'а если', 'покажи', 'найди', 'поиск', 'информация о'
    ]
    
    # Проверяем явные индикаторы
    for indicator in other_test_indicators:
        if indicator in query_lower:
            return True
    
    # Список общих типов анализов
    test_types = {
        'кровь': ['общий анализ крови', 'оак', 'гематология', 'клинический анализ крови'],
        'моча': ['общий анализ мочи', 'оам', 'анализ мочи', 'моча'],
        'биохимия': ['биохимический', 'биохимия', 'бх'],
        'гормоны': ['гормон', 'ттг', 'т3', 'т4', 'тиреотропный'],
        'инфекции': ['пцр', 'ифа', 'антитела', 'вирус'],
        'кал': ['кал', 'копрограмма', 'фекалии'],
        'цитология': ['цитология', 'мазок', 'соскоб']
    }
    
    # Проверяем, упоминается ли другой тип анализа
    current_type = None
    mentioned_type = None
    
    # Определяем тип текущего теста
    for test_type, keywords in test_types.items():
        for keyword in keywords:
            if keyword in current_test_name:
                current_type = test_type
                break
    
    # Проверяем, какой тип упоминается в запросе
    for test_type, keywords in test_types.items():
        for keyword in keywords:
            if keyword in query_lower:
                mentioned_type = test_type
                break
    
    # Если упоминается другой тип теста - нужен новый поиск
    if mentioned_type and mentioned_type != current_type:
        return True
    
    # Проверяем упоминание конкретных тестов
    # Если в запросе есть паттерн кода теста, отличный от текущего
    potential_codes = re.findall(r'\b[AА][NН]?\d+\b', query.upper())
    if potential_codes:
        for code in potential_codes:
            if normalize_test_code(code) != current_test_data['test_code']:
                return True
    
    # Проверяем, не спрашивает ли о совершенно другом
    # Например, если текущий тест про кровь, а спрашивают про мочу
    if current_type == 'кровь' and any(word in query_lower for word in ['моч', 'урин']):
        return True
    if current_type == 'моча' and any(word in query_lower for word in ['кров', 'гемат', 'эритроцит']):
        return True
    
    return False

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
        
        # Ищем тест по коду
        results = processor.search_test(filter_dict={"test_code": test_code})
        
        if not results:
            await callback.message.answer(f"❌ Тест {test_code} не найден")
            return
            
        doc = results[0][0]
        test_data = format_test_data(doc.metadata)
        
        # Формируем ответ
        response = f"<b>Информация о выбранном тесте:</b>\n\n"
        response += format_test_info(test_data)
        
        # Обновляем статистику
        user_id = callback.from_user.id
        await db.add_search_history(
            user_id=user_id,
            search_query=f"Выбор из списка: {test_code}",
            found_test_code=test_code,
            search_type='code',
            success=True
        )
        await db.update_user_frequent_test(
            user_id=user_id,
            test_code=test_code,
            test_name=test_data['test_name']
        )
        
        # Обновляем связанные тесты
        data = await state.get_data()
        if 'last_viewed_test' in data and data['last_viewed_test'] != test_code:
            await db.update_related_tests(
                user_id=user_id,
                test_code_1=data['last_viewed_test'],
                test_code_2=test_code
            )
        
        # Получаем связанные тесты из истории пользователя
        related_tests = await db.get_user_related_tests(user_id, test_code)
        
        # Ищем похожие тесты для этого теста
        similar_tests = await fuzzy_test_search(processor, test_code, threshold=40)
        
        # Фильтруем, чтобы не показывать сам тест
        similar_tests = [(d, s) for d, s in similar_tests if d.metadata.get('test_code') != test_code]
        
        # Создаем клавиатуру если есть похожие или связанные
        reply_markup = None
        if related_tests or similar_tests:
            response += "\n<b>🎯 Рекомендуем также:</b>"
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
            
            keyboard.append([
                InlineKeyboardButton(text="🔄 Новый поиск", callback_data="new_search"),
                InlineKeyboardButton(text="❌ Закрыть", callback_data="close_keyboard")
            ])
            
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        # Отправляем как новое сообщение
        await callback.message.answer(
            response, 
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        
        # Обновляем состояние с текущим тестом
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(current_test=test_data, last_viewed_test=test_code)
        
        # Показываем клавиатуру для продолжения диалога
        await callback.message.answer(
            "Можете задать вопрос об этом тесте или выбрать действие:",
            reply_markup=get_dialog_kb()
        )
        
    except Exception as e:
        print(f"[ERROR] Callback handling failed: {e}")
        await callback.message.answer("⚠️ Ошибка при загрузке информации о тесте")

@questions_router.callback_query(F.data.startswith("quick_test:"))
async def handle_quick_test_selection(callback: CallbackQuery, state: FSMContext):
    """Обработчик быстрого выбора теста из подсказок"""
    test_code = callback.data.split(':')[1]
    
    # Получаем информацию о тесте
    test_info = await db.get_test_by_code(test_code)
    
    if test_info:
        # Формируем полный ответ с информацией о тесте
        response_text = (
            f"🔬 <b>{test_info['test_name']}</b>\n"
            f"📋 Код: {test_info['test_code']}\n"
            f"🏢 Отдел: {test_info['department']}\n"
            f"🧪 Контейнер: {test_info['container_type']}\n"
            f"❄️ Хранение: {test_info['storage_temp']}\n\n"
            f"📝 Преаналитика:\n{test_info['preanalytics']}"
        )
        
        await callback.message.answer(response_text, parse_mode="HTML")
        
        # Обновляем статистику
        await db.update_user_frequent_test(
            callback.from_user.id, 
            test_info['test_code'],
            test_info['test_name']
        )
    else:
        await callback.message.answer("❌ Тест не найден")
    
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

# Глобальный хендлер для кнопки возврата в меню (работает в любом состоянии)
@questions_router.message(F.text == "🔙 Вернуться в главное меню")
async def handle_back_to_menu(message: Message, state: FSMContext):
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
    
    # Проверяем, не кнопка ли это возврата
    if text == "🔙 Вернуться в главное меню":
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
            # Обрабатываем как общий вопрос
            await handle_general_question(message, state, text)

@questions_router.message(QuestionStates.waiting_for_code)
async def handle_code_search(message: Message, state: FSMContext):
    """Handle test code search with smart matching and fuzzy suggestions."""
    # Проверка на параллельную обработку
    data = await state.get_data()
    if data.get('is_processing', False):
        await message.answer(
            "⏳ Подождите, идет обработка предыдущего запроса...",
            reply_markup=get_back_to_menu_kb()
        )
        return
    
    # Устанавливаем флаг обработки
    await state.update_data(is_processing=True)
    
    user_id = message.from_user.id
    original_input = message.text.strip()
    
    # Инициализируем переменные
    gif_msg = None
    loading_msg = None
    animation_task = None

    try:
        # Создаем задачу для отслеживания
        current_task = asyncio.current_task()
        await state.update_data(current_task=current_task)
        
        # Безопасная отправка GIF
        try:
            if LOADING_GIF_ID:
                gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
        except Exception:
            gif_msg = None
        
        loading_msg = await message.answer("🔍 Ищу тест по коду...\n⏳ Анализирую данные...")
        if loading_msg:
            animation_task = asyncio.create_task(animate_loading(loading_msg))
        
        # Проверяем, не отменена ли задача
        if current_task and current_task.cancelled():
            raise asyncio.CancelledError()
        
        processor = DataProcessor()
        processor.load_vector_store()
        
        # Нормализуем входной код
        normalized_input = normalize_test_code(original_input)
        
        # Сначала проверяем персонализированные результаты
        user_suggestions = await db.get_search_suggestions(user_id, normalized_input)
        
        # Если есть точное совпадение в истории пользователя
        if user_suggestions:
            for sug in user_suggestions:
                if sug['code'].upper() == normalized_input.upper():
                    # Нашли в истории - сразу показываем
                    results = processor.search_test(filter_dict={"test_code": sug['code']})
                    if results:
                        result = results[0]
                        found_variant = sug['code']
                        match_type = "personalized"
                        break
        
        # Если не нашли в истории - используем умный поиск
        if 'result' not in locals():
            result, found_variant, match_type = await smart_test_search(processor, normalized_input)
        
        # Проверяем, не отменена ли задача
        if current_task and current_task.cancelled():
            raise asyncio.CancelledError()
        
        if not result:
            # Ищем похожие тесты - увеличиваем количество
            similar_tests = await fuzzy_test_search(processor, normalized_input, threshold=30)
            
            if animation_task:
                animation_task.cancel()
            await safe_delete_message(loading_msg)
            await safe_delete_message(gif_msg)
            
            # Записываем неудачный поиск
            await db.add_search_history(
                user_id=user_id,
                search_query=original_input,
                search_type='code',
                success=False
            )
            
            if similar_tests:
                # Показываем ВСЕ найденные варианты (до 20)
                response = f"❌ Тест с кодом '<code>{original_input.upper()}</code>' не найден.\n"
                response += format_similar_tests_text(similar_tests, max_display=20)
                
                keyboard = create_similar_tests_keyboard(similar_tests[:20])
                
                await message.answer(
                    response + "\n<i>Выберите код теста из кнопок ниже:</i>", 
                    parse_mode="HTML", 
                    reply_markup=keyboard
                )
            else:
                error_msg = f"❌ Тест с кодом '{original_input.upper()}' не найден.\n"
                error_msg += "Попробуйте ввести другой код или опишите, что вы ищете."
                await message.answer(error_msg, reply_markup=get_back_to_menu_kb())
            
            await state.set_state(QuestionStates.waiting_for_search_type)
            return
            
        # Найден результат
        doc = result[0]
        test_data = format_test_data(doc.metadata)
        
        response = ""
        if match_type == "personalized":
            response = f"<i>⭐ Из вашей истории поиска:</i>\n\n"
        elif match_type == "phonetic" and found_variant != original_input.upper():
            response = f"<i>По запросу '{original_input.upper()}' найден тест:</i>\n\n"
        
        response += format_test_info(test_data)
        
        # Сохраняем успешный поиск
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
        
        # Обновляем связанные тесты
        data = await state.get_data()
        if 'last_viewed_test' in data and data['last_viewed_test'] != test_data['test_code']:
            await db.update_related_tests(
                user_id=user_id,
                test_code_1=data['last_viewed_test'],
                test_code_2=test_data['test_code']
            )
        
        # Получаем связанные тесты
        related_tests = await db.get_user_related_tests(user_id, test_data['test_code'])
        
        # Ищем похожие тесты
        similar_tests = await fuzzy_test_search(processor, test_data['test_code'], threshold=50)
        similar_tests = [(d, s) for d, s in similar_tests if d.metadata.get('test_code') != test_data['test_code']]
        
        # Добавляем текст о похожих тестах если есть
        if related_tests or similar_tests:
            response += "\n<b>📋 Рекомендуем также:</b>\n"
            
            # Сначала связанные из истории
            for related in related_tests[:3]:
                response += f"• ⭐ <code>{related['test_code']}</code> - {related['test_name'][:50]}...\n"
            
            # Затем похожие
            shown_codes = {r['test_code'] for r in related_tests}
            for doc, _ in similar_tests[:5]:
                if doc.metadata['test_code'] not in shown_codes:
                    response += f"• <code>{doc.metadata['test_code']}</code> - {doc.metadata['test_name'][:50]}...\n"
        
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        
        # Отправляем результат
        await message.answer(response, parse_mode="HTML")
        
        # ВАЖНО: Создаем inline клавиатуру с похожими тестами
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []
        
        # Добавляем связанные тесты
        for related in related_tests[:6]:
            row.append(InlineKeyboardButton(
                text=f"⭐ {related['test_code']}",
                callback_data=TestCallback.pack("show_test", related['test_code'])
            ))
            if len(row) >= 3:
                keyboard.inline_keyboard.append(row)
                row = []
        
        # Добавляем похожие тесты
        shown_codes = {r['test_code'] for r in related_tests}
        for doc, _ in similar_tests[:10]:
            if len(keyboard.inline_keyboard) * 3 + len(row) >= 15:  # Максимум 15 кнопок
                break
            if doc.metadata['test_code'] not in shown_codes:
                row.append(InlineKeyboardButton(
                    text=doc.metadata['test_code'],
                    callback_data=TestCallback.pack("show_test", doc.metadata['test_code'])
                ))
                if len(row) >= 3:
                    keyboard.inline_keyboard.append(row)
                    row = []
        
        if row:
            keyboard.inline_keyboard.append(row)
        
        if keyboard.inline_keyboard:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="🔄 Новый поиск", callback_data="new_search"),
                InlineKeyboardButton(text="❌ Закрыть", callback_data="close_keyboard")
            ])
            
            await message.answer(
                "🔍 Выберите похожий тест или задайте вопрос:",
                reply_markup=keyboard
            )
        
        # Показываем основную клавиатуру диалога
        await message.answer(
            "Можете задать вопрос об этом тесте или выбрать действие:", 
            reply_markup=get_dialog_kb()
        )
        
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(current_test=test_data, last_viewed_test=test_data['test_code'])
        
    except asyncio.CancelledError:
        # Задача была отменена
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
        # Сбрасываем флаг обработки
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

@questions_router.message(QuestionStates.waiting_for_name)
async def handle_name_search(message: Message, state: FSMContext):
    """Handle test name search using RAG."""
    user_id = message.from_user.id
    text = message.text.strip()
    
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
            # Show multiple results with full info, splitting into multiple messages if needed
            
            # Подготавливаем полные данные для всех тестов
            full_test_responses = []
            for i, doc in enumerate(selected_docs):
                test_data = format_test_data(doc.metadata)
                full_response = f"<b>{i+1}.</b> {format_test_info(test_data)}\n\n"
                full_test_responses.append(full_response)
            
            # Группируем ответы в сообщения, не превышающие 4000 символов
            messages_to_send = []
            current_message = "Найдено несколько подходящих тестов:\n\n"
            
            for test_response in full_test_responses:
                # Проверяем, поместится ли текущий тест в текущее сообщение
                if len(current_message + test_response) <= 4000:
                    current_message += test_response
                else:
                    # Если текущее сообщение не пустое, добавляем его в список
                    if current_message.strip() != "Найдено несколько подходящих тестов:":
                        messages_to_send.append(current_message)
                    
                    # Начинаем новое сообщение с текущим тестом
                    current_message = test_response
            
            # Добавляем последнее сообщение, если оно не пустое
            if current_message.strip():
                messages_to_send.append(current_message)
            
            # Отправляем все сообщения
            for message_text in messages_to_send:
                await message.answer(message_text, parse_mode="HTML")
            
            # Создаем клавиатуру для выбора
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            row = []
            
            for i, doc in enumerate(selected_docs[:15]):  # До 15 кнопок
                row.append(InlineKeyboardButton(
                    text=doc.metadata['test_code'],
                    callback_data=TestCallback.pack("show_test", doc.metadata['test_code'])
                ))
                if len(row) >= 3:
                    keyboard.inline_keyboard.append(row)
                    row = []
            
            if row:
                keyboard.inline_keyboard.append(row)
            
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="🔄 Новый поиск", callback_data="new_search")
            ])
            
            await message.answer(
                "Выберите интересующий тест:",
                reply_markup=keyboard
            )

        else:
            # Single result
            test_data = format_test_data(selected_docs[0].metadata)
            response = format_test_info(test_data)
            
            # Проверяем длину и отправляем
            if len(response) > 4000:
                # Если даже один результат слишком длинный, обрезаем преаналитику
                test_data['preanalytics'] = test_data['preanalytics'][:500] + "..."
                response = format_test_info(test_data)
            
            await message.answer(response, parse_mode="HTML")
            
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
    """Handle follow-up questions using LLM with smart context switching."""
    text = message.text.strip()
    user_id = message.from_user.id
    
    if text == "❌ Завершить диалог":
        await state.clear()
        user = await db.get_user(user_id)
        role = user['role'] if 'role' in user.keys() else 'staff'
        user_name = get_user_first_name(user)
        farewell = get_time_based_farewell(user_name)
        await message.answer(farewell, reply_markup=get_menu_by_role(role))
        return
        
    if text == "🔄 Новый вопрос":
        await handle_new_question_in_dialog(message, state)
        return
    
    data = await state.get_data()
    test_data = data['current_test'] if 'current_test' in data else None
    
    # Проверяем, не новый ли это поиск по коду
    if is_test_code_pattern(text):
        await state.set_state(QuestionStates.waiting_for_code)
        await handle_code_search(message, state)
        return
    
    # Анализируем, спрашивает ли пользователь о другом тесте
    needs_new_search = await check_if_needs_new_search(text, test_data)
    
    if needs_new_search:
        # Пользователь спрашивает о другом тесте - делаем новый поиск
        await state.set_state(QuestionStates.waiting_for_name)
        await handle_name_search(message, state)
        return
    
    if not test_data:
        await message.answer("Контекст потерян. Задайте новый вопрос.", reply_markup=get_back_to_menu_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)
        return
        
    gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
    loading_msg = await message.answer("Обрабатываю ваш запрос...\n⏳ Анализирую данные...")
    animation_task = asyncio.create_task(animate_loading(loading_msg))
    
    try:
        # Более умный промпт, который четко ограничивает контекст
        system_msg = SystemMessage(content=f"""
            Ты - ассистент лаборатории VetUnion. 
            
            ВАЖНО: Ты можешь отвечать ТОЛЬКО про текущий тест:
            Код: {test_data['test_code']}
            Название: {test_data['test_name']}
            Контейнер: {test_data['container_type']}
            Преаналитика: {test_data['preanalytics']}
            Температура: {test_data['storage_temp']}
            Отдел: {test_data['department']}
            
            Если пользователь спрашивает про ДРУГОЙ тест, скажи:
            "Для получения информации о другом тесте, пожалуйста, введите его код или название."
            
            Отвечай кратко и по существу на русском языке, используя ТОЛЬКО информацию о текущем тесте.
        """)
        
        response = await llm.agenerate([[system_msg, HumanMessage(content=text)]])
        answer = response.generations[0][0].text.strip()
        
        # Проверяем, не предлагает ли LLM искать другой тест
        if "введите его код или название" in answer.lower():
            await loading_msg.edit_text(
                "Похоже, вы спрашиваете о другом тесте. "
                "Введите код или название интересующего теста:"
            )
            await state.set_state(QuestionStates.waiting_for_search_type)
            
            # Показываем персонализированные подсказки
            await show_personalized_suggestions(message, state)
        else:
            await loading_msg.edit_text(answer)
            await message.answer("Выберите действие:", reply_markup=get_dialog_kb())
        
        await db.add_request_stat(
            user_id=user_id,
            request_type='question',
            request_text=text
        )
        
    except Exception:
        await loading_msg.edit_text("Ошибка обработки вопроса.")
        await message.answer("Произошла ошибка. Попробуйте снова или начните новый вопрос.", reply_markup=get_dialog_kb())
    finally:
        animation_task.cancel()
        await gif_msg.delete()

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
       