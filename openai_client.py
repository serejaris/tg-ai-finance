from openai import OpenAI
from config import OPENAI_API_KEY
import io

client = OpenAI(api_key=OPENAI_API_KEY)

def transcribe_audio(audio_file) -> str:
    if hasattr(audio_file, 'seek'):
        audio_file.seek(0)
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file
    )
    return transcript.text

def extract_text_from_image(image_base64: str) -> str:
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
    return response.choices[0].message.content

def parse_expense_from_text(text: str) -> float:
    prompt = f"""Извлеки сумму расхода из следующего текста. 
Верни только число (сумму в рублях), без дополнительного текста. 
Если суммы нет, верни 0.

Текст: {text}
Сумма:"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Ты помощник для извлечения сумм расходов из текста. Всегда возвращай только число."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=50,
        temperature=0
    )
    
    result = response.choices[0].message.content.strip()
    try:
        amount = float(result)
        return max(0, amount)
    except ValueError:
        return 0.0

