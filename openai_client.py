from openai import OpenAI
from config import OPENAI_API_KEY
import io
import logging

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)

def transcribe_audio(audio_file) -> str:
    logger.info("Запрос транскрипции аудио через Whisper")
    if hasattr(audio_file, 'seek'):
        audio_file.seek(0)
    try:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
        logger.info(f"Транскрипция успешно получена: {transcript.text[:100]}")
        return transcript.text
    except Exception as e:
        logger.error(f"Ошибка при транскрипции аудио: {str(e)}", exc_info=True)
        raise

def extract_text_from_image(image_base64: str) -> str:
    logger.info("Запрос извлечения текста из изображения через GPT-4 Vision")
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Прочитай текст на этом изображении и верни его полностью."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300
        )
        text = response.choices[0].message.content
        logger.info(f"Текст из изображения успешно извлечен: {text[:100]}")
        return text
    except Exception as e:
        logger.error(f"Ошибка при извлечении текста из изображения: {str(e)}", exc_info=True)
        raise

def determine_expense_category(text: str) -> str:
    logger.info(f"Запрос определения категории из текста: {text[:100]}")
    prompt = f"""Определи категорию расхода на основе следующего текста.
Доступные категории: еда, транспорт, развлечения, коммунальные, одежда, здоровье, другие.
Верни только одно слово - название категории на русском языке.
Если категорию определить сложно, используй "другие".

Текст: {text}
Категория:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты помощник для определения категорий расходов. Определяй категорию на основе текста. Всегда возвращай только одно слово из списка: еда, транспорт, развлечения, коммунальные, одежда, здоровье, другие."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=20,
            temperature=0
        )
        
        category = response.choices[0].message.content.strip().lower()
        valid_categories = ['еда', 'транспорт', 'развлечения', 'коммунальные', 'одежда', 'здоровье', 'другие']
        
        if category in valid_categories:
            logger.info(f"Категория успешно определена: {category}")
            return category
        else:
            logger.warning(f"Получена недопустимая категория: {category}, используется 'другие'")
            return 'другие'
    except Exception as e:
        logger.error(f"Ошибка при определении категории: {str(e)}", exc_info=True)
        return 'другие'

def parse_expense_from_text(text: str) -> tuple[float, str]:
    logger.info(f"Запрос парсинга суммы из текста: {text[:100]}")
    prompt = f"""Извлеки сумму расхода и валюту из следующего текста. 
Сумма может быть указана в любой валюте (рубли, песо, доллары, USD, ARS и т.д.).
Понимай словесные формы чисел: "15 тысяч" = 15000, "тысяч" = умножить на 1000, "тыс" = умножить на 1000.
Верни результат в формате: СУММА|ВАЛЮТА
Например: 15000|ARS или 500|руб или 100|USD
Если валюты нет в тексте, используй "ARS" (песо).
Если суммы нет, верни 0|ARS.

Текст: {text}
Результат:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты помощник для извлечения сумм расходов из текста. Извлекай сумму и валюту. Всегда возвращай в формате: СУММА|ВАЛЮТА (например: 15000|ARS или 500|руб). Если валюта не указана, используй ARS (песо) по умолчанию."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50,
            temperature=0
        )
        
        result = response.choices[0].message.content.strip()
        try:
            if '|' in result:
                amount_str, currency = result.split('|', 1)
                amount = float(amount_str.strip())
                currency = currency.strip().upper()
                if currency in ['RUB', 'РУБ', 'РУБЛЕЙ', 'РУБЛЯ', 'РУБЛЬ']:
                    currency = 'RUB'
                elif currency in ['ARS', 'ПЕСО']:
                    currency = 'ARS'
                elif currency in ['USD', 'ДОЛЛАР', 'ДОЛЛАРОВ', 'ДОЛЛАРА', '$']:
                    currency = 'USD'
                else:
                    currency = currency[:3].upper()
                logger.info(f"Сумма и валюта успешно извлечены: {amount} {currency}")
                return (max(0, amount), currency)
            else:
                amount = float(result)
                logger.warning(f"Валюту не удалось извлечь, используется ARS по умолчанию")
                return (max(0, amount), 'ARS')
        except ValueError:
            logger.warning(f"Не удалось преобразовать результат: {result}")
            return (0.0, 'ARS')
    except Exception as e:
        logger.error(f"Ошибка при парсинге суммы из текста: {str(e)}", exc_info=True)
        return (0.0, 'ARS')

