"""Независимая от Telegram логика для тестирования."""
import re


def normalize_phone(raw: str | None) -> str | None:
    """Разрешает цифры, пробелы, скобки и дефисы; 10–15 цифр."""
    if not raw:
        return None
    raw = raw.strip()
    if not re.fullmatch(r"\+?[\d\s()\-]+", raw):
        return None
    digits = re.sub(r"\D", "", raw)
    if not 10 <= len(digits) <= 15:
        return None
    return ("+" if raw.startswith("+") else "") + digits


def clean_name(raw: str | None) -> str | None:
    if not raw:
        return None
    name = " ".join(raw.split())
    return name if 2 <= len(name) <= 80 else None


def clean_description(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    return text if 10 <= len(text) <= 2000 else None
