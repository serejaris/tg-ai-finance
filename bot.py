from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN
from storage import init_db, add_expense, get_today_total, get_month_total
from openai_client import transcribe_audio, extract_text_from_image, parse_expense_from_text
from expense_parser import extract_expense, extract_expense_with_category
import base64
import io
import logging

def get_currency_name(currency: str) -> str:
    currency_map = {
        'RUB': 'руб.',
        'ARS': 'песо',
        'USD': 'долл.',
        'EUR': 'евро'
    }
    return currency_map.get(currency.upper(), currency.upper())

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    logger.info(f"Команда /start от пользователя {user_id} (@{username})")
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
    user_id = update.effective_user.id
    logger.info(f"Команда /help от пользователя {user_id}")
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
    user_id = update.effective_user.id
    
    if text.startswith('/'):
        return
    
    logger.info(f"Получено текстовое сообщение от пользователя {user_id}: {text[:100]}")
    
    try:
        amount, currency, category = extract_expense_with_category(text)
        
        if amount > 0:
            add_expense(amount, currency, category)
            today_totals = get_today_total()
            
            currency_name = get_currency_name(currency)
            logger.info(f"Расход {amount:.2f} {currency} ({category}) сохранен для пользователя {user_id}")
            
            summary_lines = [f"Расход {amount:.2f} {currency_name} ({category}) сохранен."]
            if today_totals:
                summary_lines.append("\nВсего за сегодня:")
                for curr, total in today_totals.items():
                    summary_lines.append(f"{total:.2f} {get_currency_name(curr)}")
            
            await update.message.reply_text("\n".join(summary_lines))
        else:
            logger.warning(f"Не удалось извлечь сумму из сообщения пользователя {user_id}: {text[:100]}")
            await update.message.reply_text(
                "Не удалось извлечь сумму расхода из сообщения."
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке текстового сообщения от пользователя {user_id}: {str(e)}", exc_info=True)
        await update.message.reply_text(f"Ошибка при обработке сообщения: {str(e)}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Получено голосовое сообщение от пользователя {user_id}")
    
    voice_file = await context.bot.get_file(update.message.voice.file_id)
    audio_bytes = await voice_file.download_as_bytearray()
    audio_stream = io.BytesIO(audio_bytes)
    audio_stream.name = "voice.ogg"
    
    try:
        transcribed_text = transcribe_audio(audio_stream)
        logger.info(f"Транскрипция голосового сообщения от пользователя {user_id}: {transcribed_text[:100]}")
        amount, currency, category = extract_expense_with_category(transcribed_text)
        
        if amount > 0:
            add_expense(amount, currency, category)
            today_totals = get_today_total()
            
            currency_name = get_currency_name(currency)
            logger.info(f"Расход {amount:.2f} {currency} ({category}) сохранен для пользователя {user_id} из голосового сообщения")
            
            summary_lines = [
                f"Распознано: {transcribed_text}",
                f"Расход {amount:.2f} {currency_name} ({category}) сохранен."
            ]
            if today_totals:
                summary_lines.append("\nВсего за сегодня:")
                for curr, total in today_totals.items():
                    summary_lines.append(f"{total:.2f} {get_currency_name(curr)}")
            
            await update.message.reply_text("\n".join(summary_lines))
        else:
            logger.warning(f"Не удалось извлечь сумму из транскрипции пользователя {user_id}: {transcribed_text[:100]}")
            await update.message.reply_text(
                f"Распознано: {transcribed_text}\n"
                "Не удалось извлечь сумму расхода."
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке голосового сообщения от пользователя {user_id}: {str(e)}", exc_info=True)
        await update.message.reply_text(f"Ошибка при обработке голосового сообщения: {str(e)}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Получено фото от пользователя {user_id}")
    
    photo = update.message.photo[-1]
    photo_file = await context.bot.get_file(photo.file_id)
    image_bytes = await photo_file.download_as_bytearray()
    
    try:
        image_base64 = base64.b64encode(bytes(image_bytes)).decode('utf-8')
        extracted_text = extract_text_from_image(image_base64)
        logger.info(f"Текст из изображения от пользователя {user_id}: {extracted_text[:100]}")
        amount, currency, category = extract_expense_with_category(extracted_text)
        
        if amount > 0:
            add_expense(amount, currency, category)
            today_totals = get_today_total()
            
            currency_name = get_currency_name(currency)
            logger.info(f"Расход {amount:.2f} {currency} ({category}) сохранен для пользователя {user_id} из фото")
            
            summary_lines = [
                f"Прочитано с изображения: {extracted_text}",
                f"Расход {amount:.2f} {currency_name} ({category}) сохранен."
            ]
            if today_totals:
                summary_lines.append("\nВсего за сегодня:")
                for curr, total in today_totals.items():
                    summary_lines.append(f"{total:.2f} {get_currency_name(curr)}")
            
            await update.message.reply_text("\n".join(summary_lines))
        else:
            logger.warning(f"Не удалось извлечь сумму из текста изображения пользователя {user_id}: {extracted_text[:100]}")
            await update.message.reply_text(
                f"Прочитано с изображения: {extracted_text}\n"
                "Не удалось извлечь сумму расхода."
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке изображения от пользователя {user_id}: {str(e)}", exc_info=True)
        await update.message.reply_text(f"Ошибка при обработке изображения: {str(e)}")

async def today_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    totals = get_today_total()
    logger.info(f"Команда /today от пользователя {user_id}")
    
    if totals:
        lines = ["Расходы за сегодня:"]
        for currency, total in totals.items():
            lines.append(f"{total:.2f} {get_currency_name(currency)}")
        message = "\n".join(lines)
    else:
        message = "Расходы за сегодня: 0 руб."
    
    await update.message.reply_text(message)

async def month_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    totals = get_month_total()
    logger.info(f"Команда /month от пользователя {user_id}")
    
    if totals:
        lines = ["Расходы за текущий месяц:"]
        for currency, total in totals.items():
            lines.append(f"{total:.2f} {get_currency_name(currency)}")
        message = "\n".join(lines)
    else:
        message = "Расходы за текущий месяц: 0 руб."
    
    await update.message.reply_text(message)

async def set_bot_commands(application: Application):
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("help", "Показать справку по командам"),
        BotCommand("today", "Показать расходы за сегодня"),
        BotCommand("month", "Показать расходы за текущий месяц")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Меню команд установлено")

def main():
    logger.info("Запуск бота...")
    init_db()
    logger.info("База данных инициализирована")
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(set_bot_commands).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("today", today_summary))
    application.add_handler(CommandHandler("month", month_summary))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    logger.info("Бот запущен и готов к работе")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

