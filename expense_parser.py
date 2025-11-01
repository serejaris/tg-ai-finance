from openai_client import parse_expense_from_text

def extract_expense(text: str) -> float:
    amount = parse_expense_from_text(text)
    return amount

