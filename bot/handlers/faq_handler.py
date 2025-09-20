import pandas as pd
import json
import os
import re
from typing import Dict, List, Any
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from src.database.db_init import db
from bot.keyboards import get_back_to_menu_kb, get_menu_by_role, get_faq_search_kb, get_faq_back_kb

ITEMS_PER_PAGE = 10
EXCEL_FILE_PATH = "data/processed/1_FAQ BOT VET UNION_драфт.xlsx"
JSON_DATA_FILE = "data/faq_data.json"

faq_router = Router()

class FAQHandler:
    def __init__(self, excel_path: str, json_path: str):
        self.excel_path = excel_path
        self.json_path = json_path
        self.faq_data = []
        self.is_loaded = False
        self.user_sessions = {}
    
    async def initialize(self):
        """Инициализирует данные FAQ"""
        try:
            self.faq_data = self.load_or_convert_data()
            self.is_loaded = True
            print(f"✅ FAQ данные загружены: {len(self.faq_data)} вопросов")
        except Exception as e:
            print(f"❌ Ошибка загрузки FAQ: {e}")
            self.faq_data = []
            self.is_loaded = False
    
    def load_or_convert_data(self) -> List[Dict[str, str]]:
        """Загружает данные из JSON или конвертирует из Excel"""
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                faq_list = data.get("faq", [])
                print(f"✅ Загружено {len(faq_list)} вопросов FAQ из JSON")
                return faq_list
            except Exception as e:
                print(f"❌ Ошибка загрузки JSON FAQ: {e}")
        
        return self.convert_excel_to_json()
    
    def convert_excel_to_json(self) -> List[Dict[str, str]]:
        """Конвертирует данные из Excel в JSON формат"""
        try:
            if not os.path.exists(self.excel_path):
                print(f"❌ Excel файл не найден: {self.excel_path}")
                return []
            
            # Читаем Excel файл
            df = pd.read_excel(self.excel_path, sheet_name='FAQ')
            
            faq_list = []
            
            # Обрабатываем данные
            for index, row in df.iterrows():
                try:
                    question = str(row['Q']).strip()
                    answer = str(row['A']).strip()
                    
                    if (question and answer and 
                        question not in ['Q', 'Question', 'Вопрос'] and 
                        answer not in ['A', 'Answer', 'Ответ']):
                        
                        # Извлекаем категорию из ответа
                        category_match = re.search(r'Область применения: (.+?)(?:\n|$)', answer)
                        category = category_match.group(1) if category_match else "Общее"
                        
                        # Очищаем ответ от категории для чистоты
                        clean_answer = re.sub(r'Область применения: .+?$', '', answer).strip()
                        
                        faq_list.append({
                            "id": index + 1,
                            "question": question,
                            "answer": clean_answer,
                            "category": category
                        })
                except Exception as e:
                    print(f"❌ Ошибка обработки строки {index}: {e}")
                    continue
            
            # Сохраняем в JSON
            data_to_save = {"faq": faq_list}
            os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Конвертировано {len(faq_list)} вопросов FAQ из Excel")
            return faq_list
            
        except Exception as e:
            print(f"❌ Ошибка конвертации Excel: {e}")
            return []

    def create_faq_list_keyboard(self, page: int, total_pages: int) -> InlineKeyboardMarkup:
        """Создает клавиатуру для навигации по списку FAQ"""
        keyboard = []
        
        # Добавляем кнопки вопросов для текущей страницы
        start_idx = page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.faq_data))
        
        for i in range(start_idx, end_idx):
            item = self.faq_data[i]
            short_question = item['question'][:50] + "..." if len(item['question']) > 50 else item['question']
            keyboard.append([InlineKeyboardButton(
                text=f"❓ {i+1}. {short_question}",
                callback_data=f"faq_item_{i}"
            )])
        
        # Кнопки навигации
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(
                text="⬅️ Назад", 
                callback_data=f"faq_list_{page-1}"
            ))
        
        nav_buttons.append(InlineKeyboardButton(
            text=f"📄 {page + 1}/{total_pages}", 
            callback_data="faq_info"
        ))
        
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(
                text="Вперед ➡️", 
                callback_data=f"faq_list_{page+1}"
            ))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Кнопки возврата - ИСПРАВЛЕНО: используем faq_main_menu
        keyboard.append([InlineKeyboardButton(
            text="🔍 Новый поиск", 
            callback_data="faq_search_start"
        )])
        keyboard.append([InlineKeyboardButton(
            text="🏠 В главное меню", 
            callback_data="faq_main_menu"
        )])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    def create_faq_item_keyboard(self, current_index: int, total_items: int) -> InlineKeyboardMarkup:
        """Создает клавиатуру для навигации по конкретному вопросу"""
        keyboard = []
        
        # Кнопки навигации между вопросами
        nav_buttons = []
        if current_index > 0:
            nav_buttons.append(InlineKeyboardButton(
                text="⬅️ Предыдущий", 
                callback_data=f"faq_item_{current_index - 1}"
            ))
        
        nav_buttons.append(InlineKeyboardButton(
            text=f"📖 {current_index + 1}/{total_items}", 
            callback_data="faq_info"
        ))
        
        if current_index < total_items - 1:
            nav_buttons.append(InlineKeyboardButton(
                text="Следующий ➡️", 
                callback_data=f"faq_item_{current_index + 1}"
            ))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Кнопка возврата к списку и главному меню - ИСПРАВЛЕНО
        keyboard.append([InlineKeyboardButton(
            text="🔙 К списку вопросов", 
            callback_data="faq_back_to_list"
        )])
        keyboard.append([InlineKeyboardButton(
            text="🔍 Новый поиск", 
            callback_data="faq_search_start"
        )])
        keyboard.append([InlineKeyboardButton(
            text="🏠 В главное меню", 
            callback_data="faq_main_menu"
        )])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def show_faq_page(self, message: Message, page: int, edit_message: Message = None):
        """Показывает страницу со списком FAQ"""
        if not self.faq_data:
            await message.answer("❌ База знаний FAQ пуста или не загружена")
            return
        
        total_pages = max(1, (len(self.faq_data) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        
        # Проверяем корректность страницы
        if page < 0 or page >= total_pages:
            page = 0
        
        start_idx = page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.faq_data))
        
        message_text = "📚 *База знаний FAQ*\n\n"
        message_text += f"*Всего вопросов:* {len(self.faq_data)}\n"
        message_text += f"*Страница {page + 1} из {total_pages}*\n\n"
        message_text += "*Выберите вопрос для просмотра ответа:*"
        
        keyboard = self.create_faq_list_keyboard(page, total_pages)
        
        # Сохраняем состояние пользователя
        user_id = message.from_user.id
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {}
        self.user_sessions[user_id]["page"] = page
        self.user_sessions[user_id]["mode"] = "list"
        
        # Если передано сообщение для редактирования - редактируем его
        if edit_message:
            try:
                await edit_message.edit_text(message_text, parse_mode='Markdown', reply_markup=keyboard)
                return
            except Exception as e:
                print(f"Ошибка редактирования сообщения: {e}")
                # Если не удалось отредактировать, отправляем новое
        
        # Иначе отправляем новое сообщение
        sent_message = await message.answer(message_text, parse_mode='Markdown', reply_markup=keyboard)
        self.user_sessions[user_id]["last_message_id"] = sent_message.message_id

    async def show_faq_item(self, callback: CallbackQuery, item_index: int):
        """Показывает конкретный вопрос-ответ"""
        if not self.faq_data or item_index >= len(self.faq_data):
            await callback.answer("❌ Вопрос не найден")
            return
        
        item = self.faq_data[item_index]
        
        # Сохраняем в историю просмотров (если метод существует)
        user_id = callback.from_user.id
        try:
            # Пробуем вызвать метод, если он существует
            if hasattr(db, 'add_faq_history'):
                await db.add_faq_history(
                    user_id=user_id,
                    faq_id=item['id'],
                    question=item['question']
                )
        except Exception as e:
            print(f"⚠️ Не удалось сохранить историю просмотров: {e}")
            # Продолжаем выполнение без сохранения истории
        
        message = f"📚 *Вопрос #{item_index + 1}*\n\n"
        message += f"❓ *Вопрос:* {item['question']}\n\n"
        message += f"✅ *Ответ:* {item['answer']}\n\n"
        
        if item.get('category'):
            message += f"🏷️ *Категория:* {item['category']}\n\n"
        
        message += f"🔢 *ID:* {item['id']}"
        
        # Клавиатура для навигации
        keyboard = self.create_faq_item_keyboard(item_index, len(self.faq_data))
        
        # Сохраняем ID текущего сообщения перед редактированием
        user_id = callback.from_user.id
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {}
        self.user_sessions[user_id]["last_item_message_id"] = callback.message.message_id
        
        # Редактируем существующее сообщение
        try:
            await callback.message.edit_text(message, parse_mode='Markdown', reply_markup=keyboard)
        except Exception as e:
            print(f"Ошибка редактирования сообщения: {e}")
            # Если не удалось отредактировать, отправляем новое
            sent_message = await callback.message.answer(message, parse_mode='Markdown', reply_markup=keyboard)
            self.user_sessions[user_id]["last_item_message_id"] = sent_message.message_id
        
        await callback.answer()    
    
    async def show_faq_item(self, callback: CallbackQuery, item_index: int):
        """Показывает конкретный вопрос-ответ"""
        if not self.faq_data or item_index >= len(self.faq_data):
            await callback.answer("❌ Вопрос не найден")
            return
        
        item = self.faq_data[item_index]
        
        # Сохраняем в историю просмотров
        user_id = callback.from_user.id
        await db.add_faq_history(
            user_id=user_id,
            faq_id=item['id'],
            question=item['question']
        )
        
        message = f"📚 *Вопрос #{item_index + 1}*\n\n"
        message += f"❓ *Вопрос:* {item['question']}\n\n"
        message += f"✅ *Ответ:* {item['answer']}\n\n"
        
        if item.get('category'):
            message += f"🏷️ *Категория:* {item['category']}\n\n"
        
        message += f"🔢 *ID:* {item['id']}"
        
        # Клавиатура для навигации
        keyboard = self.create_faq_item_keyboard(item_index, len(self.faq_data))
        
        # Редактируем существующее сообщение
        try:
            await callback.message.edit_text(message, parse_mode='Markdown', reply_markup=keyboard)
        except Exception as e:
            print(f"Ошибка редактирования сообщения: {e}")
            # Если не удалось отредактировать, отправляем новое
            await callback.message.answer(message, parse_mode='Markdown', reply_markup=keyboard)
        
        await callback.answer()
    
    async def search_faq(self, query: str) -> List[Dict]:
        """Поиск по FAQ"""
        if not self.faq_data:
            return []
        
        query_lower = query.lower()
        results = []
        
        for item in self.faq_data:
            if (query_lower in item["question"].lower() or 
                query_lower in item["answer"].lower() or 
                query_lower in item.get("category", "").lower()):
                results.append(item)
        
        return results

    def create_search_results_keyboard(self, results: List[Dict], start_index: int = 0) -> InlineKeyboardMarkup:
        """Создает клавиатуру для результатов поиска"""
        keyboard = []
        
        # Показываем до 5 результатов
        end_index = min(start_index + 5, len(results))
        
        for i in range(start_index, end_index):
            item = results[i]
            short_question = item['question'][:35] + "..." if len(item['question']) > 35 else item['question']
            keyboard.append([InlineKeyboardButton(
                text=f"🔍 {i+1}. {short_question}",
                callback_data=f"faq_search_{i}"
            )])
        
        # Кнопки навигации
        nav_buttons = []
        
        # Кнопка "Назад"
        if start_index > 0:
            nav_buttons.append(InlineKeyboardButton(
                text="⬅️ Назад", 
                callback_data=f"faq_search_nav_{max(0, start_index - 5)}"
            ))
        
        # Информация о странице
        total_pages = max(1, (len(results) + 4) // 5)
        current_page = (start_index // 5) + 1
        nav_buttons.append(InlineKeyboardButton(
            text=f"📄 {current_page}/{total_pages}", 
            callback_data="faq_info"
        ))
        
        # Кнопка "Вперед"
        if end_index < len(results):
            nav_buttons.append(InlineKeyboardButton(
                text="Вперед ➡️", 
                callback_data=f"faq_search_nav_{end_index}"
            ))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Кнопки действий - ИСПРАВЛЕНО
        keyboard.append([InlineKeyboardButton(
            text="🔍 Новый поиск", 
            callback_data="faq_search_start"
        )])
        keyboard.append([InlineKeyboardButton(
            text="🏠 В главное меню", 
            callback_data="faq_main_menu"
        )])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    async def show_search_results(self, message: Message, results: List[Dict], start_index: int = 0):
        """Показывает результаты поиска"""
        if not results:
            await message.answer("❌ По вашему запросу ничего не найдено")
            return
        
        response = f"🔍 *Найдено результатов: {len(results)}*\n\n"
        
        end_index = min(start_index + 5, len(results))
        for i in range(start_index, end_index):
            item = results[i]
            short_question = item['question'][:50] + "..." if len(item['question']) > 50 else item['question']
            response += f"{i+1}. {short_question}\n"
        
        if len(results) > 5:
            total_pages = (len(results) + 4) // 5
            current_page = (start_index // 5) + 1
            response += f"\nСтраница {current_page}/{total_pages}"
        
        keyboard = self.create_search_results_keyboard(results, start_index)
        
        # Сохраняем результаты поиска в сессии
        user_id = message.from_user.id
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {}
        self.user_sessions[user_id]["search_results"] = results
        self.user_sessions[user_id]["search_start_index"] = start_index
        
        await message.answer(response, parse_mode='Markdown', reply_markup=keyboard)


# Инициализация обработчика
faq_handler = FAQHandler(EXCEL_FILE_PATH, JSON_DATA_FILE)

@faq_router.message(F.text == "🔍 Новый поиск")
async def handle_new_search_text(message: Message, state: FSMContext):
    """Обработчик текстовой кнопки нового поиска"""
    user_id = message.from_user.id
    faq_handler.user_sessions[user_id] = {"mode": "search"}
    
    await message.answer(
        "💡 Введите вопрос для поиска в базе знаний:",
        reply_markup=get_faq_back_kb()
    )

@faq_router.message(F.text == "🔙 Вернуться в главное меню")
async def handle_back_to_menu_legacy(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    role = user["role"] if "role" in user.keys() else "staff"
    await message.answer("Операция отменена.", reply_markup=get_menu_by_role(role))
    return

@faq_router.message(F.text == "📚 База знаний FAQ")
async def handle_faq_button(message: Message, state: FSMContext):
    """Обработчик кнопки FAQ из главного меню"""
    # Инициализируем если еще не загружено
    if not faq_handler.is_loaded:
        await faq_handler.initialize()
    
    user_id = message.from_user.id
    
    if not faq_handler.faq_data:
        await message.answer("❌ База знаний FAQ пуста или не загружена")
        return
    
    # Сохраняем состояние пользователя
    faq_handler.user_sessions[user_id] = {"page": 0, "mode": "menu"}
    
    # Показываем меню FAQ
    await message.answer(
        "📚 *База знаний FAQ*\n\nВыберите действие:",
        parse_mode='Markdown',
        reply_markup=get_faq_search_kb()
    )

@faq_router.message(F.text == "🔍 Поиск по базе знаний")
async def handle_faq_search_start(message: Message, state: FSMContext):
    """Обработчик начала поиска в FAQ"""
    user_id = message.from_user.id
    faq_handler.user_sessions[user_id] = {"mode": "search"}
    
    await message.answer(
        "💡 Введите вопрос для поиска в базе знаний:",
        reply_markup=get_faq_back_kb()
    )

@faq_router.message(F.text == "📋 Показать все вопросы")
async def handle_faq_show_all(message: Message, state: FSMContext):
    """Обработчик показа всех вопросов FAQ"""
    user_id = message.from_user.id
    
    if not faq_handler.is_loaded:
        await faq_handler.initialize()
    
    if not faq_handler.faq_data:
        await message.answer("❌ База знаний FAQ пуста или не загружена")
        return
    
    # Сохраняем состояние пользователя
    faq_handler.user_sessions[user_id] = {"page": 0, "mode": "list"}
    await faq_handler.show_faq_page(message, 0)

@faq_router.message(F.text == "🔙 Назад к FAQ")
async def handle_faq_back(message: Message, state: FSMContext):
    """Обработчик возврата к меню FAQ"""
    user_id = message.from_user.id
    faq_handler.user_sessions[user_id] = {"mode": "menu"}
    
    await message.answer(
        "📚 *База знаний FAQ*\n\nВыберите действие:",
        parse_mode='Markdown',
        reply_markup=get_faq_search_kb()
    )

@faq_router.callback_query(F.data.startswith("faq_"))
async def handle_faq_callbacks(callback: CallbackQuery, state: FSMContext):
    """Обработчик callback'ов FAQ"""
    data = callback.data
    user_id = callback.from_user.id
    
    if user_id not in faq_handler.user_sessions:
        faq_handler.user_sessions[user_id] = {"page": 0, "mode": "list"}
    
    try:
        # Разбираем callback data
        parts = data.split('_')
        
        # 1. Навигация по основному списку FAQ
        if len(parts) >= 3 and parts[1] == "list" and parts[2].isdigit():
            page = int(parts[2])
            faq_handler.user_sessions[user_id]["page"] = page
            faq_handler.user_sessions[user_id]["mode"] = "list"
            await faq_handler.show_faq_page(callback.message, page, callback.message)
        
        # 2. Просмотр конкретного вопроса из основного списка
        elif len(parts) >= 3 and parts[1] == "item" and parts[2].isdigit():
            item_index = int(parts[2])
            faq_handler.user_sessions[user_id]["mode"] = "item"
            await faq_handler.show_faq_item(callback, item_index)
        
        # 3. Просмотр результата поиска
        elif len(parts) >= 3 and parts[1] == "search" and parts[2].isdigit():
            item_index = int(parts[2])
            faq_handler.user_sessions[user_id]["mode"] = "item"
            
            if "search_results" in faq_handler.user_sessions[user_id]:
                results = faq_handler.user_sessions[user_id]["search_results"]
                if item_index < len(results):
                    # Находим соответствующий вопрос в основном массиве
                    search_item = results[item_index]
                    main_index = next((i for i, item in enumerate(faq_handler.faq_data) 
                                    if item['id'] == search_item['id']), -1)
                    if main_index != -1:
                        await faq_handler.show_faq_item(callback, main_index)
        
        # 4. Навигация по страницам поиска
        elif len(parts) >= 4 and parts[1] == "search" and parts[2] == "nav" and parts[3].isdigit():
            start_index = int(parts[3])
            if "search_results" in faq_handler.user_sessions[user_id]:
                results = faq_handler.user_sessions[user_id]["search_results"]
                
                response = f"🔍 *Найдено результатов: {len(results)}*\n\n"
                end_index = min(start_index + 5, len(results))
                
                for i in range(start_index, end_index):
                    item = results[i]
                    short_question = item['question'][:50] + "..." if len(item['question']) > 50 else item['question']
                    response += f"{i+1}. {short_question}\n"
                
                if len(results) > 5:
                    total_pages = (len(results) + 4) // 5
                    current_page = (start_index // 5) + 1
                    response += f"\nСтраница {current_page}/{total_pages}"
                
                keyboard = faq_handler.create_search_results_keyboard(results, start_index)
                
                try:
                    await callback.message.edit_text(response, parse_mode='Markdown', reply_markup=keyboard)
                except Exception as e:
                    print(f"Ошибка редактирования: {e}")
                    await callback.answer("Ошибка обновления")
        
        # 5. Начать новый поиск
        elif data == "faq_search_start":
            faq_handler.user_sessions[user_id]["mode"] = "search"
            try:
                await callback.message.edit_text(
                    "💡 Введите вопрос для поиска в базе знаний:",
                    reply_markup=get_faq_back_kb()
                )
            except:
                await callback.message.answer(
                    "💡 Введите вопрос для поиска в базе знаний:",
                    reply_markup=get_faq_back_kb()
                )
        
        # 6. Вернуться к списку вопросов
        elif data == "faq_back_to_list":
            current_page = faq_handler.user_sessions[user_id].get("page", 0)
            faq_handler.user_sessions[user_id]["mode"] = "list"
            
            # Пытаемся удалить сообщение с вопросом
            try:
                if "last_item_message_id" in faq_handler.user_sessions[user_id]:
                    await callback.bot.delete_message(
                        chat_id=callback.message.chat.id,
                        message_id=faq_handler.user_sessions[user_id]["last_item_message_id"]
                    )
            except Exception as e:
                print(f"Не удалось удалить сообщение: {e}")
            
            await faq_handler.show_faq_page(callback.message, current_page, callback.message)
        
        # 7. Вернуться в главное меню - ИСПРАВЛЕНО
        elif data == "faq_main_menu":
            user = await db.get_user(user_id)
            role = user["role"] if user and "role" in user else "user"
            await callback.message.answer(
                "Возвращаемся в главное меню:",
                reply_markup=get_menu_by_role(role)
            )
        
        # 8. Информация (пустая кнопка)
        elif data == "faq_info":
            await callback.answer("Информация о навигации")
        
        else:
            await callback.answer("Неизвестная команда")
            
    except Exception as e:
        print(f"❌ Ошибка обработки callback: {e}")
        await callback.answer("Произошла ошибка")   

@faq_router.message(F.text)
async def handle_faq_search(message: Message, state: FSMContext):
    """Обработчик поиска по FAQ"""
    # Пропускаем команды и системные сообщения
    if (message.text.startswith('/') or 
        message.text in ["📚 База знаний FAQ", "🔬 Задать вопрос ассистенту",
                        "🔍 Поиск по базе знаний", "📋 Показать все вопросы",
                        "🔙 Назад к FAQ", "🏠 В главное меню", "🔍 Новый поиск"] or
        message.text.startswith("❌")):
        return
    
    # Проверяем, находится ли пользователь в режиме поиска FAQ
    user_id = message.from_user.id
    if (user_id not in faq_handler.user_sessions or 
        faq_handler.user_sessions[user_id].get("mode") != "search"):
        return
    
    # Инициализируем если еще не загружено
    if not faq_handler.is_loaded:
        await faq_handler.initialize()
    
    if not faq_handler.faq_data:
        await message.answer("❌ База знаний FAQ пуста или не загружена")
        return
    
    query = message.text.strip()
    
    if len(query) < 2:
        await message.answer("🔍 Введите минимум 2 символа для поиска")
        return
    
    results = await faq_handler.search_faq(query)
    
    # Сохраняем результаты в сессию
    faq_handler.user_sessions[user_id]["search_results"] = results
    
    if not results:
        await message.answer("❌ По вашему запросу ничего не найдено в базе знаний")
        return
    
    await faq_handler.show_search_results(message, results)