import sqlite3
from datetime import date, datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

DB_PATH = "expenses.db"

def init_db():
    logger.info("Инициализация базы данных")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            amount REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("PRAGMA table_info(expenses)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'currency' not in columns:
        logger.info("Добавление поля currency в таблицу expenses")
        cursor.execute("ALTER TABLE expenses ADD COLUMN currency TEXT DEFAULT 'RUB'")
        conn.commit()
    
    if 'category' not in columns:
        logger.info("Добавление поля category в таблицу expenses")
        cursor.execute("ALTER TABLE expenses ADD COLUMN category TEXT DEFAULT 'другие'")
        conn.commit()
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована успешно")

def add_expense(amount: float, currency: str = 'RUB', category: str = 'другие', expense_date: Optional[date] = None):
    if expense_date is None:
        expense_date = date.today()
    
    logger.info(f"Добавление расхода: {amount:.2f} {currency} ({category}) на дату {expense_date}")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO expenses (date, amount, currency, category)
            VALUES (?, ?, ?, ?)
        """, (expense_date.isoformat(), amount, currency, category))
        conn.commit()
        conn.close()
        logger.info(f"Расход {amount:.2f} {currency} ({category}) успешно сохранен")
    except Exception as e:
        logger.error(f"Ошибка при сохранении расхода: {str(e)}", exc_info=True)
        raise

def get_expenses_by_date(expense_date: date) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT amount, currency FROM expenses
        WHERE date = ?
    """, (expense_date.isoformat(),))
    results = cursor.fetchall()
    conn.close()
    
    totals = {}
    for amount, currency in results:
        if currency is None:
            currency = 'RUB'
        if currency not in totals:
            totals[currency] = 0.0
        totals[currency] += amount
    return totals

def get_monthly_expenses(year: int, month: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT amount, currency FROM expenses
        WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
    """, (str(year), f"{month:02d}"))
    results = cursor.fetchall()
    conn.close()
    
    totals = {}
    for amount, currency in results:
        if currency is None:
            currency = 'RUB'
        if currency not in totals:
            totals[currency] = 0.0
        totals[currency] += amount
    return totals

def get_today_total() -> dict:
    today = date.today()
    return get_expenses_by_date(today)

def get_month_total() -> dict:
    today = date.today()
    return get_monthly_expenses(today.year, today.month)

