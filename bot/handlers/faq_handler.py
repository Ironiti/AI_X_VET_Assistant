import pandas as pd
import json
import os
import html
from typing import Dict, List, Any, Optional
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
import asyncio

from src.database.db_init import db

ITEMS_PER_PAGE = 5
EXCEL_FILE_PATH = "data/processed/1_FAQ BOT VET UNION_драфт.xlsx"
JSON_DATA_FILE = "data/faq_data.json"

faq_router = Router()

class FAQHandler:
    def __init__(self, excel_path: str, json_path: str):
        self.excel_path = excel_path
        self.json_path = json_path
        self.faq_data = []
        self.is_loaded = False
    
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
        # Сначала пробуем загрузить из JSON
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                faq_list = data.get("faq", [])
                print(f"✅ Загружено {len(faq_list)} вопросов FAQ из JSON")
                return faq_list
            except Exception as e:
                print(f"❌ Ошибка загрузки JSON FAQ: {e}")
        
        # Если JSON нет, пробуем конвертировать из Excel
        return self.convert_excel_to_json()
    
    def convert_excel_to_json(self) -> List[Dict[str, str]]:
        """Конвертирует данные из Excel в JSON формат"""
        try:
            if not os.path.exists(self.excel_path):
                print(f"❌ Excel файл не найден: {self.excel_path}")
                return []
            
            # Пробуем разные возможные названия листов
            sheet_names = ['FAQ', 'faq', 'Лист1', 'Sheet1']
            df = None
            
            for sheet_name in sheet_names:
                try:
                    df = pd.read_excel(self.excel_path, sheet_name=sheet_name)
                    print(f"✅ Загружен лист: {sheet_name}")
                    break
                except:
                    continue
            
            if df is None:
                print("❌ Не удалось загрузить ни один лист из Excel")
                return []
            
            faq_list = []
            
            # Ищем колонки с вопросами и ответами
            question_col = None
            answer_col = None
            
            for col in df.columns:
                col_lower = str(col).lower()
                if 'question' in col_lower or 'вопрос' in col_lower or 'q' in col_lower:
                    question_col = col
                elif 'answer' in col_lower or 'ответ' in col_lower or 'a' in col_lower:
                    answer_col = col
            
            if question_col is None or answer_col is None:
                # Если не нашли стандартные названия, берем первые две колонки
                if len(df.columns) >= 2:
                    question_col = df.columns[0]
                    answer_col = df.columns[1]
                else:
                    print("❌ Не найдены колонки с вопросами и ответами")
                    return []
            
            for index, row in df.iterrows():
                try:
                    question = str(row[question_col]).strip()
                    answer = str(row[answer_col]).strip()
                    
                    if question and answer and question not in ['Q', 'Question', 'Вопрос'] and answer not in ['A', 'Answer', 'Ответ']:
                        faq_list.append({
                            "id": index + 1,
                            "question": question,
                            "answer": answer,
                            "category": str(row.get('Category', '')).strip() if 'Category' in df.columns else "Общее"
                        })
                except Exception as e:
                    print(f"❌ Ошибка обработки строки {index}: {e}")
                    continue
            
            # Сохраняем в JSON для будущего использования
            data_to_save = {"faq": faq_list}
            os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Конвертировано {len(faq_list)} вопросов FAQ из Excel")
            return faq_list
            
        except Exception as e:
            print(f"❌ Ошибка конвертации Excel: {e}")
            return []

    def create_faq_keyboard(self, page: int, total_pages: int, current_item: int = None) -> InlineKeyboardMarkup:
        """Создает клавиатуру для навигации по FAQ"""
        keyboard = []
        
        # Кнопки навигации (только если есть страницы)
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"faq_prev_{page}"))
            
            if current_item is not None:
                nav_buttons.append(InlineKeyboardButton(f"{current_item + 1}/{len(self.faq_data)}", callback_data="faq_info"))
            else:
                nav_buttons.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="faq_info"))
            
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"faq_next_{page}"))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        # Кнопка возврата
        keyboard.append([InlineKeyboardButton("🔙 Назад к поиску", callback_data="faq_back_to_search")])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def show_faq_page(self, message: Message, page: int):
        """Показывает страницу со списком FAQ"""
        if not self.faq_data:
            await message.answer("❌ База знаний FAQ пуста или не загружена")
            return
        
        start_idx = page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.faq_data))
        total_pages = max(1, (len(self.faq_data) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        
        # Проверяем корректность страницы
        if page < 0 or page >= total_pages:
            page = 0
            start_idx = 0
            end_idx = min(ITEMS_PER_PAGE, len(self.faq_data))
        
        message_text = "📚 *База знаний FAQ*\n\n"
        
        for i in range(start_idx, end_idx):
            item = self.faq_data[i]
            short_question = item['question'][:60] + "..." if len(item['question']) > 60 else item['question']
            message_text += f"{i+1}. {short_question}\n"
        
        message_text += f"\n*Страница {page + 1} из {total_pages}*"
        
        keyboard = self.create_faq_keyboard(page, total_pages)
        
        await message.answer(message_text, parse_mode='Markdown', reply_markup=keyboard)
    
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
        
        message = f"❓ *Вопрос:* {item['question']}\n\n"
        message += f"✅ *Ответ:* {item['answer']}\n\n"
        
        if item.get('category'):
            message += f"📂 *Категория:* {item['category']}\n\n"
        
        message += f"📋 *ID:* {item['id']}"
        
        # Клавиатура для навигации
        keyboard = self.create_faq_keyboard(0, 1, item_index)
        
        await callback.message.edit_text(message, parse_mode='Markdown', reply_markup=keyboard)
    
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

    async def get_search_suggestions(self, query: str, limit: int = 5) -> List[str]:
        """Получает подсказки для поиска"""
        if not self.faq_data or len(query) < 2:
            return []
        
        suggestions = []
        query_lower = query.lower()
        
        for item in self.faq_data:
            if query_lower in item["question"].lower():
                suggestions.append(item["question"])
                if len(suggestions) >= limit:
                    break
        
        return suggestions

# Инициализация обработчика
faq_handler = FAQHandler(EXCEL_FILE_PATH, JSON_DATA_FILE)

@faq_router.message(Command("faq"))
@faq_router.message(F.text == "📚 База знаний FAQ")
async def handle_faq_command(message: Message):
    """Обработчик команды /faq"""
    # Инициализируем если еще не загружено
    if not faq_handler.is_loaded:
        await faq_handler.initialize()
    
    user_id = message.from_user.id
    
    if not faq_handler.faq_data:
        await message.answer("❌ База знаний FAQ пуста или не загружена")
        return
    
    faq_handler.user_sessions[user_id] = {"page": 0}
    await faq_handler.show_faq_page(message, 0)

@faq_router.callback_query(F.data.startswith("faq_"))
async def handle_faq_callbacks(callback: CallbackQuery):
    """Обработчик callback'ов FAQ"""
    data = callback.data
    user_id = callback.from_user.id
    
    if user_id not in faq_handler.user_sessions:
        faq_handler.user_sessions[user_id] = {"page": 0}
    
    if data.startswith("faq_prev_"):
        page = int(data.split("_")[2]) - 1
        await faq_handler.show_faq_page(callback.message, page)
        
    elif data.startswith("faq_next_"):
        page = int(data.split("_")[2]) + 1
        await faq_handler.show_faq_page(callback.message, page)
        
    elif data.startswith("faq_item_"):
        item_index = int(data.split("_")[2])
        await faq_handler.show_faq_item(callback, item_index)
        
    elif data == "faq_back_to_list":
        current_page = faq_handler.user_sessions[user_id].get("page", 0)
        await faq_handler.show_faq_page(callback.message, current_page)
        
    elif data == "faq_back_to_search":
        await callback.message.edit_text(
            "💡 Введите вопрос для поиска в базе знаний:",
            reply_markup=None
        )
    
    await callback.answer()

@faq_router.message(F.text)
async def handle_faq_search(message: Message):
    """Обработчик поиска по FAQ"""
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
    
    # Получаем подсказки
    suggestions = await faq_handler.get_search_suggestions(query)
    if suggestions:
        suggestion_text = "💡 Возможно вы ищете:\n" + "\n".join(f"• {s}" for s in suggestions[:3])
        await message.answer(suggestion_text)
    
    results = await faq_handler.search_faq(query)
    
    if not results:
        await message.answer("❌ По вашему запросу ничего не найдено в базе знаний")
        return
    
    response = f"🔍 *Найдено результатов: {len(results)}*\n\n"
    
    for i, item in enumerate(results[:5], 1):
        short_question = item['question'][:50] + "..." if len(item['question']) > 50 else item['question']
        response += f"{i}. {short_question}\n"
    
    if len(results) > 5:
        response += f"\n... и еще {len(results) - 5} результатов"
    
    # Создаем клавиатуру с результатами
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for i, item in enumerate(results[:5]):
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"📖 {i+1}. {item['question'][:30]}...",
                callback_data=f"faq_item_{i}"
            )
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton("🔙 Вернуться", callback_data="faq_back_to_search")
    ])
    
    await message.answer(response, parse_mode='Markdown', reply_markup=keyboard)