def nan_ratio(specs: dict) -> float:
    total = len(specs)
    empty = sum(1 for v in specs.values() if v in (None, "N/A", False))
    return empty / max(total, 1)


def extract_with_fallback(text: str, llm_client=None) -> dict:
    from core.ocr.spec_parser import extract_specs

    specs = extract_specs(text)

    # Fallback via Gemini removido: mantemos apenas parsing local.
    # Se quiser melhorar a extração, ajuste o parser/heurísticas locais.
    if nan_ratio(specs) > 0.4:
        return specs

    return specs
