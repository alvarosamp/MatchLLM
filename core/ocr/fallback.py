def nan_ratio(specs: dict) -> float:
    total = len(specs)
    empty = sum(1 for v in specs.values() if v in (None, "N/A", False))
    return empty / max(total, 1)


def extract_with_fallback(text: str, gemini_client) -> dict:
    from core.ocr.spec_parser import extract_specs

    specs = extract_specs(text)

    if nan_ratio(specs) > 0.4:
        specs = gemini_client.extract_specs(text)

    return specs
