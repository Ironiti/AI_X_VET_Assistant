from aiogram.types import Message
from langchain.schema import Document
import pytz
import asyncio
import html
import re
from typing import Dict, List, Tuple
from datetime import datetime
from src.database.db_init import db
from bot.handlers.utils import create_test_link, is_profile_test, format_i_pattern_numbered, format_i_pattern_comma
import os
from aiogram.types import FSInputFile
from typing import List
import logging


logger = logging.getLogger(__name__)


BOT_USERNAME = "AI_VET_Assistant_Bot"
# BOT_USERNAME = "@idontknow12bot"
BLANKS_PATH = "data/documents"

async def send_blank_files_by_names(message, form_names: List[str]) -> Tuple[bool, List[int]]:
    """Отправляет актуальные бланки из админ-панели, кэша или с диска."""
    try:
        sent_files = 0
        message_ids = []
        
        for form_name in form_names:
            name = form_name.strip()
            file_name = f"{name}.pdf"

            # Файл из админ-панели имеет приоритет: именно его видят и в
            # разделе скачивания, и внутри карточки анализа.
            blank_doc = await db.find_blank_document_by_title(name)
            file_data = (
                {"file_id": blank_doc["file_id"]}
                if blank_doc and blank_doc.get("file_id")
                else await db.get_blank_file_id(file_name)
            )
            
            if file_data and file_data.get("file_id"):
                # Используем существующий file_id для быстрой отправки
                try:
                    sent_msg = await message.answer_document(
                        file_data["file_id"],
                        caption=f"📄 {form_name}"
                    )
                    message_ids.append(sent_msg.message_id)
                    sent_files += 1
                    logger.info(f"[BLANKS] Sent blank via file_id: {file_name}")
                except Exception as e:
                    logger.warning(f"[BLANKS] File_id expired, sending file directly: {e}")
                    # Если file_id устарел, отправляем файл напрямую
                    file_data = None
            
            if not file_data or not file_data.get("file_id"):
                # Загружаем новый файл
                file_path = os.path.join(BLANKS_PATH, file_name)
                if os.path.exists(file_path):
                    try:
                        sent_msg = await message.answer_document(
                            FSInputFile(file_path),
                            caption=f"📄 {form_name}"
                        )
                        message_ids.append(sent_msg.message_id)
                        sent_files += 1
                        
                        # Сохраняем file_id для будущего использования
                        if sent_msg.document:
                            await db.save_blank_file_id(file_name, sent_msg.document.file_id)
                            logger.info(f"[BLANKS] Saved new file_id for: {file_name}")
                    except Exception as e:
                        logger.error(f"[BLANKS] Failed to send file {file_path}: {e}")
                        continue
                else:
                    logger.warning(f"[BLANKS] File not found: {file_path}")
                    continue
            
            # Небольшая задержка между отправкой файлов
            await asyncio.sleep(0.3)
        
        return sent_files > 0, message_ids
        
    except Exception as e:
        logger.error(f"[BLANKS] Failed to send blanks: {e}")
        return False, []
        

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


# def format_similar_tests_text(
#     similar_tests: List[Tuple[Document, float]], max_display: int = 5
# ) -> str:
#     """Форматирует текст с информацией о похожих тестах."""
#     if not similar_tests:
#         return ""

#     text = "\n<b>📋 Похожие тесты:</b>\n"
#     for doc, score in similar_tests[:max_display]:
#         test_code = doc.metadata.get("test_code", "")
#         test_name = doc.metadata.get("test_name", "")
#         # Сокращаем название если слишком длинное
#         if len(test_name) > 50:
#             test_name = test_name[:47] + "..."
#         text += f"• <code>{test_code}</code> - {test_name}\n"

#     if len(similar_tests) > max_display:
#         text += f"\n<i>Показаны {max_display} из {len(similar_tests)} найденных</i>"

#     return text


# def format_similar_tests_with_links(
#     similar_tests: List[Tuple[Document, float]], 
#     max_display: int = 5
# ) -> str:
#     """Форматирует список похожих тестов с кликабельными ссылками"""
#     if not similar_tests:
#         return ""
    
#     response = "\n\n🔍 <b>Похожие тесты:</b>\n"
    
#     for i, (doc, score) in enumerate(similar_tests[:max_display], 1):
#         test_code = doc.metadata.get("test_code", "")
#         test_name = html.escape(doc.metadata.get("test_name", ""))[:50]
        
#         # Добавляем метку для профилей
#         type_label = "🔬" if is_profile_test(test_code) else "🧪"
        
#         link = create_test_link(test_code)
#         response += f"{i}. {type_label} <a href='{link}'>{test_code}</a> - {test_name}...\n"
    
#     return response


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

['primary_container_type', 'container_type', 'container_number']

def format_test_data(metadata: Dict) -> Dict:
    """Extract and format test metadata into standardized dictionary."""

    return {
        "type": metadata.get("type"),
        "test_code": metadata.get("test_code"),
        "test_name": metadata.get("test_name"),
        "department": metadata.get("department"),
        "term_of_execution": metadata.get("term_of_execution"),
        "important_information": metadata.get("important_information"),
        "patient_preparation": metadata.get("patient_preparation") + bool(metadata.get("additional_information_name"))*(' (Название файла:' + metadata.get("additional_information_name") + ')'),
        "biomaterial_type": metadata.get("biomaterial_type"),
        
        # Сохраняем ОРИГИНАЛЬНЫЕ данные для поиска фото
        "primary_container_type_raw": metadata.get("primary_container_type"),
        "container_type_raw": metadata.get("container_type"),
        
        # Форматированные данные для отображения
        "primary_container_type": format_i_pattern_numbered(metadata.get("primary_container_type")),
        "container_type": format_i_pattern_numbered(metadata.get("container_type")),
        "container_number": format_i_pattern_comma(metadata.get("container_number")),
        "preanalytics": '\n' + re.sub(
            r'\s*\*I\*\s*', ' ', 
            re.sub(
                r"\s*(\d+\.)\s*", r"\n\t\t\1 ", metadata.get("preanalytics", "")
            )
        ) if metadata.get("preanalytics") else "",
        "storage_temp": metadata.get("storage_temp"),
        "poss_postorder_container": metadata.get("poss_postorder_container"),
        "form_link": metadata.get("form_link"),
        "form_name": metadata.get("form_name"),
        "additional_information_link": metadata.get("additional_information_link"),
        "additional_information_name": metadata.get("additional_information_name").replace('_', ' '),
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
        "term_of_execution": ("⏱️term_of_execution", "Сроки исполнения (БЕЗ учёта логистики)"),
        "patient_preparation": (
            "📝patient_preparation",
            "Важная информация для подготовки животного",
        ),
        "biomaterial_type": ("🔬biomaterial_type", "Исследуемый биоматериал"),
        "primary_container_type": (
            "🩸primary_container_type",
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
        "storage_temp": ("🌡️storage_temp", "Температура"),
        "poss_postorder_container": (
            "⏳poss_postorder_container",
            "Возможность дозаказа с момента взятия биоматериала",
        ),
        "form_name": ("📃form_name", "Основной бланк"),
        "additional_information_name": (
            "📒additional_information_name",
            "Файл дополнительной информации",
        ),
    }

    message_parts = [
        emoji_manager.format_message(
            f"test_name <b>{t_type}: {test_data['test_code']} - {test_data['test_name']}</b>\n\n"
        )
    ]

    for field, (emoji, display_name) in field_templates.items():
       
        if field == "form_link" and (value := test_data.get(field)):
            pass
        #     value = [part.strip() for part in value.split('*I*') if part.strip()]

        #     if len(value) == 1:
        #         # deep_link = f"https://t.me/{BOT_USERNAME}?start=download_{value[0]}"

        #         message_parts.append(
        #             emoji_manager.format_message(
        #                 f"{emoji} <b>{display_name}:</b> <a href='{value[0]}'> {test_data.get('form_name')} </a>\n"
        #             )
        #         )
        #     else:
        #         # deep_link_f = f"https://t.me/{BOT_USERNAME}?start=download_{value[0]}"
        #         # deep_link_s = f"https://t.me/{BOT_USERNAME}?start=download_{value[1]}"
                
        #         names = [part.strip() for part in test_data.get('form_name').split('*I*') if part.strip()]
        #         message_parts.append(
        #             emoji_manager.format_message(
        #                 f'''{emoji} <b>{display_name}:</b> <a href='{value[0]}'> {names[0]} </a> \t <a href='{value[1]}'> {names[1]} </a>\n'''
        #             )
        #         )
        # elif field == "additional_information_link" and (value := test_data.get(field)):
        #     # deep_link = f"https://t.me/{BOT_USERNAME}?start=download_{value}"
        #     message_parts.append(
        #         emoji_manager.format_message(
        #             f"{emoji} <b>{display_name}:</b> <a href='{value}'> {test_data.get('additional_information_name')} </a>\n"
        #         )
        #     )
        else:
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
            "term_of_execution": "5328315072840234225",
            "important_information": "5328315072840234225",
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
            "form_name": "5327966179761881250",
            "additional_information_name": "5328169834226158945",
        }

    def format_message(self, text: str) -> str:
        for key in self.emoji_ids.keys():
            if key in text:
                emoji_html = f'<tg-emoji emoji-id="{self.emoji_ids[key]}"></tg-emoji>'
                text = text.replace(f"{key}", emoji_html)
        return text


# Инициализация
emoji_manager = CustomEmojiManager()
