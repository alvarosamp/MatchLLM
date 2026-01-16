from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PaddleOCr.paddle_ocr_extractor import PaddleOCRExtractor, PaddleOCROptions


def main() -> int:
    p = argparse.ArgumentParser(description="Extrai texto de PDF usando PaddleOCR (local).")
    p.add_argument("pdf", type=str, help="Caminho do PDF")
    p.add_argument("--out", type=str, default="", help="Arquivo .txt de saída (opcional)")
    p.add_argument("--dpi", type=int, default=300, help="DPI para rasterizar o PDF")
    p.add_argument("--lang", type=str, default="pt", help="Idioma PaddleOCR (ex: pt, en)")
    p.add_argument("--no-angle-cls", action="store_true", help="Desativa classificação de ângulo")

    args = p.parse_args()

    opts = PaddleOCROptions(lang=args.lang, use_angle_cls=not args.no_angle_cls)
    ex = PaddleOCRExtractor(opts)

    text = ex.extract_pdf_text(Path(args.pdf), dpi=int(args.dpi))

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
