from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from config import TELEGRAM_BOT_TOKEN
from storage import init_db, add_expense, get_today_total, get_month_total, convert_currency, get_user_settings, set_display_currency, set_exchange_rate
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

def format_amount(amount: float) -> str:
    if amount == int(amount):
        formatted = str(int(amount))
    else:
        formatted = f"{amount:.2f}".rstrip('0').rstrip('.')
    
    parts = formatted.split('.')
    integer_part = parts[0]
    
    if len(integer_part) > 3:
        result = []
        for i in range(len(integer_part) - 1, -1, -1):
            result.append(integer_part[i])
            if (len(integer_part) - i) % 3 == 0 and i > 0:
                result.append(' ')
        integer_part = ''.join(reversed(result))
    
    if len(parts) > 1:
        return f"{integer_part}.{parts[1]}"
    return integer_part

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
        "/settings - настройки валюты отображения\n"
        "/setrate - установить курс валюты\n"
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
            currency_name = get_currency_name(currency)
            settings = get_user_settings(user_id)
            display_currency = settings['display_currency']
            display_currency_name = get_currency_name(display_currency)
            
            if currency == display_currency:
                preview_text = f"Расход {amount:.2f} {currency_name} в категории {category}"
            else:
                converted_amount = convert_currency(amount, currency, user_id)
                preview_text = f"Расход {amount:.2f} {currency_name} ({converted_amount:.2f} {display_currency_name}) в категории {category}"
            
            context.user_data['pending_expense'] = {
                'amount': amount,
                'currency': currency,
                'category': category,
                'source_type': 'text'
            }
            
            keyboard = [
                [
                    InlineKeyboardButton("Подтвердить", callback_data="confirm_expense"),
                    InlineKeyboardButton("Отменить", callback_data="cancel_expense")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"{preview_text}\n\nПодтвердите сохранение расхода:",
                reply_markup=reply_markup
            )
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
            currency_name = get_currency_name(currency)
            settings = get_user_settings(user_id)
            display_currency = settings['display_currency']
            display_currency_name = get_currency_name(display_currency)
            
            if currency == display_currency:
                preview_text = f"Распознано: {transcribed_text}\nРасход {amount:.2f} {currency_name} в категории {category}"
            else:
                converted_amount = convert_currency(amount, currency, user_id)
                preview_text = f"Распознано: {transcribed_text}\nРасход {amount:.2f} {currency_name} ({converted_amount:.2f} {display_currency_name}) в категории {category}"
            
            context.user_data['pending_expense'] = {
                'amount': amount,
                'currency': currency,
                'category': category,
                'source_type': 'voice',
                'transcribed_text': transcribed_text
            }
            
            keyboard = [
                [
                    InlineKeyboardButton("Подтвердить", callback_data="confirm_expense"),
                    InlineKeyboardButton("Отменить", callback_data="cancel_expense")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"{preview_text}\n\nПодтвердите сохранение расхода:",
                reply_markup=reply_markup
            )
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
            currency_name = get_currency_name(currency)
            settings = get_user_settings(user_id)
            display_currency = settings['display_currency']
            display_currency_name = get_currency_name(display_currency)
            
            if currency == display_currency:
                preview_text = f"Прочитано с изображения: {extracted_text}\nРасход {amount:.2f} {currency_name} в категории {category}"
            else:
                converted_amount = convert_currency(amount, currency, user_id)
                preview_text = f"Прочитано с изображения: {extracted_text}\nРасход {amount:.2f} {currency_name} ({converted_amount:.2f} {display_currency_name}) в категории {category}"
            
            context.user_data['pending_expense'] = {
                'amount': amount,
                'currency': currency,
                'category': category,
                'source_type': 'photo',
                'extracted_text': extracted_text
            }
            
            keyboard = [
                [
                    InlineKeyboardButton("Подтвердить", callback_data="confirm_expense"),
                    InlineKeyboardButton("Отменить", callback_data="cancel_expense")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"{preview_text}\n\nПодтвердите сохранение расхода:",
                reply_markup=reply_markup
            )
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
    totals = get_today_total(user_id)
    logger.info(f"Команда /today от пользователя {user_id}")
    
    settings = get_user_settings(user_id)
    display_currency = settings['display_currency']
    display_currency_name = get_currency_name(display_currency)
    
    if totals:
        lines = ["<b>Расходы за сегодня:</b>"]
        category_names = {
            'еда': '🍔 Еда',
            'транспорт': '🚗 Транспорт',
            'развлечения': '🎬 Развлечения',
            'коммунальные': '🏠 Коммунальные',
            'одежда': '👕 Одежда',
            'здоровье': '💊 Здоровье',
            'другие': '📦 Другие'
        }
        for category, total in sorted(totals.items()):
            cat_name = category_names.get(category, category.capitalize())
            formatted_amount = format_amount(total)
            lines.append(f"{cat_name}: {formatted_amount} {display_currency_name}")
        message = "\n".join(lines)
    else:
        message = f"<b>Расходы за сегодня:</b>\n0 {display_currency_name}"
    
    await update.message.reply_text(message, parse_mode='HTML')

async def month_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    totals = get_month_total(user_id)
    logger.info(f"Команда /month от пользователя {user_id}")
    
    settings = get_user_settings(user_id)
    display_currency = settings['display_currency']
    display_currency_name = get_currency_name(display_currency)
    
    if totals:
        lines = ["<b>Расходы за текущий месяц:</b>"]
        category_names = {
            'еда': '🍔 Еда',
            'транспорт': '🚗 Транспорт',
            'развлечения': '🎬 Развлечения',
            'коммунальные': '🏠 Коммунальные',
            'одежда': '👕 Одежда',
            'здоровье': '💊 Здоровье',
            'другие': '📦 Другие'
        }
        for category, total in sorted(totals.items()):
            cat_name = category_names.get(category, category.capitalize())
            formatted_amount = format_amount(total)
            lines.append(f"{cat_name}: {formatted_amount} {display_currency_name}")
        message = "\n".join(lines)
    else:
        message = f"<b>Расходы за текущий месяц:</b>\n0 {display_currency_name}"
    
    await update.message.reply_text(message, parse_mode='HTML')

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Команда /settings от пользователя {user_id}")
    
    settings = get_user_settings(user_id)
    display_currency = settings['display_currency']
    
    keyboard = [
        [
            InlineKeyboardButton("ARS (песо)" + (" ✓" if display_currency == 'ARS' else ""), callback_data="currency_ARS"),
            InlineKeyboardButton("USD (долл.)" + (" ✓" if display_currency == 'USD' else ""), callback_data="currency_USD"),
            InlineKeyboardButton("RUB (руб.)" + (" ✓" if display_currency == 'RUB' else ""), callback_data="currency_RUB")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    settings_text = f"Ваша валюта отображения: {get_currency_name(display_currency)}\n\n"
    settings_text += "Выберите валюту для отображения:\n\n"
    settings_text += "Для установки курсов используйте команду /setrate\n"
    settings_text += "Формат: /setrate USD 1000 (1 USD = 1000 ARS)"
    
    await update.message.reply_text(settings_text, reply_markup=reply_markup)

async def expense_confirmation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if 'pending_expense' not in context.user_data:
        await query.answer("Расход не найден. Попробуйте снова.")
        await query.edit_message_text("Расход не найден. Попробуйте отправить расход снова.")
        return
    
    pending = context.user_data['pending_expense']
    
    if query.data == "confirm_expense":
        await query.answer()
        
        amount = pending['amount']
        currency = pending['currency']
        category = pending['category']
        
        add_expense(amount, currency, category, user_id)
        today_totals = get_today_total(user_id)
        
        currency_name = get_currency_name(currency)
        settings = get_user_settings(user_id)
        display_currency = settings['display_currency']
        display_currency_name = get_currency_name(display_currency)
        
        if currency == display_currency:
            summary_lines = [f"Расход {amount:.2f} {currency_name} в категории {category} сохранен."]
        else:
            converted_amount = convert_currency(amount, currency, user_id)
            summary_lines = [f"Расход {amount:.2f} {currency_name} ({converted_amount:.2f} {display_currency_name}) в категории {category} сохранен."]
        
        if today_totals:
            total_display = sum(today_totals.values())
            summary_lines.append(f"\nВсего за сегодня: {total_display:.2f} {display_currency_name}")
        
        del context.user_data['pending_expense']
        
        await query.edit_message_text("\n".join(summary_lines))
        logger.info(f"Расход {amount:.2f} {currency} ({category}) сохранен для пользователя {user_id}")
        
    elif query.data == "cancel_expense":
        await query.answer("Расход отменен")
        del context.user_data['pending_expense']
        await query.edit_message_text("Сохранение расхода отменено.")
        logger.info(f"Сохранение расхода отменено пользователем {user_id}")

async def currency_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    currency = query.data.split('_')[1]
    
    logger.info(f"Изменение валюты отображения для пользователя {user_id} на {currency}")
    set_display_currency(user_id, currency)
    
    settings = get_user_settings(user_id)
    display_currency = settings['display_currency']
    
    keyboard = [
        [
            InlineKeyboardButton("ARS (песо)" + (" ✓" if display_currency == 'ARS' else ""), callback_data="currency_ARS"),
            InlineKeyboardButton("USD (долл.)" + (" ✓" if display_currency == 'USD' else ""), callback_data="currency_USD"),
            InlineKeyboardButton("RUB (руб.)" + (" ✓" if display_currency == 'RUB' else ""), callback_data="currency_RUB")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    settings_text = f"Ваша валюта отображения: {get_currency_name(display_currency)}\n\n"
    settings_text += "Выберите валюту для отображения:\n\n"
    settings_text += "Для установки курсов используйте команду /setrate\n"
    settings_text += "Формат: /setrate USD 1000 (1 USD = 1000 ARS)"
    
    await query.edit_message_text(settings_text, reply_markup=reply_markup)

async def setrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Команда /setrate от пользователя {user_id}")
    
    if not context.args or len(context.args) != 2:
        await update.message.reply_text(
            "Неправильный формат команды.\n\n"
            "Используйте: /setrate <CURRENCY> <RATE>\n\n"
            "Примеры:\n"
            "/setrate USD 1000\n"
            "/setrate RUB 10"
        )
        return
    
    currency = context.args[0].upper()
    try:
        rate = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Курс должен быть числом.")
        return
    
    if currency not in ['USD', 'RUB']:
        await update.message.reply_text("Поддерживаются только USD и RUB.")
        return
    
    set_exchange_rate(user_id, currency, 'ARS', rate)
    currency_name = get_currency_name(currency)
    await update.message.reply_text(f"Курс установлен: 1 {currency_name} = {rate:.2f} песо")

async def set_bot_commands(application: Application):
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("help", "Показать справку по командам"),
        BotCommand("today", "Показать расходы за сегодня"),
        BotCommand("month", "Показать расходы за текущий месяц"),
        BotCommand("settings", "Настройки валюты отображения"),
        BotCommand("setrate", "Установить курс валюты")
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
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("setrate", setrate_command))
    application.add_handler(CallbackQueryHandler(expense_confirmation_callback, pattern="^(confirm_expense|cancel_expense)$"))
    application.add_handler(CallbackQueryHandler(currency_callback, pattern="currency_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    logger.info("Бот запущен и готов к работе")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

