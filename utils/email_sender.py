# utils/email_sender.py
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging
from config import EMAIL_HOST, EMAIL_PORT, EMAIL_LOGIN, EMAIL_PASSWORD, EMAIL_TO

# Настроим более подробное логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def send_feedback_email(user_data: dict, feedback_type: str, message: str):
    """Отправка email о предложениях и жалобах"""
    try:
        type_text = "Предложение" if feedback_type == "suggestion" else "Жалоба"
        
        # Определяем тип пользователя для отображения
        user_type_text = "Неизвестно"
        if user_data.get('user_type') == 'client':
            user_type_text = f"Клиент ({user_data.get('client_code', 'Не указан')})"
        elif user_data.get('user_type') == 'employee':
            dept = user_data.get('department_function', '')
            dept_map = {'laboratory': 'Лаборатория', 'sales': 'Продажи', 'support': 'Поддержка'}
            dept_text = dept_map.get(dept, dept)
            user_type_text = f"Сотрудник ({dept_text})"
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'{type_text} - {user_data.get("name", "Неизвестный пользователь")}'
        msg['From'] = EMAIL_LOGIN
        msg['To'] = EMAIL_TO
        
        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif;">
            <h2>{type_text}</h2>
            <p><strong>Дата и время:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            
            <h3>Информация о пользователе:</h3>
            <ul>
              <li><strong>Имя:</strong> {user_data.get('name', 'Не указано')}</li>
              <li><strong>Тип:</strong> {user_type_text}</li>
              <li><strong>Telegram ID:</strong> {user_data.get('telegram_id', 'Не указан')}</li>
            </ul>
            
            <h3>Текст обращения:</h3>
            <p style="background-color: #f0f0f0; padding: 10px; border-radius: 5px;">
              {message}
            </p>
          </body>
        </html>
        """
        
        text = f"""
        {type_text}
        
        Дата и время: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        
        Информация о пользователе:
        - Имя: {user_data.get('name', 'Не указано')}
        - Тип: {user_type_text}
        - Telegram ID: {user_data.get('telegram_id', 'Не указан')}
        
        Текст обращения:
        {message}
        """
        
        part1 = MIMEText(text, 'plain', 'utf-8')
        part2 = MIMEText(html, 'html', 'utf-8')
        
        msg.attach(part1)
        msg.attach(part2)
        
        if EMAIL_LOGIN and EMAIL_PASSWORD:
            logger.info(f"Attempting to send email from {EMAIL_LOGIN} to {EMAIL_TO}")
            logger.info(f"Using SMTP server: smtp.yandex.ru:465")
            
            response = await aiosmtplib.send(
                msg,
                hostname='smtp.yandex.ru',
                port=465,
                use_tls=True,
                username=EMAIL_LOGIN,
                password=EMAIL_PASSWORD,
            )
            
            logger.info(f"Email sent successfully. Response: {response}")
            return True
        else:
            logger.error("Email credentials not configured")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {e}", exc_info=True)
        return False

async def send_callback_email(user_data: dict, phone: str, message: str):
    """Отправка email о заказе обратного звонка"""
    try:
        # Определяем тип пользователя для отображения
        user_type_text = "Неизвестно"
        additional_info = ""
        
        if user_data.get('user_type') == 'client':
            user_type_text = "Ветеринарный врач клиники-партнера"
            additional_info = f"""
              <li><strong>Код клиента:</strong> {user_data.get('client_code', 'Не указан')}</li>
              <li><strong>Специализация:</strong> {user_data.get('specialization', 'Не указана')}</li>
            """
        elif user_data.get('user_type') == 'employee':
            dept = user_data.get('department_function', '')
            dept_map = {'laboratory': 'Лаборатория', 'sales': 'Продажи', 'support': 'Поддержка'}
            dept_text = dept_map.get(dept, dept)
            user_type_text = "Сотрудник VET UNION"
            additional_info = f"""
              <li><strong>Регион:</strong> {user_data.get('region', 'Не указан')}</li>
              <li><strong>Функция:</strong> {dept_text}</li>
            """
        
        # Создаем сообщение
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'Заказ обратного звонка - {user_data.get("name", "Неизвестный пользователь")}'
        msg['From'] = EMAIL_LOGIN
        msg['To'] = EMAIL_TO
        # Добавим заголовки для лучшей доставляемости
        msg['Reply-To'] = EMAIL_LOGIN
        msg['X-Mailer'] = 'Python/aiosmtplib'
        
        # HTML версия письма
        html = f"""
        <html>
          <head>
            <meta charset="utf-8">
          </head>
          <body style="font-family: Arial, sans-serif;">
            <h2>Новый заказ обратного звонка</h2>
            <p><strong>Дата и время:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            
            <h3>Информация о пользователе:</h3>
            <ul>
              <li><strong>Имя:</strong> {user_data.get('name', 'Не указано')}</li>
              <li><strong>Тип:</strong> {user_type_text}</li>
              {additional_info}
              <li><strong>Telegram ID:</strong> {user_data.get('telegram_id', 'Не указан')}</li>
            </ul>
            
            <h3>Контактные данные:</h3>
            <ul>
              <li><strong>Телефон:</strong> {phone}</li>
            </ul>
            
            <h3>Сообщение:</h3>
            <p style="background-color: #f0f0f0; padding: 10px; border-radius: 5px;">
              {message}
            </p>
            
            <hr>
            <p style="color: #666; font-size: 12px;">
              Это автоматическое сообщение от бота лаборатории VET UNION
            </p>
          </body>
        </html>
        """
        
        # Текстовая версия
        text = f"""
        Новый заказ обратного звонка
        
        Дата и время: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        
        Информация о пользователе:
        - Имя: {user_data.get('name', 'Не указано')}
        - Тип: {user_type_text}
        - Telegram ID: {user_data.get('telegram_id', 'Не указан')}
        
        Контактные данные:
        - Телефон: {phone}
        
        Сообщение:
        {message}
        
        ---
        Это автоматическое сообщение от бота лаборатории VET UNION
        """
        
        part1 = MIMEText(text, 'plain', 'utf-8')
        part2 = MIMEText(html, 'html', 'utf-8')
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Отправляем email
        if EMAIL_LOGIN and EMAIL_PASSWORD:
            logger.info(f"Attempting to send callback email from {EMAIL_LOGIN} to {EMAIL_TO}")
            logger.info(f"Subject: {msg['Subject']}")
            logger.info(f"User data: {user_data}")
            
            response = await aiosmtplib.send(
                msg,
                hostname='smtp.yandex.ru',
                port=465,
                use_tls=True,
                username=EMAIL_LOGIN,
                password=EMAIL_PASSWORD,
            )
            
            logger.info(f"Email sent successfully. SMTP Response: {response}")
            return True
        else:
            logger.error("Email credentials not configured")
            return False
            
    except aiosmtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {e}", exc_info=True)
        return False