from __future__ import annotations

from pathlib import Path

import pytest

from core.ocr.extractor import PDFExtractor


@pytest.mark.integration
def test_paddleocr_runs_on_repo_editais_and_produtos():
    """Sanity test: ensures we can run OCR on at least one repo PDF.

    This is intentionally lightweight and does NOT assert exact text.
    It validates:
      - no crash
      - returns non-empty string
      - method recorded as paddleocr/native/doctr depending on PDF type

    Skips if PDFs are missing.
    """

    repo_root = Path(__file__).resolve().parents[1]
    edital_dir = repo_root / "data" / "editais"
    prod_dir = repo_root / "data" / "produtos"

    pdfs = []
    if edital_dir.exists():
        pdfs += sorted(edital_dir.glob("*.pdf"))
    if prod_dir.exists():
        pdfs += sorted(prod_dir.glob("*.pdf"))

    if not pdfs:
        pytest.skip("Nenhum PDF em data/editais ou data/produtos")

    extractor = PDFExtractor()

    # Always test the known product datasheet if present (common real-world doc type)
    preferred = repo_root / "data" / "produtos" / "Produto36334IdArquivo15589.pdf"
    to_test = []
    if preferred.exists():
        to_test.append(preferred)

    # add a couple more PDFs to keep runtime bounded
    for p in pdfs:
        if p in to_test:
            continue
        to_test.append(p)
        if len(to_test) >= 3:
            break

    for pdf in to_test:
        text = extractor.extract(str(pdf), log_label=pdf.stem[:16])
        assert isinstance(text, str)
        assert len(text.strip()) > 0
        assert extractor.last_meta.get("method") in ("native", "paddleocr", "doctr", "paddleocr_low_quality")
