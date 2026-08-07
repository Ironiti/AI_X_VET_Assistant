import re
import asyncio
from collections import defaultdict
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import (
    CALLBACK_BUTTON_ALIASES,
    CLEAR_SUBMISSION_BUTTON,
    FEEDBACK_BUTTON_ALIASES,
    REMOVE_LAST_FILE_BUTTON,
    RESULTS_REQUEST_BUTTON_ALIASES,
    SEND_SUBMISSION_BUTTON,
    get_menu_by_role, 
    get_phone_kb, 
    get_feedback_type_kb, 
    get_contact_type_kb,
    get_submission_kb,
)
from utils.email_sender import send_callback_email, send_feedback_email
from bot.feedback_payload import (
    AttachmentDownloadError,
    AttachmentTooLargeError,
    MAX_ATTACHMENT_COUNT,
    MAX_TOTAL_ATTACHMENT_BYTES,
    SUPPORTED_ATTACHMENT_HINT,
    build_attachment_reference,
    build_admin_message,
    download_attachment_reference,
    extract_message_text,
)

from src.database.db_init import db
from bot.telegram_html import build_callback_confirmation_html

feedback_router = Router()
_draft_locks = defaultdict(asyncio.Lock)


def _files_label(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "файл"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "файла"
    return "файлов"


def _draft_summary(text: str, attachments: list[dict]) -> str:
    parts = []
    if text:
        parts.append("текст")
    if attachments:
        parts.append(f"{len(attachments)} {_files_label(len(attachments))}")
    added = " и ".join(parts) if parts else "пока ничего"
    return (
        f"Добавлено: {added}.\n\n"
        "Можно добавить ещё или нажать «✅ Отправить»."
    )


async def _reset_draft(state: FSMContext) -> None:
    await state.update_data(
        draft_text="",
        draft_attachments=[],
        draft_sending=False,
    )


async def _handle_draft_controls(message: Message, state: FSMContext) -> bool:
    async with _draft_locks[message.from_user.id]:
        return await _handle_draft_controls_unlocked(message, state)


async def _handle_draft_controls_unlocked(message: Message, state: FSMContext) -> bool:
    if message.text == CLEAR_SUBMISSION_BUTTON:
        await _reset_draft(state)
        await message.answer(
            "Черновик очищен. Отправьте новый текст или файл.",
            reply_markup=get_submission_kb(),
        )
        return True

    if message.text == REMOVE_LAST_FILE_BUTTON:
        data = await state.get_data()
        attachments = list(data.get("draft_attachments", []))
        if not attachments:
            await message.answer(
                "В черновике нет файлов.",
                reply_markup=get_submission_kb(),
            )
            return True
        removed = attachments.pop()
        await state.update_data(draft_attachments=attachments)
        await message.answer(
            f"Файл «{removed['filename']}» удалён.\n\n"
            f"{_draft_summary(data.get('draft_text', ''), attachments)}",
            reply_markup=get_submission_kb(),
        )
        return True

    return False


async def _collect_draft_item(message: Message, state: FSMContext) -> None:
    async with _draft_locks[message.from_user.id]:
        await _collect_draft_item_unlocked(message, state)


async def _collect_draft_item_unlocked(message: Message, state: FSMContext) -> None:
    text = extract_message_text(message)
    try:
        reference = build_attachment_reference(message)
    except AttachmentTooLargeError:
        await message.answer(
            "Этот файл больше 15 МБ. Выберите файл меньшего размера.",
            reply_markup=get_submission_kb(),
        )
        return

    if not text and reference is None:
        await message.answer(
            "Отправьте текст, голосовое сообщение или файл.",
            reply_markup=get_submission_kb(),
        )
        return

    data = await state.get_data()
    if data.get("draft_sending"):
        await message.answer("Обращение уже отправляется.")
        return
    draft_text = data.get("draft_text", "")
    attachments = list(data.get("draft_attachments", []))

    if text:
        combined_text = f"{draft_text}\n{text}".strip()
        if len(combined_text) > 10000:
            await message.answer(
                "Текст слишком длинный. Сократите его и отправьте ещё раз.",
                reply_markup=get_submission_kb(),
            )
            return
        draft_text = combined_text

    if reference is not None:
        if len(attachments) >= MAX_ATTACHMENT_COUNT:
            await message.answer(
                f"Можно добавить не больше {MAX_ATTACHMENT_COUNT} файлов. "
                "Удалите последний файл или отправьте обращение.",
                reply_markup=get_submission_kb(),
            )
            return

        known_total = sum(item.get("file_size") or 0 for item in attachments)
        known_total += reference.get("file_size") or 0
        if known_total > MAX_TOTAL_ATTACHMENT_BYTES:
            await message.answer(
                "Общий размер файлов больше 18 МБ. "
                "Удалите последний файл или выберите файлы меньшего размера.",
                reply_markup=get_submission_kb(),
            )
            return
        attachments.append(reference)

    await state.update_data(draft_text=draft_text, draft_attachments=attachments)
    await message.answer(
        _draft_summary(draft_text, attachments),
        reply_markup=get_submission_kb(),
    )


async def _get_draft_for_sending(message: Message, state: FSMContext):
    async with _draft_locks[message.from_user.id]:
        return await _get_draft_for_sending_unlocked(message, state)


async def _get_draft_for_sending_unlocked(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("draft_sending"):
        await message.answer("Обращение уже отправляется.")
        return None
    draft_text = data.get("draft_text", "").strip()
    references = list(data.get("draft_attachments", []))
    if not draft_text and not references:
        await message.answer(
            "Сначала добавьте текст или файл.",
            reply_markup=get_submission_kb(),
        )
        return None

    attachments = []
    for index, reference in enumerate(references):
        try:
            attachments.append(
                await download_attachment_reference(message.bot, reference)
            )
        except AttachmentTooLargeError:
            references.pop(index)
            await state.update_data(draft_attachments=references)
            await message.answer(
                f"Файл «{reference['filename']}» больше 15 МБ и удалён из черновика. "
                "Прикрепите файл меньшего размера.",
                reply_markup=get_submission_kb(),
            )
            return None
        except AttachmentDownloadError:
            references.pop(index)
            await state.update_data(draft_attachments=references)
            await message.answer(
                f"Файл «{reference['filename']}» не загрузился и удалён из черновика. "
                "Прикрепите его ещё раз.",
                reply_markup=get_submission_kb(),
            )
            return None

    if sum(len(attachment.data) for attachment in attachments) > MAX_TOTAL_ATTACHMENT_BYTES:
        await message.answer(
            "Общий размер файлов больше 18 МБ. Удалите один из файлов.",
            reply_markup=get_submission_kb(),
        )
        return None

    labels = [reference["label"] for reference in references]
    admin_text = draft_text or "Без текстового комментария."
    admin_message = build_admin_message(admin_text, ", ".join(labels))
    await state.update_data(draft_sending=True)
    return data, draft_text, references, attachments, admin_message

class ContactStates(StatesGroup):
    """Состояния для общей функции связи с лабораторией"""
    waiting_for_contact_type = State()
    waiting_for_phone = State()
    waiting_for_callback_message = State()
    waiting_for_feedback_type = State()
    waiting_for_feedback_message = State()
    waiting_for_results_message = State()

def format_phone_number(phone: str, country: str = 'BY'):
    """Форматирование телефонного номера с учетом страны"""
    digits = re.sub(r'\D', '', phone)
    
    if country == 'BY':
        # Добавляем код страны если его нет
        if len(digits) == 9:
            digits = '375' + digits
        if len(digits) == 12 and digits.startswith('375'):
            return f"+{digits[:3]} ({digits[3:5]}) {digits[5:8]}-{digits[8:10]}-{digits[10:12]}"
    
    elif country == 'RU':
        # Для России
        if len(digits) == 10:
            digits = '7' + digits
        elif len(digits) == 11 and digits.startswith('8'):
            digits = '7' + digits[1:]
        if len(digits) == 11 and digits.startswith('7'):
            return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    
    elif country == 'KZ':
        # Для Казахстана
        if len(digits) == 10 and digits.startswith('7'):
            digits = '7' + digits
        elif len(digits) == 11 and digits.startswith('8'):
            digits = '7' + digits[1:]
        if len(digits) == 11 and digits.startswith('77'):
            return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    elif country == 'AM':
        # Для Армении
        if len(digits) == 8:
            digits = '374' + digits
        if len(digits) == 11 and digits.startswith('374'):
            return f"+{digits[:3]} ({digits[3:5]}) {digits[5:8]}-{digits[8:11]}" 
    return phone  

def validate_phone_number(phone: str, country: str = 'BY'):
    """Валидация телефонного номера с учетом страны"""
    digits = re.sub(r'\D', '', phone)
    
    if country == 'BY':
        # Беларусь: +375 XX XXX-XX-XX
        return bool(re.match(r'^(375)?[0-9]{9}$', digits))
    elif country == 'RU':
        # Россия: +7 XXX XXX-XX-XX
        return bool(re.match(r'^[78]?[0-9]{10}$', digits))
    elif country == 'KZ':
        # Казахстан: +7 7XX XXX-XX-XX
        return bool(re.match(r'^[78]?7[0-9]{9}$', digits))
    elif country == 'AM':
        # Армения: +374 XX XXX-XXX
        return bool(re.match(r'^(374)?[0-9]{8}$', digits))
    return False


async def _get_registered_user(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer(
            "Для использования этой функции необходимо пройти регистрацию.\n"
            "Используйте команду /start"
        )
    return user


async def _start_callback_flow(message: Message, state: FSMContext, user) -> None:
    country = user['country'] if 'country' in user.keys() else 'BY'
    await state.update_data(user_country=country, contact_type='callback')

    phone_formats = {
        'BY': "+375 (XX) XXX-XX-XX",
        'RU': "+7 (XXX) XXX-XX-XX",
        'KZ': "+7 (7XX) XXX-XX-XX",
        'AM': "+374 (XX) XXX-XXX",
    }
    format_hint = phone_formats.get(country, phone_formats['BY'])

    await message.answer(
        "📞 Заказ звонка\n\n"
        "Нажмите «Поделиться номером» или введите его вручную.\n"
        f"Пример: {format_hint}",
        reply_markup=get_phone_kb(),
    )
    await state.set_state(ContactStates.waiting_for_phone)


async def _start_feedback_flow(message: Message, state: FSMContext) -> None:
    await state.update_data(contact_type='feedback')
    await message.answer("Выберите тип обращения:", reply_markup=get_feedback_type_kb())
    await state.set_state(ContactStates.waiting_for_feedback_type)


@feedback_router.message(F.text.in_(CALLBACK_BUTTON_ALIASES))
async def start_callback(message: Message, state: FSMContext):
    user = await _get_registered_user(message)
    if not user:
        return
    await _start_callback_flow(message, state, user)


@feedback_router.message(F.text.in_(FEEDBACK_BUTTON_ALIASES))
async def start_feedback(message: Message, state: FSMContext):
    user = await _get_registered_user(message)
    if not user:
        return
    await _start_feedback_flow(message, state)


@feedback_router.message(F.text.in_(RESULTS_REQUEST_BUTTON_ALIASES))
async def start_results_request(message: Message, state: FSMContext):
    user = await _get_registered_user(message)
    if not user:
        return

    country = user['country'] if 'country' in user.keys() else 'BY'
    phone_formats = {
        'BY': "+375 (XX) XXX-XX-XX",
        'RU': "+7 (XXX) XXX-XX-XX",
        'KZ': "+7 (7XX) XXX-XX-XX",
        'AM': "+374 (XX) XXX-XXX",
    }
    format_hint = phone_formats.get(country, phone_formats['BY'])

    await state.update_data(
        user_country=country,
        contact_type='results_request',
        phone=None,
    )
    await _reset_draft(state)
    await message.answer(
        "🧪 Запрос по результатам\n\n"
        "Укажите номер, по которому лаборатория сможет с вами связаться.\n"
        "Нажмите «Поделиться номером» или введите его вручную.\n"
        f"Пример: {format_hint}",
        reply_markup=get_phone_kb(),
    )
    await state.set_state(ContactStates.waiting_for_phone)


@feedback_router.message(ContactStates.waiting_for_results_message)
async def process_results_request(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        return

    if await _handle_draft_controls(message, state):
        return

    if message.text != SEND_SUBMISSION_BUTTON:
        await _collect_draft_item(message, state)
        return

    draft = await _get_draft_for_sending(message, state)
    if draft is None:
        return
    data, draft_text, references, attachments, admin_message = draft
    phone = data.get('phone')

    user = await db.get_user(user_id)
    user_dict = dict(user) if user else {}
    email_sent = await send_feedback_email(
        user_dict,
        'results_request',
        admin_message,
        attachment=attachments,
        phone=phone,
    )
    if not email_sent:
        await state.update_data(draft_sending=False)
        await message.answer(
            "❌ Не удалось отправить запрос. Попробуйте ещё раз.",
            reply_markup=get_submission_kb(),
        )
        return

    await db.add_feedback(
        user_id=user_id,
        feedback_type='results_request',
        message=draft_text or "Без текстового комментария.",
        media_type=references[0]["media_type"] if references else None,
        media_file_id=references[0]["file_id"] if references else None,
    )
    await db.add_request_stat(user_id, 'results_request', admin_message[:500])

    user_role = user['role'] if user else 'user'
    await message.answer(
        "✅ Запрос по результатам отправлен в лабораторию.\n\n"
        f"Сотрудник свяжется с вами по номеру {phone}.",
        reply_markup=get_menu_by_role(user_role),
    )
    await state.clear()

@feedback_router.message(F.text == "📞 Связь с лабораторией")
async def start_contact(message: Message, state: FSMContext):
    """Начало процесса связи с лабораторией"""
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await message.answer("Для использования этой функции необходимо пройти регистрацию.\nИспользуйте команду /start")
        return

    await message.answer(
        "📞 Связь с лабораторией\n\n"
        "Выберите тип обращения:",
        reply_markup=get_contact_type_kb()
    )
    await state.set_state(ContactStates.waiting_for_contact_type)
    print(f"[INFO] User {user_id} started contact process")

@feedback_router.message(ContactStates.waiting_for_contact_type)
async def process_contact_type(message: Message, state: FSMContext):
    """Обработка выбора типа обращения"""
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        return

    if message.text == "📞 Заказать звонок":
        user = await db.get_user(user_id)
        await _start_callback_flow(message, state, user)
        print(f"[INFO] User {user_id} chose callback request")
        
    elif message.text == "💡 Предложение/жалоба":
        await _start_feedback_flow(message, state)
        print(f"[INFO] User {user_id} chose feedback submission")
        
    else:
        await message.answer(
            "Пожалуйста, выберите тип обращения из предложенных вариантов.",
            reply_markup=get_contact_type_kb()
        )

@feedback_router.message(ContactStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обработка номера телефона для заказа звонка"""
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        return

    data = await state.get_data()
    country = data.get('user_country', 'BY')
    contact_type = data.get('contact_type')
    phone = ""

    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone
    else:
        if not message.text:
            await message.answer(
                "Пожалуйста, отправьте номер телефона текстом или кнопкой контакта.",
                reply_markup=get_phone_kb()
            )
            return

        phone = message.text
        if not validate_phone_number(phone, country):
            phone_examples = {
                'BY': "375291234567 или +375 29 123-45-67",
                'RU': "79123456789 или +7 912 345-67-89",
                'KZ': "77012345678 или +7 701 234-56-78",
                'AM': "37477123456 или +374 77 123-456"
            }
            example = phone_examples.get(country, phone_examples['BY'])
            
            await message.answer(
                f"❌ Неверный формат номера телефона.\n"
                f"Пожалуйста, введите номер в формате:\n"
                f"{example}",
                reply_markup=get_phone_kb()
            )
            return
        
        phone = format_phone_number(phone, country)

    await state.update_data(phone=phone)

    if contact_type == 'results_request':
        await message.answer(
            "Опишите вопрос по готовому результату и при необходимости приложите сам результат.\n\n"
            f"{SUPPORTED_ATTACHMENT_HINT}\n\n"
            "Когда всё будет готово, нажмите «✅ Отправить».",
            reply_markup=get_submission_kb(),
        )
        await state.set_state(ContactStates.waiting_for_results_message)
        return

    await _reset_draft(state)
    await message.answer(
        "Коротко напишите, о чём хотите поговорить и когда вам удобно принять звонок.\n\n"
        f"{SUPPORTED_ATTACHMENT_HINT}\n\n"
        "Когда всё будет готово, нажмите «✅ Отправить».",
        reply_markup=get_submission_kb()
    )
    await state.set_state(ContactStates.waiting_for_callback_message)

@feedback_router.message(ContactStates.waiting_for_callback_message)
async def process_callback_message(message: Message, state: FSMContext):
    """Обработка сообщения для заказа звонка"""
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        print(f"[INFO] User {user_id} cancelled callback message")
        return

    if await _handle_draft_controls(message, state):
        return

    if message.text != SEND_SUBMISSION_BUTTON:
        await _collect_draft_item(message, state)
        return

    draft = await _get_draft_for_sending(message, state)
    if draft is None:
        return
    data, draft_text, references, attachments, admin_message = draft

    phone = data.get('phone')
    user = await db.get_user(user_id)
    
    # Преобразуем Row в словарь
    user_dict = dict(user) if user else {}

    print(f"[INFO] Sending callback email for user {user_id}")
    email_sent = await send_callback_email(user_dict, phone, admin_message, attachment=attachments)

    if email_sent:
        print(f"[INFO] Callback email sent for user {user_id}")
    else:
        print(f"[WARN] Callback email failed for user {user_id}")
        await state.update_data(draft_sending=False)
        await message.answer(
            "❌ Не удалось отправить заявку по почте. Попробуйте отправить обращение ещё раз — "
            "введённые данные сохранены на этом шаге.",
            reply_markup=get_submission_kb(),
        )
        return

    await db.add_request_stat(user_id, "callback_request", f"Телефон: {phone}, Сообщение: {admin_message[:100]}...")
    print(f"[INFO] Callback stat saved for user {user_id}")

    user_role = user['role'] if user else 'user'
    attachment_label = f"{len(references)} файл(а)" if references else None
    await message.answer(
        build_callback_confirmation_html(phone, draft_text, attachment_label),
        reply_markup=get_menu_by_role(user_role)
    )
    await state.clear()
    print(f"[INFO] State cleared for user {user_id}")

@feedback_router.message(ContactStates.waiting_for_feedback_type)
async def process_feedback_type(message: Message, state: FSMContext):
    """Обработка выбора типа обратной связи"""
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        print(f"[INFO] User {user_id} cancelled feedback type selection")
        return

    if message.text not in ["💡 Предложение", "⚠️ Жалоба"]:
        print(f"[WARN] User {user_id} entered invalid feedback type: {message.text}")
        await message.answer("Пожалуйста, выберите тип обращения из предложенных вариантов.", reply_markup=get_feedback_type_kb())
        return

    feedback_type = "suggestion" if message.text == "💡 Предложение" else "complaint"
    await state.update_data(feedback_type=feedback_type)
    await _reset_draft(state)
    print(f"[INFO] User {user_id} selected feedback type: {feedback_type}")

    prompt = (
        "Расскажите, что произошло."
        if feedback_type == "complaint"
        else "Напишите, что вы предлагаете улучшить."
    )
    await message.answer(
        f"{prompt}\n\n{SUPPORTED_ATTACHMENT_HINT}\n\n"
        "Когда всё будет готово, нажмите «✅ Отправить».",
        reply_markup=get_submission_kb()
    )
    await state.set_state(ContactStates.waiting_for_feedback_message)
    print(f"[INFO] State set to waiting_for_feedback_message for user {user_id}")

@feedback_router.message(ContactStates.waiting_for_feedback_message)
async def process_feedback_message(message: Message, state: FSMContext):
    """Обработка сообщения обратной связи"""
    user_id = message.from_user.id

    if message.text == "🔙 Вернуться в главное меню":
        await state.clear()
        user = await db.get_user(user_id)
        user_role = user['role'] if user else 'user'
        await message.answer("Операция отменена.", reply_markup=get_menu_by_role(user_role))
        print(f"[INFO] User {user_id} cancelled feedback message")
        return

    if await _handle_draft_controls(message, state):
        return

    if message.text != SEND_SUBMISSION_BUTTON:
        await _collect_draft_item(message, state)
        return

    draft = await _get_draft_for_sending(message, state)
    if draft is None:
        return
    data, draft_text, references, attachments, admin_message = draft

    feedback_type = data.get('feedback_type')
    user = await db.get_user(user_id)
    
    # Преобразуем Row в словарь
    user_dict = dict(user) if user else {}

    email_sent = await send_feedback_email(
        user_dict,
        feedback_type,
        admin_message,
        attachment=attachments,
    )
    if not email_sent:
        print(f"[WARN] Feedback email failed for user {user_id}")
        await state.update_data(draft_sending=False)
        await message.answer(
            "❌ Не удалось отправить обращение по почте. Попробуйте отправить его ещё раз — "
            "текущий шаг не сброшен.",
            reply_markup=get_submission_kb(),
        )
        return

    await db.add_feedback(
        user_id=user_id,
        feedback_type=feedback_type,
        message=draft_text or "Без текстового комментария.",
        media_type=references[0]["media_type"] if references else None,
        media_file_id=references[0]["file_id"] if references else None,
    )
    print(f"[INFO] Feedback email sent and saved to DB for user {user_id}")

    type_text = "предложение" if feedback_type == "suggestion" else "жалоба"
    user_role = user['role'] if user else 'user'
    await message.answer(
        f"✅ Ваше {type_text} отправлено.",
        reply_markup=get_menu_by_role(user_role)
    )
    await state.clear()
    print(f"[INFO] State cleared for user {user_id}")
