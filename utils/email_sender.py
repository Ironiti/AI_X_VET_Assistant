import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging
from config import EMAIL_HOST, EMAIL_PORT, EMAIL_LOGIN, EMAIL_PASSWORD, EMAIL_TO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def send_feedback_email(user_data: dict, feedback_type: str, message: str):
    """Отправка email о предложениях и жалобах"""
    try:
        type_text = "Предложение" if feedback_type == "suggestion" else "Жалоба"
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'{type_text} - {user_data.get("name", "Неизвестный пользователь")}'
        msg['From'] = EMAIL_LOGIN
        msg['To'] = EMAIL_TO
        
        # Определяем тип пользователя
        if user_data.get('user_type') == 'client':
            user_type = "Ветеринарный врач клиники-партнера"
            additional_info = f"""
              <li><strong>Код клиента:</strong> {user_data.get('client_code', 'Не указан')}</li>
              <li><strong>Специализация:</strong> {user_data.get('specialization', 'Не указана')}</li>
            """
        elif user_data.get('user_type') == 'employee':
            user_type = "Сотрудник VET UNION"
            dept_map = {'laboratory': 'Лаборатория', 'sales': 'Продажи', 'support': 'Поддержка'}
            dept = dept_map.get(user_data.get('department_function', ''), user_data.get('department_function', ''))
            additional_info = f"""
              <li><strong>Регион:</strong> {user_data.get('region', 'Не указан')}</li>
              <li><strong>Функция:</strong> {dept}</li>
            """
        else:
            user_type = "Пользователь"
            additional_info = ""
        
        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif;">
            <h2>{type_text}</h2>
            <p><strong>Дата и время:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            
            <h3>Информация о пользователе:</h3>
            <ul>
              <li><strong>Имя:</strong> {user_data.get('name', 'Не указано')}</li>
              <li><strong>Тип:</strong> {user_type}</li>
              {additional_info}
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
        - Тип: {user_type}
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
            
            response = await aiosmtplib.send(
                msg,
                hostname=EMAIL_HOST,
                port=EMAIL_PORT,
                start_tls=True,
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
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'Заказ обратного звонка - {user_data.get("name", "Неизвестный пользователь")}'
        msg['From'] = EMAIL_LOGIN
        msg['To'] = EMAIL_TO
        msg['Reply-To'] = EMAIL_LOGIN
        msg['X-Mailer'] = 'Python/aiosmtplib'
        
        # Определяем тип пользователя и дополнительную информацию
        if user_data.get('user_type') == 'client':
            user_type = "Ветеринарный врач клиники-партнера"
            additional_info = f"""
              <li><strong>Код клиента:</strong> {user_data.get('client_code', 'Не указан')}</li>
              <li><strong>Специализация:</strong> {user_data.get('specialization', 'Не указана')}</li>
            """
            additional_text = f"""
        - Код клиента: {user_data.get('client_code', 'Не указан')}
        - Специализация: {user_data.get('specialization', 'Не указана')}"""
        elif user_data.get('user_type') == 'employee':
            user_type = "Сотрудник VET UNION"
            dept_map = {'laboratory': 'Лаборатория', 'sales': 'Продажи', 'support': 'Поддержка'}
            dept = dept_map.get(user_data.get('department_function', ''), user_data.get('department_function', ''))
            additional_info = f"""
              <li><strong>Регион:</strong> {user_data.get('region', 'Не указан')}</li>
              <li><strong>Функция:</strong> {dept}</li>
            """
            additional_text = f"""
        - Регион: {user_data.get('region', 'Не указан')}
        - Функция: {dept}"""
        else:
            user_type = "Пользователь"
            additional_info = ""
            additional_text = ""
        
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
              <li><strong>Тип:</strong> {user_type}</li>
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
        
        text = f"""
        Новый заказ обратного звонка
        
        Дата и время: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        
        Информация о пользователе:
        - Имя: {user_data.get('name', 'Не указано')}
        - Тип: {user_type}{additional_text}
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
        
        if EMAIL_LOGIN and EMAIL_PASSWORD:
            logger.info(f"Attempting to send callback email from {EMAIL_LOGIN} to {EMAIL_TO}")
            
            response = await aiosmtplib.send(
                msg,
                hostname=EMAIL_HOST,
                port=EMAIL_PORT,
                start_tls=True,
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