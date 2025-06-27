import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging
from config import EMAIL_HOST, EMAIL_PORT, EMAIL_LOGIN, EMAIL_PASSWORD, EMAIL_TO

logger = logging.getLogger(__name__)

async def send_feedback_email(user_data: dict, feedback_type: str, message: str):
    """Отправка email о предложениях и жалобах"""
    try:
        type_text = "Предложение" if feedback_type == "suggestion" else "Жалоба"
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'{type_text} - {user_data.get("username", "Неизвестный пользователь")}'
        msg['From'] = EMAIL_LOGIN
        msg['To'] = EMAIL_TO
        
        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif;">
            <h2>{type_text}</h2>
            <p><strong>Дата и время:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            
            <h3>Информация о клиенте:</h3>
            <ul>
              <li><strong>Имя:</strong> {user_data.get('username', 'Не указано')}</li>
              <li><strong>Код клиента:</strong> {user_data.get('client_code', 'Не указан')}</li>
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
        
        Информация о клиенте:
        - Имя: {user_data.get('username', 'Не указано')}
        - Код клиента: {user_data.get('client_code', 'Не указан')}
        - Telegram ID: {user_data.get('telegram_id', 'Не указан')}
        
        Текст обращения:
        {message}
        """
        
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        if EMAIL_LOGIN and EMAIL_PASSWORD:
            await aiosmtplib.send(
                msg,
                hostname=EMAIL_HOST,
                port=EMAIL_PORT,
                start_tls=True,
                username=EMAIL_LOGIN,
                password=EMAIL_PASSWORD,
            )
            return True
        return False
            
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {e}")
        return False

async def send_callback_email(user_data: dict, phone: str, message: str):
    """Отправка email о заказе обратного звонка"""
    try:
        # Определяем страну
        country_map = {
            'RU': 'Россия',
            'BY': 'Беларусь',
            'KZ': 'Казахстан'
        }
        country_name = country_map.get(user_data.get('country', 'RU'), 'Не указана')
        
        # Создаем сообщение
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'Заказ обратного звонка - {user_data.get("username", "Неизвестный пользователь")} ({country_name})'
        msg['From'] = EMAIL_LOGIN
        msg['To'] = EMAIL_TO
        
        # HTML версия письма
        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif;">
            <h2>Новый заказ обратного звонка</h2>
            <p><strong>Дата и время:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            
            <h3>Информация о клиенте:</h3>
            <ul>
              <li><strong>Имя:</strong> {user_data.get('username', 'Не указано')}</li>
              <li><strong>Страна:</strong> {country_name}</li>
              <li><strong>Код клиента:</strong> {user_data.get('client_code', 'Не указан')}</li>
              <li><strong>Питомец:</strong> {user_data.get('pet_name', 'Не указан')} ({user_data.get('pet_type', 'Не указан')})</li>
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
              Это автоматическое сообщение от бота ветеринарной клиники
            </p>
          </body>
        </html>
        """
        
        # Текстовая версия
        text = f"""
        Новый заказ обратного звонка
        
        Дата и время: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        
        Информация о клиенте:
        - Имя: {user_data.get('username', 'Не указано')}
        - Страна: {country_name}
        - Код клиента: {user_data.get('client_code', 'Не указан')}
        - Питомец: {user_data.get('pet_name', 'Не указан')} ({user_data.get('pet_type', 'Не указан')})
        - Telegram ID: {user_data.get('telegram_id', 'Не указан')}
        
        Контактные данные:
        - Телефон: {phone}
        
        Сообщение:
        {message}
        
        ---
        Это автоматическое сообщение от бота ветеринарной клиники
        """
        
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Отправляем email
        if EMAIL_LOGIN and EMAIL_PASSWORD:
            await aiosmtplib.send(
                msg,
                hostname=EMAIL_HOST,
                port=EMAIL_PORT,
                start_tls=True,
                username=EMAIL_LOGIN,
                password=EMAIL_PASSWORD,
            )
            logger.info(f"Email успешно отправлен на {EMAIL_TO}")
            return True
        else:
            logger.error("Email credentials not configured")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {e}")
        return False