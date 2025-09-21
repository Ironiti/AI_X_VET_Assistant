from aiogram.types import Message
from langchain.schema import Document
import pytz
import asyncio
import html
import re
from typing import Dict, List, Tuple
from datetime import datetime
from src.database.db_init import db
from bot.handlers.utils import create_test_link, is_profile_test

BOT_USERNAME = "AL_VET_UNION_BOT"

async def get_test_container_photos(test_data: Dict) -> List[Dict]:
    """Получает все фото контейнеров для теста"""
    photos = []
    container_types = []
    
    # ✅ ИСПРАВЛЕНИЕ: Проверяем ОБА поля
    # Сначала проверяем primary_container_type (приоритет)
    primary_container = str(test_data.get("primary_container_type", "")).strip()
    if primary_container and primary_container.lower() not in ["не указан", "нет", "-", "", "none", "null"]:
        # Убираем кавычки и нормализуем
        primary_container = primary_container.replace('"', "").replace("\n", " ")
        primary_container = " ".join(primary_container.split())
        
        # Разбиваем по *I* если есть несколько контейнеров
        if "*I*" in primary_container:
            container_types.extend([ct.strip() for ct in primary_container.split("*I*")])
        else:
            container_types.append(primary_container)
    
    # Затем проверяем обычный container_type
    container_type_raw = str(test_data.get("container_type", "")).strip()
    if container_type_raw and container_type_raw.lower() not in ["не указан", "нет", "-", "", "none", "null"]:
        # Убираем кавычки и нормализуем
        container_type_raw = container_type_raw.replace('"', "").replace("\n", " ")
        container_type_raw = " ".join(container_type_raw.split())
        
        # Разбиваем по *I* если есть несколько контейнеров
        if "*I*" in container_type_raw:
            new_types = [ct.strip() for ct in container_type_raw.split("*I*")]
            # Добавляем только те, которых еще нет
            for ct in new_types:
                if ct not in container_types:
                    container_types.append(ct)
        else:
            if container_type_raw not in container_types:
                container_types.append(container_type_raw)
    
    # Получаем фото для всех найденных типов контейнеров
    for ct in container_types:
        if ct:
            # Нормализуем каждый тип
            ct_normalized = " ".join(word.capitalize() for word in ct.split())
            photo_data = await db.get_container_photo(ct_normalized)
            if photo_data:
                photos.append(
                    {
                        "type": ct_normalized,
                        "file_id": photo_data["file_id"],
                        "description": photo_data.get("description"),
                    }
                )
    
    return photos


def format_similar_tests_text(
    similar_tests: List[Tuple[Document, float]], max_display: int = 5
) -> str:
    """Форматирует текст с информацией о похожих тестах."""
    if not similar_tests:
        return ""

    text = "\n<b>📋 Похожие тесты:</b>\n"
    for doc, score in similar_tests[:max_display]:
        test_code = doc.metadata.get("test_code", "")
        test_name = doc.metadata.get("test_name", "")
        # Сокращаем название если слишком длинное
        if len(test_name) > 50:
            test_name = test_name[:47] + "..."
        text += f"• <code>{test_code}</code> - {test_name}\n"

    if len(similar_tests) > max_display:
        text += f"\n<i>Показаны {max_display} из {len(similar_tests)} найденных</i>"

    return text


def format_similar_tests_with_links(
    similar_tests: List[Tuple[Document, float]], 
    max_display: int = 5
) -> str:
    """Форматирует список похожих тестов с кликабельными ссылками"""
    if not similar_tests:
        return ""
    
    response = "\n\n🔍 <b>Похожие тесты:</b>\n"
    
    for i, (doc, score) in enumerate(similar_tests[:max_display], 1):
        test_code = doc.metadata.get("test_code", "")
        test_name = html.escape(doc.metadata.get("test_name", ""))[:50]
        
        # Добавляем метку для профилей
        type_label = "🔬" if is_profile_test(test_code) else "🧪"
        
        link = create_test_link(test_code)
        response += f"{i}. {type_label} <a href='{link}'>{test_code}</a> - {test_name}...\n"
    
    return response


def get_time_based_farewell(user_name: str = None):
    """Возвращает персонализированное прощание в зависимости от времени суток"""
    tz = pytz.timezone("Europe/Minsk")
    current_hour = datetime.now(tz).hour

    # Проверяем, что имя не пустое и не дефолтное
    name_part = f", {user_name}" if user_name and user_name != "друг" else ""

    if 4 <= current_hour < 12:
        return f"Рад был помочь{name_part}! Хорошего утра ☀️"
    elif 12 <= current_hour < 17:
        return f"Рад был помочь{name_part}! Хорошего дня 🤝"
    elif 17 <= current_hour < 22:
        return f"Рад был помочь{name_part}! Хорошего вечера 🌆"
    else:
        return f"Рад был помочь{name_part}! Доброй ночи 🌙"


def get_user_first_name(user):
    """Универсальная функция получения имени для обращения"""
    if not user:
        return "друг"

    # Обработка sqlite3.Row или dict
    try:
        # Пробуем как словарь (для dict)
        user_type = user.get("user_type") if hasattr(user, "get") else user["user_type"]
    except (KeyError, TypeError):
        return "друг"

    if user_type == "employee":
        # Для сотрудников используем first_name
        try:
            first_name = (
                user.get("first_name") if hasattr(user, "get") else user["first_name"]
            )
            if first_name:
                return first_name
        except (KeyError, TypeError):
            pass

        # Fallback на разбор полного имени для старых записей
        try:
            name = user.get("name") if hasattr(user, "get") else user["name"]
            if name:
                parts = name.strip().split()
                # Предполагаем формат "Фамилия Имя" для сотрудников
                return parts[1] if len(parts) > 1 else parts[0]
        except (KeyError, TypeError):
            pass
    else:
        # Для клиентов используем первое слово из name
        try:
            name = user.get("name") if hasattr(user, "get") else user["name"]
            if name:
                parts = name.strip().split()
                return parts[0]
        except (KeyError, TypeError):
            pass

    return "друг"


def format_test_data(metadata: Dict) -> Dict:
    """Extract and format test metadata into standardized dictionary."""
    return {
        "type": metadata.get("type"),
        "test_code": metadata.get("test_code"),
        "test_name": metadata.get("test_name"),
        "department": metadata.get("department"),
        "important_information": metadata.get("important_information"),
        "patient_preparation": metadata.get("patient_preparation"),
        "biomaterial_type": metadata.get("biomaterial_type"),
        "primary_container_type": metadata.get("primary_container_type"),
        "container_type": metadata.get("container_type"),
        "container_number": metadata.get("container_number"),
        "preanalytics": re.sub(
            r"\s*(\d+\.)\s*", r"\n\t\t\1 ", metadata.get("preanalytics")
        ),
        "storage_temp": metadata.get("storage_temp"),
        "poss_postorder_container": metadata.get("poss_postorder_container"),
        "form_link": metadata.get("form_link"),
        "additional_information_link": metadata.get("additional_information_link"),
    }


def format_test_info_brief(test_data: Dict) -> str:
    """Format brief test information for initial search results."""
    t_type = "Тест" if test_data["type"] == "Тесты" else "Профиль"
    # Экранируем HTML символы в названии теста
    test_name = html.escape(test_data.get("test_name"))
    department = html.escape(test_data.get("department"))

    return emoji_manager.format_message(
        f"test_name <b>{t_type}: {test_data['test_code']} - {test_name}</b>\n\n"
    ) + emoji_manager.format_message(
        f"🧬department <b>Вид исследования:</b> {department}\n"
    )


def format_test_info(test_data: Dict) -> str:
    t_type = "Тест" if test_data.get("type") == "Тесты" else "Профиль"

    field_templates = {
        "department": ("🧬department", "Вид исследования"),
        "important_information": ("❗️important_information", "Важная информация"),
        "patient_preparation": (
            "📝patient_preparation",
            "Важная информация для подготовки животного",
        ),
        "biomaterial_type": ("🧫biomaterial_type", "Исследуемый биоматериал"),
        "primary_container_type": (
            "🧰primary_container_type",
            "Тип первичного контейнера",
        ),
        "container_type": (
            "🧪container_type",
            "Тип контейнера для хранения и транспортировки",
        ),
        "container_number": (
            "🔢container_number",
            "Номер контейнера для хранения и транспортировки",
        ),
        "preanalytics": ("📋preanalytics", "Преаналитика"),
        "storage_temp": ("❄️storage_temp", "Температура"),
        "poss_postorder_container": (
            "⏱️poss_postorder_container",
            "Возможность дозаказа с момента взятия биоматериала",
        ),
        "form_link": ("📃form_link", "Ссылка скачивания бланка"),
        "additional_information_link": (
            "📒additional_information_link",
            "Ссылка для скачивания дополнительной информации",
        ),
    }

    message_parts = [
        emoji_manager.format_message(
            f"test_name <b>{t_type}: {test_data['test_code']} - {test_data['test_name']}</b>\n\n"
        )
    ]

    # Process other fields
    for field, (emoji, display_name) in field_templates.items():
        if value := test_data.get(field):
            escaped_value = html.escape(str(value))
            message_parts.append(
                emoji_manager.format_message(
                    f"{emoji} <b>{display_name}:</b> {escaped_value}\n"
                )
            )

    return "".join(message_parts)


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


class CustomEmojiManager:
    def __init__(self):
        self.emoji_ids = {
            "test_name": "5328315072840234225",
            "department": "5328315072840234225",
            "patient_preparation": "5328176289562004639",
            "biomaterial_type": "5327846616462291750",
            "primary_container_type": "5328063361986887821",
            "container_type": "5325856719459357092",
            "container_number": "5327851985171417222",
            "preanalytics": "5325585891706569447",
            "storage_temp": "5327963091680397149",
            "poss_postorder_container": "5327925321737995698",
            "form_link": "5327966179761881250",
            "additional_information_link": "5328169834226158945",
        }

    def format_message(self, text: str) -> str:
        for key in self.emoji_ids.keys():
            if key in text:
                emoji_html = f'<tg-emoji emoji-id="{self.emoji_ids[key]}"></tg-emoji>'
                text = text.replace(f"{key}", emoji_html)
        return text


# Инициализация
emoji_manager = CustomEmojiManager()
