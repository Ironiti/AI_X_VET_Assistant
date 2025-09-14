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
        r"^\d{1,4}$",  # Только цифры (до 4 знаков)
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


def transliterate_abbreviation(abbr: str) -> str:
    if not abbr or not abbr.isalpha():
        return abbr
    
    letter_map = {
        'A': 'А', 'B': 'Б', 'C': 'К', 'D': 'Д', 'E': 'Е', 
        'F': 'Ф', 'G': 'Г', 'H': 'Х', 'I': 'И', 'J': 'ДЖ',
        'K': 'К', 'L': 'Л', 'M': 'М', 'N': 'Н', 'O': 'О',
        'P': 'П', 'Q': 'К', 'R': 'Р', 'S': 'С', 'T': 'Т',
        'U': 'У', 'V': 'В', 'W': 'В', 'X': 'КС', 'Y': 'И', 
        'Z': 'З'
    }
    
    # Транслитерируем каждую букву
    result = []
    for letter in abbr.upper():
        if letter in letter_map:
            result.append(letter_map[letter])
        else:
            result.append(letter)
    
    return ''.join(result)

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
