import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from html import escape
import logging
from bot.feedback_payload import EmailAttachment
from config import EMAIL_HOST, EMAIL_PORT, EMAIL_LOGIN, EMAIL_PASSWORD, EMAIL_TO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _attach_email_file(message: MIMEMultipart, attachment: EmailAttachment | None) -> None:
    if attachment is None:
        return
    maintype, separator, subtype = attachment.content_type.partition('/')
    if not separator:
        maintype, subtype = "application", "octet-stream"
    part = MIMEBase(maintype, subtype)
    part.set_payload(attachment.data)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=attachment.filename)
    message.attach(part)


def _attach_email_files(
    message: MIMEMultipart,
    attachments: EmailAttachment | list[EmailAttachment] | tuple[EmailAttachment, ...] | None,
) -> None:
    if attachments is None:
        return
    if isinstance(attachments, EmailAttachment):
        attachments = [attachments]
    for attachment in attachments:
        _attach_email_file(message, attachment)


async def send_feedback_email(
    user_data: dict,
    feedback_type: str,
    message: str,
    attachment: EmailAttachment | list[EmailAttachment] | None = None,
    phone: str | None = None,
):
    """Отправка email об обращении пользователя"""
    try:
        type_labels = {
            "suggestion": ("Предложение", "предложение"),
            "complaint": ("Жалоба", "жалоба"),
            "results_request": ("Запрос по результатам", "запрос по результатам"),
        }
        type_text, subject_label = type_labels.get(
            feedback_type,
            ("Обращение", "обращение"),
        )
        
        msg = MIMEMultipart('mixed')
        msg['Subject'] = (
            f'X-LAB VET Assistant — {subject_label} — '
            f'{user_data.get("name", "Неизвестный пользователь")}'
        )
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
        
        phone_html = (
            f'<li><strong>Телефон:</strong> {escape(phone)}</li>'
            if phone
            else ""
        )
        phone_text = f"\n        - Телефон: {phone}" if phone else ""

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
              {phone_html}
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
        - Telegram ID: {user_data.get('telegram_id', 'Не указан')}{phone_text}
        
        Текст обращения:
        {message}
        """
        
        part1 = MIMEText(text, 'plain', 'utf-8')
        part2 = MIMEText(html, 'html', 'utf-8')
        
        body = MIMEMultipart('alternative')
        body.attach(part1)
        body.attach(part2)
        msg.attach(body)
        _attach_email_files(msg, attachment)
        
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

async def send_callback_email(
    user_data: dict,
    phone: str,
    message: str,
    attachment: EmailAttachment | list[EmailAttachment] | None = None,
):
    """Отправка email о заказе обратного звонка"""
    try:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = (
            'X-LAB VET Assistant — заказ звонка — '
            f'{user_data.get("name", "Неизвестный пользователь")}'
        )
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
        
        body = MIMEMultipart('alternative')
        body.attach(part1)
        body.attach(part2)
        msg.attach(body)
        _attach_email_files(msg, attachment)
        
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

def _build_monthly_metrics_email_content(month_name: str, generated_at: datetime = None) -> tuple[str, str]:
    """Builds the monthly metrics email in HTML plus plain-text fallback."""
    generated_at = generated_at or datetime.now()
    safe_month_name = escape(month_name)
    generated_label = generated_at.strftime('%d.%m.%Y %H:%M')

    text = f"""
Ежемесячный отчет по метрикам X-LAB VET
Период: {month_name}
Дата формирования: {generated_label}

Во вложении находится полный Excel-отчет X-LAB VET Assistant за месяц.

Внутри отчета:
- Обзор месяца и ключевые показатели
- Клиентские метрики: DAU, retention, активность пользователей
- Технические метрики: время ответа и производительность
- Метрики качества: успешность обработки запросов и типы взаимодействий
- Детальные данные и инструкции по интерпретации

Данные сохраняются для годовой статистики. Следующий отчет будет отправлен в конце следующего месяца.

Это автоматическое письмо системы метрик X-LAB VET Assistant.
"""

    html = f"""
    <!doctype html>
    <html lang="ru">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ежемесячный отчет по метрикам X-LAB VET</title>
      </head>
      <body style="margin:0; padding:0; background:#edf2f7; color:#172033; font-family:Arial, Helvetica, sans-serif;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="width:100%; background:#edf2f7;">
          <tr>
            <td align="center" style="padding:28px 12px;">
              <table role="presentation" width="640" cellspacing="0" cellpadding="0" border="0" style="width:640px; max-width:100%; background:#ffffff; border-collapse:separate; border-spacing:0; border-radius:18px; overflow:hidden; box-shadow:0 18px 45px rgba(23,32,51,0.12);">
                <tr>
                  <td style="background:#123a5f; padding:30px 34px 26px 34px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="color:#c7f0e5; font-size:12px; line-height:18px; font-weight:bold; letter-spacing:1.5px; text-transform:uppercase;">
                          X-LAB VET Assistant
                        </td>
                        <td align="right" style="color:#d8e9f5; font-size:13px; line-height:18px;">
                          {generated_label}
                        </td>
                      </tr>
                    </table>
                    <h1 style="margin:18px 0 8px 0; color:#ffffff; font-size:30px; line-height:36px; font-weight:700;">
                      Ежемесячный отчет по метрикам
                    </h1>
                    <p style="margin:0; color:#d8e9f5; font-size:17px; line-height:26px;">
                      {safe_month_name}
                    </p>
                  </td>
                </tr>

                <tr>
                  <td style="padding:28px 34px 8px 34px;">
                    <p style="margin:0 0 18px 0; color:#26344d; font-size:16px; line-height:25px;">
                      Во вложении находится полный Excel-отчет по работе X-LAB VET Assistant за месяц. Письмо собрано как короткая обложка: чтобы сразу понять, что внутри файла и зачем его открыть.
                    </p>

                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:separate; border-spacing:0 10px;">
                      <tr>
                        <td style="width:50%; padding:0 5px 0 0;">
                          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f6fbff; border:1px solid #d9e8f5; border-radius:12px;">
                            <tr>
                              <td style="padding:16px;">
                                <div style="color:#497089; font-size:12px; line-height:16px; font-weight:bold; text-transform:uppercase; letter-spacing:0.8px;">Период</div>
                                <div style="margin-top:6px; color:#172033; font-size:20px; line-height:26px; font-weight:700;">{safe_month_name}</div>
                              </td>
                            </tr>
                          </table>
                        </td>
                        <td style="width:50%; padding:0 0 0 5px;">
                          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f7fbf8; border:1px solid #d8eadc; border-radius:12px;">
                            <tr>
                              <td style="padding:16px;">
                                <div style="color:#4d7558; font-size:12px; line-height:16px; font-weight:bold; text-transform:uppercase; letter-spacing:0.8px;">Формат</div>
                                <div style="margin-top:6px; color:#172033; font-size:20px; line-height:26px; font-weight:700;">Excel во вложении</div>
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <tr>
                  <td style="padding:16px 34px 8px 34px;">
                    <h2 style="margin:0 0 14px 0; color:#172033; font-size:20px; line-height:26px; font-weight:700;">
                      Что проверить в отчете
                    </h2>
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding:14px 0; border-top:1px solid #e7edf3;">
                          <div style="color:#172033; font-size:15px; line-height:22px; font-weight:700;">Клиентская активность</div>
                          <div style="color:#5b677a; font-size:14px; line-height:21px;">DAU, retention, сессии и активность пользователей без админского шума.</div>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding:14px 0; border-top:1px solid #e7edf3;">
                          <div style="color:#172033; font-size:15px; line-height:22px; font-weight:700;">Производительность</div>
                          <div style="color:#5b677a; font-size:14px; line-height:21px;">Время ответа, технические метрики и стабильность обработки запросов.</div>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding:14px 0; border-top:1px solid #e7edf3;">
                          <div style="color:#172033; font-size:15px; line-height:22px; font-weight:700;">Качество ответов</div>
                          <div style="color:#5b677a; font-size:14px; line-height:21px;">Успешность, типы взаимодействий, оценки и детальная история для разборов.</div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <tr>
                  <td style="padding:14px 34px 30px 34px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#fff8eb; border:1px solid #f3ddb8; border-radius:12px;">
                      <tr>
                        <td style="padding:16px 18px;">
                          <div style="color:#7a551c; font-size:14px; line-height:21px; font-weight:700;">Данные сохраняются</div>
                          <div style="margin-top:4px; color:#6a5a40; font-size:14px; line-height:21px;">
                            Месячный отчет не очищает историю: накопленные метрики остаются доступными для годовой статистики и сверки динамики.
                          </div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <tr>
                  <td style="background:#f7fafc; padding:20px 34px; border-top:1px solid #e7edf3;">
                    <p style="margin:0; color:#6b7586; font-size:12px; line-height:18px;">
                      Автоматическое письмо системы метрик X-LAB VET Assistant. Если вложение не отображается, проверьте разрешение почтового клиента на файлы .xlsx.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    return text.strip(), html


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
        msg['Subject'] = f'Ежемесячный отчет по метрикам X-LAB VET - {month_name}'
        msg['From'] = EMAIL_LOGIN
        msg['To'] = recipient
        msg['Reply-To'] = EMAIL_LOGIN
        msg['X-Mailer'] = 'Python/aiosmtplib'

        text, html = _build_monthly_metrics_email_content(month_name)
        body = MIMEMultipart('alternative')
        body.attach(MIMEText(text, 'plain', 'utf-8'))
        body.attach(MIMEText(html, 'html', 'utf-8'))
        msg.attach(body)
        
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
