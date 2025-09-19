from aiogram import Router, F
from aiogram.types import Message
import base64
import html
import re
import pandas as pd
import re
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import unicodedata
import string


BOT_USERNAME = "AL_VET_UNION_BOT"

gif_router = Router()


@gif_router.message(F.animation)
async def get_gif_id(message: Message):
    await message.answer(f"GIF ID: {message.animation.file_id}")


def fix_bold(text: str) -> str:
    """Заменяет markdown жирный текст на HTML."""

    # Заменяем **текст** на <b>текст</b>
    text = re.sub(r"\*\*([^\*]+)\*\*", r"<b>\1</b>", text)
    return text


def safe_html(text: str) -> str:
    """Экранирует HTML символы в тексте"""
    return html.escape(text)


def normalize_test_code(text: str) -> str:
    """Нормализует введенный код теста."""
    # Добавляем проверку на None и пустую строку
    if not text:
        return ""

    text = text.strip().upper().replace(" ", "")

    # Заменяем кириллицу на латиницу в префиксе AN/АН
    text = text.replace("АН", "AN").replace("АN", "AN").replace("AН", "AN")

    # Если только цифры - добавляем AN
    if text.isdigit():
        text = f"AN{text}"
    # Если начинается с цифр - добавляем AN в начало
    elif re.match(r"^\d", text):
        text = f"AN{text}"

    return text


def encode_test_code_for_url(test_code: str) -> str:
    """Надежно кодирует код теста для использования в URL."""
    if not test_code:
        return ""

    try:
        # Кодируем в bytes, затем в URL-safe base64
        encoded_bytes = test_code.encode("utf-8")
        encoded_b64 = base64.urlsafe_b64encode(encoded_bytes).decode("ascii")
        # Убираем padding '=' для более чистых URL
        encoded_b64 = encoded_b64.rstrip("=")
        return encoded_b64
    except Exception as e:
        print(f"[ERROR] Failed to encode test code '{test_code}': {e}")
        # Fallback: используем только ASCII символы
        safe_code = "".join(c if c.isascii() else "_" for c in test_code)
        return base64.urlsafe_b64encode(safe_code.encode()).decode().rstrip("=")


def decode_test_code_from_url(encoded_code: str) -> str:
    """Надежно декодирует код теста из URL."""
    if not encoded_code:
        return ""

    try:
        # Восстанавливаем padding если нужно
        padding_needed = 4 - (len(encoded_code) % 4)
        if padding_needed and padding_needed != 4:
            encoded_code += "=" * padding_needed

        # Декодируем
        decoded_bytes = base64.urlsafe_b64decode(encoded_code)
        decoded_str = decoded_bytes.decode("utf-8")

        print(f"[DEBUG] Successfully decoded: {encoded_code} -> {decoded_str}")
        return decoded_str

    except Exception as e:
        print(f"[ERROR] Failed to decode '{encoded_code}': {e}")
        # Fallback: возвращаем как есть для попытки поиска
        return encoded_code


def create_test_link(test_code: str) -> str:
    """Создает deep link для теста."""
    if not test_code:
        return f"https://t.me/{BOT_USERNAME}"

    encoded_code = encode_test_code_for_url(test_code)
    link = f"https://t.me/{BOT_USERNAME}?start=test_{encoded_code}"

    return link


def split_long_message(text: str, max_length: int = 4000) -> list[str]:
    """Разбивает длинное сообщение на части"""
    if len(text) <= max_length:
        return [text]

    parts = []
    current_part = ""

    # Разбиваем по строкам
    lines = text.split("\n")

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
            current_part += "\n" + line if current_part else line

    if current_part:
        parts.append(current_part.strip())

    return parts


async def safe_delete_message(message):
    """Безопасное удаление сообщения"""
    try:
        if message:
            await message.delete()
    except Exception:
        pass  # Игнорируем ошибки удаления


def is_test_code_pattern(text: str) -> bool:
    """Проверяет, соответствует ли текст паттерну кода теста."""
    text = text.strip().upper().replace(" ", "")

    patterns = [
        r"^[AА][NН]\d+",  # AN или АН + цифры
        r"^[AА][NН]\d+[A-ZА-Я\-]+",  # AN + цифры + суффикс
        # Строже: только чисто числовые коды длиной 2-4, не 1 символ
        r"^\d{2,4}$",
        r"^\d+[A-ZА-Я\-]+$",  # Цифры + буквенный суффикс
    ]

    for pattern in patterns:
        if re.match(pattern, text):
            return True

    return False

def normalize_text(text: str) -> str:
    if not text or pd.isna(text):
        return ""
    
    text = str(text).strip()
    
    if not text:
        return ""
    
    text = unicodedata.normalize('NFKD', text)
    text = text.replace('ё', 'е').replace('Ё', 'е')
    
    text = text.lower()
    
    text = re.sub(r'[^\w\s,-]', ' ', text)
    
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'(\s*,\s*)', ', ', text)  # запятые
    text = text.strip()
    
    return text


def transliterate_abbreviation(abbr: str) -> Optional[str]:

    # Словарь транслитерации
    translit_dict = {
        'A': 'А', 'B': 'В', 'C': 'С', 'D': 'Д', 'E': 'Е', 
        'F': 'Ф', 'G': 'Г', 'H': 'Х', 'I': 'И', 'J': 'ДЖ',
        'K': 'К', 'L': 'Л', 'M': 'М', 'N': 'Н', 'O': 'О',
        'P': 'П', 'Q': 'К', 'R': 'Р', 'S': 'С', 'T': 'Т',
        'U': 'У', 'V': 'В', 'W': 'В', 'X': 'КС', 'Y': 'И',
        'Z': 'З'
    }
    
    # Список распространенных русских слов, которые могут получиться
    common_russian_words = {
        'от', 'до', 'по', 'на', 'за', 'из', 'с', 'у', 'в', 'к',
        'но', 'да', 'нет', 'ага', 'ой', 'ах', 'эх', 'ну', 'вот',
        'это', 'то', 'так', 'как', 'там', 'тут', 'здесь', 'где',
        'кто', 'что', 'почему', 'когда', 'куда', 'откуда', 'зачем',
        'и', 'а', 'или', 'но', 'же', 'бы', 'ли', 'то', 'ни', 'не',
        'даже', 'уже', 'еще', 'все', 'всё', 'всего', 'всегда',
        'очень', 'почти', 'совсем', 'вдруг', 'потом', 'теперь',
        'тогда', 'иногда', 'никогда', 'всегда', 'везде', 'нигде',
        'никуда', 'откуда', 'зачем', 'почему', 'как', 'так',
        'там', 'тут', 'здесь', 'вон', 'туда', 'сюда', 'оттуда',
        'отсюда', 'вперед', 'назад', 'вверх', 'вниз', 'внутрь',
        'наружу', 'вокруг', 'около', 'возле', 'близко', 'далеко',
        'высоко', 'низко', 'глубоко', 'мелко', 'широко', 'узко',
        'долго', 'скоро', 'рано', 'поздно', 'часто', 'редко',
        'много', 'мало', 'немного', 'совсем', 'почти', 'чуть',
        'еле', 'едва', 'чуть-чуть', 'немножко', 'немного'
    }
    
    result = []
    for char in abbr.upper():
        if char in translit_dict:
            result.append(translit_dict[char])
        else:
            result.append(char)
    
    transliterated = ''.join(result)
    
    # Проверяем, не является ли результат распространенным русским словом
    if transliterated.lower() in common_russian_words:
        return None
    
    # Также проверяем слишком короткие результаты (1-2 символа)
    if len(transliterated) <= 2:
        return None
    
    return transliterated


def is_profile_test(test_code: str) -> bool:
    """Проверяет, является ли тест профилем (заканчивается на ОБС)"""
    if not test_code:
        return False
    return test_code.upper().strip().endswith("ОБС")

def check_profile_request(query: str) -> tuple[bool, str]:
    """
    Определяет, запрашивает ли пользователь профили и очищает запрос
    
    Returns:
        (is_profile_request, cleaned_query)
    """
    query_lower = query.lower()
    
    profile_keywords = [
        "профиль",
        "профили", 
        "профил",
    ]
    
    is_profile = any(keyword in query_lower for keyword in profile_keywords)
    
    # Очищаем запрос от ключевых слов профилей
    cleaned_query = query
    if is_profile:
        for keyword in profile_keywords:
            cleaned_query = re.sub(rf'\b{keyword}\w*\b', '', cleaned_query, flags=re.IGNORECASE)
        cleaned_query = ' '.join(cleaned_query.split())  # Убираем лишние пробелы
    
    return is_profile, cleaned_query.strip()


def filter_results_by_type(results: List[Tuple], show_profiles: bool = False) -> List[Tuple]:
    """
    Фильтрует результаты по типу (профили или обычные тесты)
    
    Args:
        results: Список результатов поиска
        show_profiles: True - показать только профили, False - только обычные тесты
    """
    filtered = []
    for item in results:
        doc = item[0] if isinstance(item, tuple) else item
        test_code = doc.metadata.get("test_code", "")
        
        is_profile = is_profile_test(test_code)
        
        if show_profiles == is_profile:
            filtered.append(item)
    
    return filtered


def replace_test_codes_with_links(text: str, all_test_codes: Set[str]) -> Tuple[str, Dict]:
    """
    Заменяет коды тестов в тексте на Telegram-совместимые HTML ссылки.
    
    Args:
        text: Исходный текст
        all_test_codes: Множество всех доступных кодов тестов (в верхнем регистре)
    
    Returns:
        Tuple[str, Dict]: Текст с маркерами и словарь замен
    """
    # Комбинированный паттерн для поиска всех возможных кодов
    combined_pattern = r'\b(?:[AА][NН]\d+[A-ZА-Я\-]*|[A-ZА-Я]+\d+[A-ZА-Я\-]*|\d{2,4}[A-ZА-Я]*)\b'
    
    # Находим все потенциальные коды
    matches = []
    for match in re.finditer(combined_pattern, text, re.IGNORECASE):
        found_code = match.group()
        
        # Проверяем паттерн
        if not is_test_code_pattern(found_code):
            continue
            
        # Нормализуем для сравнения
        normalized_code = normalize_test_code(found_code)
        
        if normalized_code in all_test_codes:
            matches.append({
                'start': match.start(),
                'end': match.end(),
                'original_code': found_code,
                'normalized_code': normalized_code
            })
    
    # Убираем пересекающиеся совпадения
    filtered_matches = []
    matches.sort(key=lambda x: x['start'])
    
    i = 0
    while i < len(matches):
        current = matches[i]
        j = i + 1
        
        while j < len(matches) and matches[j]['start'] < current['end']:
            if len(current['original_code']) < len(matches[j]['original_code']):
                current = matches[j]
            j += 1
        
        filtered_matches.append(current)
        i = j
    
    # Сортируем по убыванию позиции для замены
    filtered_matches.sort(key=lambda x: x['start'], reverse=True)
    
    # Заменяем найденные коды на маркеры
    result = text
    replacements = {}
    
    for i, match in enumerate(filtered_matches):
        marker = f"{{{{TEST_LINK_{i}}}}}"
        
        # Заменяем в тексте
        result = result[:match['start']] + marker + result[match['end']:]
        
        # Создаем Telegram deep link
        link = create_test_link(match['normalized_code'])
        replacements[marker] = f'<a href="{link}">**{html.escape(match["original_code"])}**</a>'
    
    return result, replacements

