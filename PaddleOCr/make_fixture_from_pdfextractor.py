from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ocr.extractor import PDFExtractor


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Gera fixtures de OCR para teste CER/WER usando o PDFExtractor do projeto.\n"
            "Use isso para criar um baseline .txt e depois revisar manualmente para virar ground truth." 
        )
    )
    p.add_argument("pdf", type=str, help="Caminho do PDF de entrada")
    p.add_argument("--out-dir", type=str, default="teste/fixtures/ocr_samples", help="Diretório de fixtures")
    p.add_argument("--name", type=str, default="sample1", help="Nome base do fixture (ex: sample1)")
    p.add_argument(
        "--force-ocr",
        action="store_true",
        help="Força OCR mesmo se houver texto nativo (útil para medir OCR, não extração nativa).",
    )

    args = p.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    pdf_path = (repo_root / args.pdf).resolve() if not Path(args.pdf).is_absolute() else Path(args.pdf)

    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    out_pdf = out_dir / f"{args.name}.pdf"
    out_txt = out_dir / f"{args.name}.txt"

    # Copy PDF into fixture folder
    out_pdf.write_bytes(pdf_path.read_bytes())

    # Extract text using the project's extractor
    env_backup = dict(os.environ)
    ex: PDFExtractor | None = None
    try:
        if args.force_ocr:
            os.environ["OCR_MIN_CHARS"] = "999999"
            os.environ["OCR_MIN_WORDS"] = "999999"
            os.environ["OCR_MIN_ALNUM_RATIO"] = "1.0"
        ex = PDFExtractor()
        try:
            text = ex.extract(str(out_pdf), log_label=args.name)
        except Exception as e:
            # If OCR forcing fails due to missing system deps (poppler), fall back to native
            # so the user can still generate a ground-truth fixture quickly.
            ex2 = PDFExtractor()
            text = ex2.extract_text_native(str(out_pdf)) or ""
            text = (
                "[NOTE] OCR forcing failed in this environment. Falling back to native PDF text extraction.\n"
                f"[NOTE] Error: {e}\n\n"
                + text
            )
    finally:
        os.environ.clear()
        os.environ.update(env_backup)

    out_txt.write_text(text or "", encoding="utf-8")

    print(f"Fixture PDF: {out_pdf}")
    print(f"Baseline TXT (revisar para ground truth): {out_txt}")
    method = (ex.last_meta.get("method") if ex is not None else None) or "unknown"
    print(f"Extractor method used: {method}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
