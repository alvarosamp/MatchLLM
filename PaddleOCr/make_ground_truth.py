from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PaddleOCr.paddle_ocr_extractor import PaddleOCRExtractor


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Gera um .paddle.txt para um PDF (para você revisar e usar como ground truth).\n"
            "Dica: use PDFs pequenos (1-2 páginas) para testes de CER/WER."
        )
    )
    p.add_argument("pdf", type=str, help="Caminho do PDF")
    p.add_argument(
        "--out",
        type=str,
        default="",
        help="Arquivo de saída .txt (default: <pdf>.paddle.txt)",
    )
    p.add_argument("--dpi", type=int, default=350, help="DPI para rasterização (default: 350)")

    args = p.parse_args()

    pdf = Path(args.pdf)
    out = Path(args.out) if args.out else pdf.with_suffix(pdf.suffix + ".paddle.txt")

    ex = PaddleOCRExtractor()
    text = ex.extract_pdf_text(pdf, dpi=int(args.dpi))

    out.write_text(text, encoding="utf-8")
    print(f"Arquivo gerado: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
