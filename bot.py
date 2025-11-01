from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN
from storage import init_db, add_expense, get_today_total, get_month_total
from openai_client import transcribe_audio, extract_text_from_image, parse_expense_from_text
from expense_parser import extract_expense
import base64
import io

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для учета расходов.\n\n"
        "Отправь мне сообщение с расходом (текст, голос или фото чека),\n"
        "и я сохраню его автоматически.\n\n"
        "Команды:\n"
        "/today - расходы за сегодня\n"
        "/month - расходы за месяц\n"
        "/help - справка"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "/today - показать сумму расходов за сегодня\n"
        "/month - показать сумму расходов за текущий месяц\n"
        "/help - эта справка\n\n"
        "Также можно просто отправлять сообщения с расходами:\n"
        "- Текстовое сообщение\n"
        "- Голосовое сообщение\n"
        "- Фото чека или скриншота"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text.startswith('/'):
        return
    
    try:
        amount = extract_expense(text)
        
        if amount > 0:
            add_expense(amount)
            today_total = get_today_total()
            await update.message.reply_text(
                f"Расход {amount:.2f} руб. сохранен.\n"
                f"Всего за сегодня: {today_total:.2f} руб."
            )
        else:
            await update.message.reply_text(
                "Не удалось извлечь сумму расхода из сообщения."
            )
    except Exception as e:
        await update.message.reply_text(f"Ошибка при обработке сообщения: {str(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice_file = await context.bot.get_file(update.message.voice.file_id)
    audio_bytes = await voice_file.download_as_bytearray()
    audio_stream = io.BytesIO(audio_bytes)
    audio_stream.name = "voice.ogg"
    
    try:
        transcribed_text = transcribe_audio(audio_stream)
        amount = extract_expense(transcribed_text)
        
        if amount > 0:
            add_expense(amount)
            today_total = get_today_total()
            await update.message.reply_text(
                f"Распознано: {transcribed_text}\n"
                f"Расход {amount:.2f} руб. сохранен.\n"
                f"Всего за сегодня: {today_total:.2f} руб."
            )
        else:
            await update.message.reply_text(
                f"Распознано: {transcribed_text}\n"
                "Не удалось извлечь сумму расхода."
            )
    except Exception as e:
        await update.message.reply_text(f"Ошибка при обработке голосового сообщения: {str(e)}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    photo_file = await context.bot.get_file(photo.file_id)
    image_bytes = await photo_file.download_as_bytearray()
    
    try:
        image_base64 = base64.b64encode(bytes(image_bytes)).decode('utf-8')
        extracted_text = extract_text_from_image(image_base64)
        amount = extract_expense(extracted_text)
        
        if amount > 0:
            add_expense(amount)
            today_total = get_today_total()
            await update.message.reply_text(
                f"Прочитано с изображения: {extracted_text}\n"
                f"Расход {amount:.2f} руб. сохранен.\n"
                f"Всего за сегодня: {today_total:.2f} руб."
            )
        else:
            await update.message.reply_text(
                f"Прочитано с изображения: {extracted_text}\n"
                "Не удалось извлечь сумму расхода."
            )
    except Exception as e:
        await update.message.reply_text(f"Ошибка при обработке изображения: {str(e)}")

async def today_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = get_today_total()
    await update.message.reply_text(
        f"Расходы за сегодня: {total:.2f} руб."
    )

async def month_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = get_month_total()
    await update.message.reply_text(
        f"Расходы за текущий месяц: {total:.2f} руб."
    )

def main():
    init_db()
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("today", today_summary))
    application.add_handler(CommandHandler("month", month_summary))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

