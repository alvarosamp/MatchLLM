import re


def extract_specs(text: str) -> dict:
    specs = {
        "tensao_v": None,
        "corrente_a": None,
        "potencia_w": None,
        "poe": False,
        "portas": None,
        "grau_ip": None,
    }

    patterns = {
        "tensao_v": r"(\d{1,3})\s?V",
        "corrente_a": r"(\d+(\.\d+)?)\s?A",
        "potencia_w": r"(\d+(\.\d+)?)\s?W",
        "portas": r"(\d{1,2})\s?(ports|portas)",
        "grau_ip": r"IP\s?\d{2}",
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            specs[key] = m.group(0)

    specs["poe"] = "poe" in text.lower()
    return specs
