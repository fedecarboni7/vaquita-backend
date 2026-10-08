import re


def _parse_decimal_string(value: str) -> float | None:
    cleaned = value.strip()
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        decimal_sep = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        cleaned = cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "." in cleaned:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", cleaned):
            cleaned = cleaned.replace(".", "")
        else:
            cleaned = cleaned.replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_amount_text(text: str | None) -> float | None:
    """Parse es-AR amounts, including words and common multipliers.

    Rules: if both . and , are present, the last one is the decimal separator; if only . is
    present it is treated as a thousands separator when it matches 1-3 digits groups, otherwise
    as a decimal separator; if only , is present it is treated as a decimal separator.
    """
    if text is None:
        return None

    value = str(text).strip()
    if not value:
        return None

    value = value.replace("US$", "").replace("USD", "").replace("ARS", "")
    value = value.replace("$", "").replace("pesos", "").replace("dólares", "").replace("dolares", "")
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return None

    multipliers = {
        "k": 1000,
        "mil": 1000,
        "luca": 1000,
        "lucas": 1000,
        "palo": 1000000,
        "palos": 1000000,
        "millón": 1000000,
        "millon": 1000000,
        "millones": 1000000,
    }

    match = re.fullmatch(r"(?i)(?:un|una)?\s*(k|mil|luca|lucas|palo|palos|millón|millon|millones)", value)
    if match:
        amount = 1.0
        multiplier = match.group(1).lower()
        value = f"{amount * multipliers[multiplier]:.0f}"

    numeric_match = re.fullmatch(
        r"(?i)(?:[\d.,]+)\s*(k|mil|luca|lucas|palo|palos|millón|millon|millones)?",
        value,
    )
    if numeric_match:
        number_part = numeric_match.group(0).strip()
        multiplier = None
        for word in sorted(multipliers, key=len, reverse=True):
            if re.search(rf"(?i){re.escape(word)}$", number_part):
                multiplier = word
                number_part = re.sub(rf"(?i)\s*{re.escape(word)}$", "", number_part).strip()
                break
        parsed = _parse_decimal_string(number_part)
        if parsed is None:
            return None
        if multiplier:
            parsed *= multipliers[multiplier.lower()]
        if parsed <= 0:
            return None
        return round(parsed, 2)

    parsed = _parse_decimal_string(value)
    if parsed is None or parsed <= 0:
        return None
    return round(parsed, 2)
