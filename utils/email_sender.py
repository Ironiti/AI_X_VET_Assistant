import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
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
            user_type = "Сотрудник X-LAB VET"
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
            user_type = "Сотрудник X-LAB VET"
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
              Это автоматическое сообщение от бота лаборатории X-LAB VET
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
        Это автоматическое сообщение от бота лаборатории X-LAB VET
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

async def send_monthly_metrics_email(excel_data: bytes, month_name: str, metrics_recipient: str = None):
    """
    Отправка ежемесячного отчета по метрикам на email
    
    Args:
        excel_data: Данные Excel файла в байтах
        month_name: Название месяца для отчета (например, "Октябрь 2025")
        metrics_recipient: Email получателя (если None, используется EMAIL_TO)
    """
    try:
        recipient = metrics_recipient or EMAIL_TO
        
        msg = MIMEMultipart('mixed')
        msg['Subject'] = f'Ежемесячный отчет по метрикам X-LAB - {month_name}'
        msg['From'] = EMAIL_LOGIN
        msg['To'] = recipient
        msg['Reply-To'] = EMAIL_LOGIN
        msg['X-Mailer'] = 'Python/aiosmtplib'
        
        # HTML тело письма
        html = f"""
        <html>
          <head>
            <meta charset="utf-8">
            <style>
              body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
              }}
              .header {{
                background-color: #1E3A8A;
                color: white;
                padding: 20px;
                text-align: center;
              }}
              .content {{
                padding: 20px;
                background-color: #f9f9f9;
              }}
              .info-box {{
                background-color: white;
                border-left: 4px solid #3B82F6;
                padding: 15px;
                margin: 15px 0;
              }}
              .footer {{
                padding: 20px;
                text-align: center;
                color: #666;
                font-size: 12px;
              }}
            </style>
          </head>
          <body>
            <div class="header">
              <h1>📊 Ежемесячный отчет по метрикам</h1>
              <p>{month_name}</p>
            </div>
            
            <div class="content">
              <div class="info-box">
                <h2>📈 Сводка за месяц</h2>
                <p>Во вложении содержится полный отчет по метрикам системы за прошедший месяц.</p>
                <p><strong>Дата формирования:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
              </div>
              
              <div class="info-box">
                <h3>📋 Что включает отчет:</h3>
                <ul>
                  <li><strong>👥 Клиентские метрики</strong> - DAU, retention, активность пользователей</li>
                  <li><strong>⚙️ Технические метрики</strong> - производительность системы, время ответа</li>
                  <li><strong>🎯 Метрики качества</strong> - успешность обработки запросов, типы взаимодействий</li>
                  <li><strong>📊 Детальные данные</strong> - история всех взаимодействий</li>
                  <li><strong>📖 Инструкции</strong> - справка по интерпретации метрик</li>
                </ul>
              </div>
              
              <div class="info-box">
                <h3>🔄 Накопление данных:</h3>
                <p>Данные метрик сохраняются для формирования годовой статистики.
                Следующий отчет будет отправлен в конце следующего месяца.</p>
              </div>
            </div>
            
            <div class="footer">
              <p>Это автоматическое сообщение от системы метрик AI VET Assistant</p>
            </div>
          </body>
        </html>
        """
        
        # Добавляем только HTML часть (без текстовой версии)
        html_part = MIMEText(html, 'html', 'utf-8')
        msg.attach(html_part)
        
        # Добавляем Excel файл как вложение
        attachment = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        attachment.set_payload(excel_data)
        encoders.encode_base64(attachment)
        
        filename = f"metrics_report_{datetime.now().strftime('%Y_%m')}.xlsx"
        attachment.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        msg.attach(attachment)
        
        if EMAIL_LOGIN and EMAIL_PASSWORD:
            logger.info(f"Отправка ежемесячного отчета по метрикам на {recipient}")
            
            response = await aiosmtplib.send(
                msg,
                hostname=EMAIL_HOST,
                port=EMAIL_PORT,
                start_tls=True,
                username=EMAIL_LOGIN,
                password=EMAIL_PASSWORD,
            )
            
            logger.info(f"Ежемесячный отчет успешно отправлен. SMTP Response: {response}")
            return True
        else:
            logger.error("Email credentials не настроены")
            return False
            
    except aiosmtplib.SMTPException as e:
        logger.error(f"SMTP ошибка при отправке ежемесячного отчета: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Ошибка при отправке ежемесячного отчета: {e}", exc_info=True)
        return False
