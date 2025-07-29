from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_menu_by_role, get_dialog_kb, get_back_to_menu_kb, get_search_type_kb
from langchain.schema import SystemMessage, HumanMessage, Document
import pytz
import asyncio
import html
import re
from typing import Optional, Dict

from datetime import datetime
from src.database.db_init import db
from src.data_vectorization import DataProcessor
from models.models_init import qwen3_32b_instruct as llm

LOADING_GIF_ID = "CgACAgIAAxkBAAMIaGr_qy1Wxaw2VrBrm3dwOAkYji4AAu54AAKmqHlJAtZWBziZvaA2BA"
# LOADING_GIF_ID = "CgACAgIAAxkBAAIBFGiBcXtGY7OZvr3-L1dZIBRNqSztAALueAACpqh5Scn4VmIRb4UjNgQ"
questions_router = Router()

class QuestionStates(StatesGroup):
    waiting_for_search_type = State()
    waiting_for_code = State()
    waiting_for_name = State()
    in_dialog = State()

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

def generate_test_code_variants(text: str) -> list[str]:
    """Генерирует различные варианты написания кода теста."""
    text = text.upper()
    variants = [text]  # Оригинал

    cyrillic_to_latin = {
        'А': 'A',
        'Б': 'B',
        'В': ['V', 'W', 'B'],
        'Г': 'G',
        'Д': 'D',
        'Е': ['E', 'I'],
        'Ё': ['E', 'I'],
        'Ж': ['J', 'ZH'],
        'З': ['Z', 'S', 'C'],  
        'И': ['I', 'E', 'Y'],
        'Й': ['Y', 'I'],
        'К': ['K', 'C', 'Q'],
        'Л': 'L',
        'М': 'M',
        'Н': ['N', 'H'],
        'О': 'O',
        'П': 'P',
        'Р': ['R', 'P'],
        'С': ['S', 'C'],
        'Т': 'T',
        'У': ['U', 'Y', 'W'],
        'Ф': 'F',
        'Х': ['H', 'X'],
        'Ц': ['C', 'TS'],
        'Ч': 'CH',
        'Ш': 'SH',
        'Щ': 'SCH',
        'Ы': ['Y', 'I'],
        'Э': ['E', 'A'],
        'Ю': ['U', 'YU'],
        'Я': ['YA', 'A']
    }
    
    # Латиница -> кириллица (для обратного преобразования)
    latin_to_cyrillic = {
        'A': ['А', 'Я'],
        'B': ['Б', 'В'],
        'C': ['С', 'К', 'Ц'],
        'D': 'Д',
        'E': ['Е', 'И', 'Э'],
        'F': 'Ф',
        'G': 'Г',
        'H': ['Х', 'Н'],
        'I': ['И', 'Й'],
        'J': 'Ж',
        'K': 'К',
        'L': 'Л',
        'M': 'М',
        'N': 'Н',
        'O': 'О',
        'P': ['П', 'Р'],
        'Q': 'К',
        'R': 'Р',
        'S': ['С', 'З'],
        'T': 'Т',
        'U': ['У', 'Ю'],
        'V': 'В',
        'W': ['В', 'У'],
        'X': 'Х',
        'Y': ['У', 'Й', 'Ы'],
        'Z': 'З'
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

# Остальной код остается без изменений

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
        'test_code': metadata['test_code'],
        'test_name': metadata['test_name'],
        'container_type': metadata['container_type'],
        'preanalytics': metadata['preanalytics'],
        'storage_temp': metadata['storage_temp'],
        'department': metadata['department']
    }

def format_test_info(test_data: Dict) -> str:
    """Format test information from metadata using HTML tags."""
    return (
        f"<b>Тест: {test_data['test_code']} - {test_data['test_name']}</b>\n\n"
        f"<b>Тип контейнера:</b> {test_data['container_type']}\n"
        f"<b>Преаналитика:</b> {test_data['preanalytics']}\n"
        f"<b>Температура:</b> {test_data['storage_temp']}\n"
        f"<b>Вид исследования:</b> {test_data['department']}\n\n"
    )

async def animate_loading(loading_msg: Message):  # Изменить message на loading_msg
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
            await loading_msg.edit_text(animations[i])  # Теперь правильно
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
            
        return [docs[i][0] for i in selected_indices]
    except Exception:
        return [docs[0][0]]  # Fallback on error

@questions_router.message(F.text == "🔬 Задать вопрос ассистенту")
async def start_question(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return

    user_name = get_user_first_name(user)  # Добавить эту функцию
    role = user['role'] if 'role' in user else 'staff'
    
    prompt = f"""Привет, {user_name} 👋
    
🔬 Я могу помочь с поиском информации по:
    - всему перечню лабораторных тестов и профилей
    - преаналитическим требованиям
    - типам пробирок/контейнеров
    - условиям хранения/транспортировки проб"""

    await db.clear_buffer(user_id)
    await message.answer(prompt, reply_markup=get_search_type_kb())
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
async def handle_search_type(message: Message, state: FSMContext):
    """Handle search type selection."""
    text = message.text.strip()
    user_id = message.from_user.id
    
    if text == "🔢 Поиск по коду теста":
        await message.answer("Введите код теста (например, AN5):", reply_markup=get_back_to_menu_kb())
        await state.set_state(QuestionStates.waiting_for_code)
    elif text == "📝 Поиск по названию":
        await message.answer("Введите название или описание теста:", reply_markup=get_back_to_menu_kb())
        await state.set_state(QuestionStates.waiting_for_name)
    # обработка возврата в меню удалена, теперь этим занимается глобальный хендлер

@questions_router.message(QuestionStates.waiting_for_code)
async def handle_code_search(message: Message, state: FSMContext):
    """Handle test code search with smart matching."""
    user_id = message.from_user.id
    original_input = message.text.strip()

    try:
        if LOADING_GIF_ID:
            gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
            loading_msg = await message.answer("Обрабатываю ваш запрос...\n⏳ Анализирую данные...")
            animation_task = asyncio.create_task(animate_loading(loading_msg))
        else:
            gif_msg = None
            loading_msg = await message.answer("🔍 Ищем тест...")
            animation_task = None
        
        processor = DataProcessor()
        processor.load_vector_store()
        
        # Используем умный поиск
        result, found_variant, match_type = await smart_test_search(processor, original_input)
        
        if not result:
            raise ValueError("Test not found")
            
        doc = result[0]
        test_data = format_test_data(doc.metadata)
        
        # Формируем ответ
        response = ""
        if match_type == "phonetic" and found_variant != original_input.upper():
            response = f"<i>По запросу '{original_input.upper()}' найден похожий тест:</i>\n\n"
        
        response += format_test_info(test_data)
        
        # Логирование
        await db.add_request_stat(
            user_id=user_id,
            request_type='question',
            request_text=f"Поиск по коду: {original_input} → {test_data['test_code']} ({match_type})"
        )
        
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        
        await message.answer(response, reply_markup=get_dialog_kb(), parse_mode="HTML")
        await state.set_state(QuestionStates.in_dialog)
        await state.update_data(current_test=test_data)
        
    except ValueError:
        if 'animation_task' in locals() and animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg) 
        await safe_delete_message(gif_msg)
        
        # Дополнительная подсказка
        error_msg = f"❌ Тест с кодом '{original_input.upper()}' не найден.\n"
        error_msg += "Проверьте правильность ввода кода."
        
        await message.answer(error_msg, reply_markup=get_search_type_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)
        
    except Exception as e:
        print(f"[ERROR] Code search failed: {e}")
        if 'animation_task' in locals() and animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        
        await message.answer("⚠️ Ошибка при поиске. Попробуйте позже", reply_markup=get_search_type_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)

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
        
        rag_hits = processor.search_test(expanded_query, top_k=5)
        
        if not rag_hits:
            raise ValueError("Тесты не найдены")
            
        selected_docs = await select_best_match(text, rag_hits)
        
        await db.add_request_stat(
            user_id=user_id,
            request_type='question',
            request_text=f"Поиск по названию: {text}"
        )
        
        # Безопасная очистка
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        
        if len(selected_docs) > 1:
            # Show multiple results
            response = "Найдено несколько подходящих тестов:\n\n"
            
            # Ограничиваем количество результатов, чтобы не превысить лимит
            max_tests = 3
            for i, doc in enumerate(selected_docs[:max_tests]):
                test_data = format_test_data(doc.metadata)
                response += format_test_info(test_data) + "\n"
            
            if len(selected_docs) > max_tests:
                response += f"\n<i>Показаны первые {max_tests} из {len(selected_docs)} найденных тестов.</i>"
            
            # Разбиваем длинное сообщение на части
            message_parts = split_long_message(response)
            
            for i, part in enumerate(message_parts):
                if i == len(message_parts) - 1:
                    # Последняя часть с клавиатурой
                    await message.answer(part, parse_mode="HTML", reply_markup=get_dialog_kb())
                else:
                    await message.answer(part, parse_mode="HTML")
        else:
            # Single result
            test_data = format_test_data(selected_docs[0].metadata)
            response = format_test_info(test_data)
            
            # Проверяем длину и отправляем
            if len(response) > 4000:
                # Если даже один результат слишком длинный, обрезаем преаналитику
                test_data['preanalytics'] = test_data['preanalytics'][:500] + "..."
                response = format_test_info(test_data)
            
            await message.answer(
                response,
                reply_markup=get_dialog_kb(),
                parse_mode="HTML"
            )
        
        # Сохраняем последний найденный тест для диалога
        await state.set_state(QuestionStates.in_dialog)
        if selected_docs:
            last_test_data = format_test_data(selected_docs[-1].metadata)
            await state.update_data(current_test=last_test_data)
            
    except Exception as e:
        print(f"[ERROR] Name search failed: {e}")
        # Безопасная очистка при ошибке
        if animation_task:
            animation_task.cancel()
        await safe_delete_message(loading_msg)
        await safe_delete_message(gif_msg)
        
        error_msg = "❌ Тесты не найдены" if str(e) == "Тесты не найдены" else "⚠️ Ошибка поиска. Попробуйте позже."
        await message.answer(error_msg, reply_markup=get_search_type_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)

@questions_router.message(QuestionStates.in_dialog)
async def handle_dialog(message: Message, state: FSMContext):
    """Handle follow-up questions using LLM."""
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
        await message.answer("Выберите тип поиска:", reply_markup=get_search_type_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)
        return
    
    # обработка возврата в меню удалена, теперь этим занимается глобальный хендлер
    data = await state.get_data()
    test_data = data['current_test'] if 'current_test' in data else None
    
    if not test_data:
        await message.answer("Контекст потерян. Задайте новый вопрос.", reply_markup=get_search_type_kb())
        await state.set_state(QuestionStates.waiting_for_search_type)
        return
        
    gif_msg = await message.answer_animation(LOADING_GIF_ID, caption="")
    loading_msg = await message.answer("Обрабатываю ваш запрос...\n⏳ Анализирую данные...")
    animation_task = asyncio.create_task(animate_loading(loading_msg))
    
    try:
        system_msg = SystemMessage(content=f"""
            You're assisting with questions about lab test:
            Code: {test_data['test_code']}
            Name: {test_data['test_name']}
            Container: {test_data['container_type']}
            Preanalytics: {test_data['preanalytics']}
            
            Answer concisely in Russian using only this information.
        """)
        response = await llm.agenerate([[system_msg, HumanMessage(content=text)]])
        answer = response.generations[0][0].text.strip()
        
        await db.add_request_stat(
            user_id=user_id,
            request_type='question',
            request_text=text
        )
        
        await loading_msg.edit_text(answer)
        await message.answer("Выберите действие:", reply_markup=get_dialog_kb())
        
    except Exception:
        await loading_msg.edit_text("Ошибка обработки вопроса.")
        await message.answer("Произошла ошибка. Попробуйте снова или начните новый вопрос.", reply_markup=get_dialog_kb())
    finally:
        animation_task.cancel()
        await gif_msg.delete()
        