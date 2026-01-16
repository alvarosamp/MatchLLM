from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.ocr.extractor import PDFExtractor


@pytest.mark.integration
def test_datasheet_text_is_not_too_short_and_has_technical_tokens():
    """Regression-ish test on a real product datasheet PDF.

    This is not a strict accuracy test (no ground truth). It's designed to catch
    obvious OCR failures and ensure we extract something useful from a real
    datasheet-like document.
    """

    repo_root = Path(__file__).resolve().parents[1]
    pdf = repo_root / "data" / "produtos" / "Produto36334IdArquivo15589.pdf"
    if not pdf.exists():
        pytest.skip("Produto36334IdArquivo15589.pdf não encontrado no repo")

    ex = PDFExtractor()
    text = ex.extract(str(pdf), log_label="datasheet")

    assert isinstance(text, str)
    t = text.strip()
    assert len(t) > 1500

    # Look for a handful of common technical tokens.
    # We keep this permissive because datasheets vary a lot.
    t_low = t.lower()

    patterns = [
        r"\b(v|volt|volts)\b",
        r"\b(a|amp|amps)\b",
        r"\b(w|watt|watts)\b",
        r"\b(ah|mah)\b",
        r"\b(hz|khz|mhz|ghz)\b",
        r"\b(mm|cm|m|kg|g)\b",
        r"\b(tens[aã]o|corrente|pot[eê]ncia|capacidade|garantia)\b",
    ]

    hits = sum(1 for pat in patterns if re.search(pat, t_low))
    assert hits >= 1
