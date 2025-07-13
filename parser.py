from telegram import Update
from telegram.ext import Application, MessageHandler, filters

async def get_file_id(update: Update, context):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        await update.message.reply_text(f"Photo file_id: {file_id}")
    elif update.message.document:
        file_id = update.message.document.file_id
        await update.message.reply_text(f"Document file_id: {file_id}")

app = Application.builder().token("8136766001:AAGKhc5s3yWEvYsNP9MFuC2LSZntFQSlDQg").build()
app.add_handler(MessageHandler(filters.ALL, get_file_id))
app.run_polling()