from __future__ import annotations

from pathlib import Path

import pytest

from teste.test_paddleocr_metrics import cer, wer


@pytest.mark.integration
def test_paddleocr_extracts_reasonable_text_from_fixture():
    """Integration-ish test.

    This test is skipped unless a fixture exists and PaddleOCR deps are installed.
    Add your own fixtures:
      - teste/fixtures/ocr_samples/sample1.pdf
      - teste/fixtures/ocr_samples/sample1.txt  (ground truth)

    Keep the PDF small (1-2 pages) to avoid slow CI.
    """

    pdf = Path(__file__).parent / "fixtures" / "ocr_samples" / "sample1.pdf"
    gt = Path(__file__).parent / "fixtures" / "ocr_samples" / "sample1.txt"

    if not pdf.exists() or not gt.exists():
        pytest.skip("Fixture sample1.pdf/sample1.txt não encontrado.")

    try:
        from PaddleOCr.paddle_ocr_extractor import PaddleOCRExtractor
    except Exception:
        pytest.skip("PaddleOCR não instalado/configurado neste ambiente.")

    ex = PaddleOCRExtractor()
    text = ex.extract_pdf_text(pdf)

    ref = gt.read_text(encoding="utf-8")

    # Thresholds: tune after you add your fixtures.
    # Start permissive to avoid false failures; tighten once you have signal.
    assert cer(ref, text) <= 0.35
    assert wer(ref, text) <= 0.55
