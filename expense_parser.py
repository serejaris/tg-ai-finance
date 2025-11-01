from openai_client import parse_expense_from_text, determine_expense_category

def extract_expense(text: str) -> tuple[float, str]:
    amount, currency = parse_expense_from_text(text)
    return (amount, currency)

def extract_expense_with_category(text: str) -> tuple[float, str, str]:
    amount, currency = parse_expense_from_text(text)
    category = determine_expense_category(text)
    return (amount, currency, category)

