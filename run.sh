#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Создание виртуального окружения через uv..."
    uv venv
fi

source .venv/bin/activate

echo "Установка зависимостей через uv..."
uv pip install -r requirements.txt

python bot.py

