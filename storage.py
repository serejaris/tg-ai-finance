import sqlite3
from datetime import date, datetime
from typing import Optional

DB_PATH = "expenses.db"

def init_db():
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
    conn.commit()
    conn.close()

def add_expense(amount: float, expense_date: Optional[date] = None):
    if expense_date is None:
        expense_date = date.today()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO expenses (date, amount)
        VALUES (?, ?)
    """, (expense_date.isoformat(), amount))
    conn.commit()
    conn.close()

def get_expenses_by_date(expense_date: date) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT amount FROM expenses
        WHERE date = ?
    """, (expense_date.isoformat(),))
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]

def get_monthly_expenses(year: int, month: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT amount FROM expenses
        WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
    """, (str(year), f"{month:02d}"))
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]

def get_today_total() -> float:
    today = date.today()
    expenses = get_expenses_by_date(today)
    return sum(expenses)

def get_month_total() -> float:
    today = date.today()
    expenses = get_monthly_expenses(today.year, today.month)
    return sum(expenses)

