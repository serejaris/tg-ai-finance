import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, datetime
from typing import Optional
import logging
import requests
import os

from config import DATABASE_URL

logger = logging.getLogger(__name__)

_exchange_rates = None

def get_exchange_rates():
    global _exchange_rates
    if _exchange_rates is not None:
        return _exchange_rates
    
    logger.info("Запрос актуальных курсов валют")
    try:
        response = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        if response.status_code == 200:
            data = response.json()
            _exchange_rates = {
                'USD': 1.0,
                'ARS': data['rates']['ARS'],
                'RUB': data['rates']['RUB'],
                'EUR': data['rates']['EUR']
            }
            logger.info(f"Курсы валют получены: {_exchange_rates}")
            return _exchange_rates
        else:
            logger.error(f"Ошибка получения курсов: код {response.status_code}")
            _exchange_rates = {
                'USD': 1.0,
                'ARS': 900.0,
                'RUB': 90.0,
                'EUR': 1.1
            }
            logger.info(f"Используются резервные курсы: {_exchange_rates}")
            return _exchange_rates
    except Exception as e:
        logger.error(f"Ошибка при получении курсов валют: {str(e)}", exc_info=True)
        _exchange_rates = {
            'USD': 1.0,
            'ARS': 900.0,
            'RUB': 90.0,
            'EUR': 1.1
        }
        logger.info(f"Используются резервные курсы: {_exchange_rates}")
        return _exchange_rates

def convert_to_ars(amount: float, currency: str) -> float:
    if currency == 'ARS':
        return amount
    
    rates = get_exchange_rates()
    
    if currency not in rates:
        logger.warning(f"Неизвестная валюта {currency}, используется ARS напрямую")
        return amount
    
    if currency == 'USD':
        return amount * rates['ARS']
    else:
        usd_amount = amount / rates[currency]
        return usd_amount * rates['ARS']

def convert_currency(amount: float, from_currency: str, user_id: int, to_currency: str = None) -> float:
    settings = get_user_settings(user_id)
    
    if to_currency is None:
        to_currency = settings['display_currency']
    
    if from_currency == to_currency:
        return amount
    
    ars_amount = None
    
    if from_currency == 'ARS':
        ars_amount = amount
    elif from_currency == 'USD':
        if settings['usd_to_ars_rate']:
            ars_amount = amount * settings['usd_to_ars_rate']
        else:
            rates = get_exchange_rates()
            ars_amount = amount * rates['ARS']
    elif from_currency == 'RUB':
        if settings['rub_to_ars_rate']:
            ars_amount = amount * settings['rub_to_ars_rate']
        else:
            rates = get_exchange_rates()
            ars_amount = amount * (rates['ARS'] / rates['RUB'])
    else:
        logger.warning(f"Неизвестная валюта {from_currency}, используется ARS напрямую")
        ars_amount = amount
    
    if to_currency == 'ARS':
        return ars_amount
    elif to_currency == 'USD':
        if settings['usd_to_ars_rate']:
            return ars_amount / settings['usd_to_ars_rate']
        else:
            rates = get_exchange_rates()
            return ars_amount / rates['ARS']
    elif to_currency == 'RUB':
        if settings['rub_to_ars_rate']:
            return ars_amount / settings['rub_to_ars_rate']
        else:
            rates = get_exchange_rates()
            return ars_amount * (rates['RUB'] / rates['ARS'])
    
    return ars_amount

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def init_user_settings_table():
    logger.info("Инициализация таблицы настроек пользователей")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            display_currency TEXT DEFAULT 'ARS',
            usd_to_ars_rate REAL DEFAULT NULL,
            rub_to_ars_rate REAL DEFAULT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Таблица настроек пользователей инициализирована")

def init_db():
    logger.info("Инициализация базы данных")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            amount REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='expenses'
    """)
    columns = [row[0] for row in cursor.fetchall()]
    
    if 'currency' not in columns:
        logger.info("Добавление поля currency в таблицу expenses")
        cursor.execute("ALTER TABLE expenses ADD COLUMN currency TEXT DEFAULT 'RUB'")
        conn.commit()
    
    if 'category' not in columns:
        logger.info("Добавление поля category в таблицу expenses")
        cursor.execute("ALTER TABLE expenses ADD COLUMN category TEXT DEFAULT 'другие'")
        conn.commit()
    
    conn.close()
    
    init_user_settings_table()
    logger.info("База данных инициализирована успешно")

def add_expense(amount: float, currency: str = 'RUB', category: str = 'другие', expense_date: Optional[date] = None):
    if expense_date is None:
        expense_date = date.today()
    
    logger.info(f"Добавление расхода: {amount:.2f} {currency} ({category}) на дату {expense_date}")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO expenses (date, amount, currency, category)
            VALUES (%s, %s, %s, %s)
        """, (expense_date.isoformat(), amount, currency, category))
        conn.commit()
        conn.close()
        logger.info(f"Расход {amount:.2f} {currency} ({category}) успешно сохранен")
    except Exception as e:
        logger.error(f"Ошибка при сохранении расхода: {str(e)}", exc_info=True)
        raise

def get_expenses_by_date(expense_date: date, user_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT amount, currency, category FROM expenses
        WHERE date = %s
    """, (expense_date.isoformat(),))
    results = cursor.fetchall()
    conn.close()
    
    totals = {}
    for amount, currency, category in results:
        if currency is None:
            currency = 'RUB'
        if category is None:
            category = 'другие'
        
        converted_amount = convert_currency(amount, currency, user_id)
        
        if category not in totals:
            totals[category] = 0.0
        totals[category] += converted_amount
    return totals

def get_monthly_expenses(year: int, month: int, user_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT amount, currency, category FROM expenses
        WHERE EXTRACT(YEAR FROM date) = %s AND EXTRACT(MONTH FROM date) = %s
    """, (year, month))
    results = cursor.fetchall()
    conn.close()
    
    totals = {}
    for amount, currency, category in results:
        if currency is None:
            currency = 'RUB'
        if category is None:
            category = 'другие'
        
        converted_amount = convert_currency(amount, currency, user_id)
        
        if category not in totals:
            totals[category] = 0.0
        totals[category] += converted_amount
    return totals

def get_today_total(user_id: int) -> dict:
    today = date.today()
    return get_expenses_by_date(today, user_id)

def get_month_total(user_id: int) -> dict:
    today = date.today()
    return get_monthly_expenses(today.year, today.month, user_id)

def get_user_settings(user_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT display_currency, usd_to_ars_rate, rub_to_ars_rate
        FROM user_settings
        WHERE user_id = %s
    """, (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'display_currency': result[0],
            'usd_to_ars_rate': result[1],
            'rub_to_ars_rate': result[2]
        }
    else:
        return {
            'display_currency': 'ARS',
            'usd_to_ars_rate': None,
            'rub_to_ars_rate': None
        }

def set_display_currency(user_id: int, currency: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_settings (user_id, display_currency)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET display_currency = %s
    """, (user_id, currency, currency))
    conn.commit()
    conn.close()
    logger.info(f"Установлена валюта отображения для пользователя {user_id}: {currency}")

def set_exchange_rate(user_id: int, from_currency: str, to_currency: str, rate: float):
    conn = get_connection()
    cursor = conn.cursor()
    
    if from_currency == 'USD' and to_currency == 'ARS':
        cursor.execute("""
            INSERT INTO user_settings (user_id, usd_to_ars_rate)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET usd_to_ars_rate = %s
        """, (user_id, rate, rate))
    elif from_currency == 'RUB' and to_currency == 'ARS':
        cursor.execute("""
            INSERT INTO user_settings (user_id, rub_to_ars_rate)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET rub_to_ars_rate = %s
        """, (user_id, rate, rate))
    else:
        logger.warning(f"Неподдерживаемый курс: {from_currency} -> {to_currency}")
        conn.close()
        return
    
    conn.commit()
    conn.close()
    logger.info(f"Установлен курс для пользователя {user_id}: 1 {from_currency} = {rate} {to_currency}")

