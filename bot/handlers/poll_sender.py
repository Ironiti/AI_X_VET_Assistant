from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import json
from src.database.db_init import db

poll_callback_router = Router()

class PollAnsweringStates(StatesGroup):
    answering_text = State()
    answering_multiple = State()

def create_poll_keyboard(poll_id, question_index):
    """Создает клавиатуру для начала опроса"""
    keyboard = [
        [InlineKeyboardButton(
            text="🚀 Начать опрос",
            callback_data=f"start_poll:{poll_id}:{question_index}"
        )]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def create_question_keyboard(poll_id, question_id, question_type, options, question_index):
    """Создает клавиатуру для вопроса"""
    keyboard = []
    
    if question_type == 'single' and options:
        # Один вариант ответа с красивыми кружками
        for i, option in enumerate(options):
            keyboard.append([InlineKeyboardButton(
                text=f"⚪ {option}",
                callback_data=f"answer_single:{poll_id}:{question_id}:{question_index}:{option[:20]}"
            )])
    
    elif question_type == 'multiple' and options:
        # Несколько вариантов с чекбоксами
        for option in options:
            keyboard.append([InlineKeyboardButton(
                text=f"▢ {option}",
                callback_data=f"toggle_multi:{poll_id}:{question_id}:{option[:20]}"
            )])
        keyboard.append([InlineKeyboardButton(
            text="✅ Готово • Подтвердить выбор",
            callback_data=f"confirm_multi:{poll_id}:{question_id}:{question_index}"
        )])
    
    elif question_type == 'rating':
        # Рейтинг с визуальными индикаторами
        row1 = []
        row2 = []
        
        # Первая строка (1-5) с градиентом от плохого к среднему
        emojis1 = ["😟", "😕", "😐", "🙂", "😊"]
        for i in range(1, 6):
            row1.append(InlineKeyboardButton(
                text=f"{emojis1[i-1]} {i}",
                callback_data=f"answer_rating:{poll_id}:{question_id}:{question_index}:{i}"
            ))
        
        # Вторая строка (6-10) от хорошего к отличному
        emojis2 = ["😃", "😄", "🤗", "🤩", "🌟"]
        for i in range(6, 11):
            row2.append(InlineKeyboardButton(
                text=f"{emojis2[i-6]} {i}",
                callback_data=f"answer_rating:{poll_id}:{question_id}:{question_index}:{i}"
            ))
        
        keyboard.append(row1)
        keyboard.append(row2)
    
    elif question_type == 'text':
        # Для текстового ответа
        keyboard.append([InlineKeyboardButton(
            text="✏️ Написать ответ",
            callback_data=f"answer_text:{poll_id}:{question_id}:{question_index}"
        )])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def send_poll_to_user(bot, user_id, poll_id):
    """Отправляет опрос пользователю"""
    # Проверяем, не прошел ли пользователь уже этот опрос
    already_answered = await db.check_user_poll_participation(user_id, poll_id)
    if already_answered:
        return False
    
    # Получаем информацию об опросе
    poll_info = await db.get_poll_info(poll_id)
    if not poll_info:
        return False
    
    questions = await db.get_poll_questions(poll_id)
    
    # Красивый заголовок с градиентом эмодзи
    text = (
        "✨ ━━━━━━━━━━━━━━━━━━━━━ ✨\n"
        "        💫 <b>НОВЫЙ ОПРОС</b> 💫\n"
        "✨ ━━━━━━━━━━━━━━━━━━━━━ ✨\n\n"
        f"📌 <b>{poll_info['title'].upper()}</b>\n"
    )
    
    if poll_info.get('description'):
        text += f"\n💬 <i>{poll_info['description']}</i>\n"
    
    text += "\n" + "─" * 30 + "\n\n"
    
    # Информация в виде карточек
    text += f"📊 <b>Количество вопросов:</b> {len(questions)}\n"
    text += f"⏱ <b>Время прохождения:</b> ~{len(questions) * 30} секунд\n"
    text += f"🎯 <b>Тип:</b> Быстрый опрос\n\n"
    
    # Мотивационный текст
    text += "💡 <i>Ваше мнение поможет нам стать лучше!</i>\n\n"
    text += "✨ ━━━━━━━━━━━━━━━━━━━━━ ✨\n"
    text += "        Готовы начать? 🚀"
    
    await bot.send_message(
        user_id,
        text,
        parse_mode="HTML",
        reply_markup=create_poll_keyboard(poll_id, 0)
    )
    return True

@poll_callback_router.callback_query(F.data.startswith("start_poll:"))
async def start_poll_handler(callback: CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    poll_id = int(data_parts[1])
    question_index = int(data_parts[2])
    
    # Получаем вопросы опроса
    questions = await db.get_poll_questions(poll_id)
    
    if not questions:
        await callback.message.edit_text("❌ В опросе нет вопросов.")
        return
    
    # Сохраняем данные в состоянии
    await state.update_data(
        poll_id=poll_id,
        questions=questions,
        current_index=0,
        answers=[],
        selected_options=[]
    )
    
    # Показываем первый вопрос
    await show_poll_question(callback.message, state, callback.from_user.id)
    await callback.answer("🚀 Начинаем опрос!")

async def show_poll_question(message, state: FSMContext, user_id: int):
    """Показывает текущий вопрос опроса"""
    data = await state.get_data()
    questions = data['questions']
    current_index = data.get('current_index', 0)
    
    if current_index >= len(questions):
        # Опрос завершен
        await finish_poll(message, state, user_id)
        return
    
    question = questions[current_index]
    poll_id = data['poll_id']
    
    # Расчет прогресса - считаем только завершенные вопросы
    progress_percent = (current_index / len(questions)) * 100  # Убрали +1
    
    # Батарея прогресса с изменением цвета
    if progress_percent == 0:
        battery_emoji = "⚪"
        battery_icon = "🪫"  # Полностью разряженная батарея
    elif progress_percent <= 25:
        battery_emoji = "🔴"
        battery_icon = "🪫"
    elif progress_percent <= 50:
        battery_emoji = "🟠"
        battery_icon = "🔋"
    elif progress_percent <= 75:
        battery_emoji = "🟡"
        battery_icon = "🔋"
    else:
        battery_emoji = "🟢"
        battery_icon = "🔋"
    
    # Визуальный прогресс-бар
    filled = int((progress_percent / 100) * 10)
    empty = 10 - filled
    progress_bar = battery_emoji * filled + "⚪" * empty
    
    # Красивый заголовок
    text = (
        f"{battery_icon} <b>ВОПРОС {current_index + 1}/{len(questions)}</b>\n"
        f"{progress_bar} <code>{int(progress_percent)}%</code>\n"
        f"{'─' * 25}\n\n"
    )
    
    # Эмодзи для типов вопросов
    question_emojis = {
        'text': '',
        'single': '🎯',
        'multiple': '🎨',
        'rating': ''
    }
    
    emoji = question_emojis.get(question['type'], '❓')
    text += f"{emoji} <b>{question['text']}</b>\n\n"
    
    # Красивые подсказки для каждого типа
    if question['type'] == 'text':
        text += "╰➤ <i>Поделитесь своими мыслями в текстовом сообщении</i> ✍️"
    elif question['type'] == 'multiple':
        text += "╰➤ <i>Можете выбрать несколько подходящих вариантов</i> 🔲"
    elif question['type'] == 'rating':
        text += "╰➤ <i>Оцените по шкале от 1 до 10</i> 📊"
    elif question['type'] == 'single':
        text += "╰➤ <i>Выберите наиболее подходящий вариант</i> ⚡"
    
    keyboard = create_question_keyboard(
        poll_id,
        question['id'],
        question['type'],
        question.get('options'),
        current_index
    )
    
    await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

@poll_callback_router.callback_query(F.data.startswith("answer_single:"))
async def handle_single_answer(callback: CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    poll_id = int(data_parts[1])
    question_id = int(data_parts[2])
    question_index = int(data_parts[3])
    answer = data_parts[4] if len(data_parts) > 4 else ""
    
    # Получаем полный вариант ответа
    data = await state.get_data()
    questions = data['questions']
    current_question = questions[question_index]
    
    # Находим полный текст ответа
    full_answer = None
    for option in current_question.get('options', []):
        if option.startswith(answer):
            full_answer = option
            break
    
    if not full_answer:
        full_answer = answer
    
    # Сохраняем ответ
    await db.save_poll_response(poll_id, question_id, callback.from_user.id, full_answer)
    
    # Переходим к следующему вопросу
    answers = data.get('answers', [])
    answers.append(full_answer)
    await state.update_data(
        current_index=question_index + 1,
        answers=answers
    )
    
    await show_poll_question(callback.message, state, callback.from_user.id)
    await callback.answer(f"✅ Выбрано: {full_answer}")

@poll_callback_router.callback_query(F.data.startswith("answer_rating:"))
async def handle_rating_answer(callback: CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    poll_id = int(data_parts[1])
    question_id = int(data_parts[2])
    question_index = int(data_parts[3])
    rating = data_parts[4]
    
    # Сохраняем ответ
    await db.save_poll_response(poll_id, question_id, callback.from_user.id, rating)
    
    # Переходим к следующему вопросу
    data = await state.get_data()
    answers = data.get('answers', [])
    answers.append(f"Оценка: {rating}/10")
    await state.update_data(
        current_index=question_index + 1,
        answers=answers
    )
    
    await show_poll_question(callback.message, state, callback.from_user.id)
    
    # Эмодзи для обратной связи
    if int(rating) <= 3:
        emoji = "😔"
    elif int(rating) <= 6:
        emoji = "😐"
    elif int(rating) <= 8:
        emoji = "😊"
    else:
        emoji = "🤩"
    
    await callback.answer(f"{emoji} Оценка {rating}/10 записана!")

@poll_callback_router.callback_query(F.data.startswith("answer_text:"))
async def handle_text_answer_start(callback: CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    poll_id = int(data_parts[1])
    question_id = int(data_parts[2])
    question_index = int(data_parts[3])
    
    await state.update_data(
        text_question_id=question_id,
        text_question_index=question_index
    )
    
    await callback.message.edit_text(
        "💬 <b>Введите ваш ответ</b>\n\n"
        "Напишите текстовое сообщение и отправьте его 👇",
        parse_mode="HTML"
    )
    await state.set_state(PollAnsweringStates.answering_text)
    await callback.answer()

@poll_callback_router.message(PollAnsweringStates.answering_text)
async def handle_text_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    poll_id = data['poll_id']
    question_id = data['text_question_id']
    question_index = data['text_question_index']
    
    # Сохраняем ответ
    await db.save_poll_response(poll_id, question_id, message.from_user.id, message.text)
    
    # Удаляем сообщение пользователя для чистоты
    try:
        await message.delete()
    except:
        pass
    
    # Переходим к следующему вопросу
    answers = data.get('answers', [])
    answers.append(message.text)
    await state.update_data(
        current_index=question_index + 1,
        answers=answers
    )
    
    # Создаем новое сообщение для продолжения опроса
    poll_info = await db.get_poll_info(poll_id)
    new_message = await message.answer(
        f"✅ Ответ записан!\n\nПродолжаем опрос..."
    )
    
    await show_poll_question(new_message, state, message.from_user.id)
    await state.set_state(None)

@poll_callback_router.callback_query(F.data.startswith("toggle_multi:"))
async def handle_multi_toggle(callback: CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    poll_id = int(data_parts[1])
    question_id = int(data_parts[2])
    option = data_parts[3] if len(data_parts) > 3 else ""
    
    data = await state.get_data()
    selected = data.get('selected_options', [])
    
    # Находим полный текст опции
    questions = data['questions']
    current_index = data['current_index']
    current_question = questions[current_index]
    
    full_option = None
    for opt in current_question.get('options', []):
        if opt.startswith(option):
            full_option = opt
            break
    
    if not full_option:
        full_option = option
    
    if full_option in selected:
        selected.remove(full_option)
        await callback.answer(f"❌ Снят выбор: {full_option}")
    else:
        selected.append(full_option)
        await callback.answer(f"✅ Выбрано: {full_option}")
    
    await state.update_data(selected_options=selected)
    
    # Обновляем клавиатуру с отмеченными опциями
    keyboard = []
    for opt in current_question.get('options', []):
        icon = "▣" if opt in selected else "▢"
        keyboard.append([InlineKeyboardButton(
            text=f"{icon} {opt}",
            callback_data=f"toggle_multi:{poll_id}:{question_id}:{opt[:20]}"
        )])
    
    if selected:
        keyboard.append([InlineKeyboardButton(
            text=f"✅ Готово • Выбрано: {len(selected)}",
            callback_data=f"confirm_multi:{poll_id}:{question_id}:{current_index}"
        )])
    else:
        keyboard.append([InlineKeyboardButton(
            text="⚠️ Выберите хотя бы один вариант",
            callback_data=f"confirm_multi:{poll_id}:{question_id}:{current_index}"
        )])
    
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@poll_callback_router.callback_query(F.data.startswith("confirm_multi:"))
async def handle_multi_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get('selected_options', [])
    
    if not selected:
        await callback.answer("⚠️ Выберите хотя бы один вариант!", show_alert=True)
        return
    
    data_parts = callback.data.split(":")
    poll_id = int(data_parts[1])
    question_id = int(data_parts[2])
    question_index = int(data_parts[3])
    
    # Сохраняем ответ
    answer = ", ".join(selected)
    await db.save_poll_response(poll_id, question_id, callback.from_user.id, answer)
    
    # Переходим к следующему вопросу
    answers = data.get('answers', [])
    answers.append(answer)
    await state.update_data(
        current_index=question_index + 1,
        answers=answers,
        selected_options=[]
    )
    
    await show_poll_question(callback.message, state, callback.from_user.id)
    await callback.answer(f"✅ Ответ записан!")

async def finish_poll(message, state: FSMContext, user_id: int):
    """Завершение опроса"""
    data = await state.get_data()
    poll_id = data['poll_id']
    
    # Получаем информацию об опросе
    poll_info = await db.get_poll_info(poll_id)
    
    # Финальное сообщение
    finish_text = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "    🎉 <b>ОПРОС ЗАВЕРШЕН!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Спасибо за ваши ответы, а мы побежали делать бот еще лучше 💫\n\n"     
    )
    
    # Проверяем наличие медиа
    thank_you_media = poll_info.get('thank_you_media') or poll_info.get('thank_you_video')
    media_type = poll_info.get('thank_you_media_type', 'video')
    
    # Удаляем предыдущее сообщение с вопросом
    try:
        await message.delete()
    except:
        pass
    
    from bot.handlers import bot
    
    if thank_you_media:
        # Если есть медиа, отправляем его с полным текстом
        try:
            if media_type == 'video':
                await bot.send_video(
                    user_id, 
                    video=thank_you_media,
                    caption=finish_text,
                    parse_mode="HTML"
                )
            elif media_type == 'animation':
                await bot.send_animation(
                    user_id,
                    animation=thank_you_media,
                    caption=finish_text,
                    parse_mode="HTML"
                )
            elif media_type == 'document_gif':
                await bot.send_document(
                    user_id,
                    document=thank_you_media,
                    caption=finish_text,
                    parse_mode="HTML"
                )
        except Exception as e:
            print(f"Failed to send thank you media: {e}")
            # Если не удалось отправить медиа, отправляем просто текст
            await bot.send_message(user_id, finish_text, parse_mode="HTML")
    else:
        # Если нет медиа, отправляем только текстовое сообщение
        await bot.send_message(user_id, finish_text, parse_mode="HTML")
    
    await state.clear()
