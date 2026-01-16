from __future__ import annotations

from pathlib import Path

import pytest

from core.ocr.extractor import PDFExtractor


@pytest.mark.integration
def test_edital_text_is_not_too_short():
    """Regression-ish test on a real edital PDF.

    We don't validate exact content, but we want to catch cases where OCR returns
    almost nothing (common when PDF->image conversion or OCR breaks).
    """

    repo_root = Path(__file__).resolve().parents[1]
    pdf = repo_root / "data" / "editais" / "Edital_silverania.pdf"
    if not pdf.exists():
        pytest.skip("Edital_silverania.pdf não encontrado no repo")

    ex = PDFExtractor()
    text = ex.extract(str(pdf), log_label="edital")

    # Very conservative thresholds: just ensure it's not empty/garbage.
    assert isinstance(text, str)
    assert len(text.strip()) > 2000
