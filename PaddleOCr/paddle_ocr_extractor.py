from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence
from typing import TYPE_CHECKING
import math

if TYPE_CHECKING:
    from PIL import Image


@dataclass
class PaddleOCROptions:
    """Configuration for PaddleOCR extraction.

    Notes:
      - lang: use "pt" for Portuguese. PaddleOCR also accepts "en", "ch", etc.
      - use_angle_cls: improves scans where the text is rotated.
      - use_gpu: optional; defaults from env PADDLEOCR_USE_GPU.
    """

    lang: str = "pt"
    use_angle_cls: bool = True
    use_gpu: bool | None = None
    det_db_box_thresh: float | None = None
    det_db_thresh: float | None = None


class PaddleOCRNotInstalled(RuntimeError):
    pass


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in ("1", "true", "yes", "y")


def _ensure_paddleocr():
    try:
        from paddleocr import PaddleOCR  # type: ignore

        return PaddleOCR
    except Exception as e:
        raise PaddleOCRNotInstalled(
            "PaddleOCR não está instalado/funcionando. Instale 'paddleocr' e suas dependências. "
            "No macOS, pode ser necessário também 'paddlepaddle' (CPU) compatível."
        ) from e


def _pdf_to_images(pdf_path: str | Path, dpi: int = 300) -> List["Image.Image"]:
    """Convert PDF pages to PIL Images.

    Uses `pdf2image` (requires poppler / pdfinfo on the system PATH).
    """

    try:
        from pdf2image import convert_from_path  # type: ignore
        from pdf2image.exceptions import PDFInfoNotInstalledError  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "Dependência ausente: 'pdf2image'. Instale e garanta que o poppler esteja disponível no sistema."
        ) from e

    try:
        images = convert_from_path(str(pdf_path), dpi=dpi)
        return list(images)
    except PDFInfoNotInstalledError as e:
        raise RuntimeError(
            "Poppler não encontrado (comando 'pdfinfo'). No macOS, instale poppler (ex.: brew install poppler) "
            "e garanta que 'pdfinfo' esteja no PATH."
        ) from e


def _order_lines(lines: Sequence[tuple]) -> List[str]:
    """Reconstruct text lines in a table-friendly reading order.

    Strategy (robust + low-risk):
      1) Convert each OCR box into a (y_center, x_min, x_max, text)
      2) Group into "rows" by Y proximity (tolerance proportional to median height)
      3) Sort rows by Y, and within each row sort by X

    This won't perfectly recreate columns, but preserves table row locality much better
    than a global (y,x) sort.
    """

    def _box_stats(box):
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        return x0, x1, y0, y1

    items = []
    heights = []
    for box, (txt, score) in lines:
        if not txt or not str(txt).strip():
            continue
        x0, x1, y0, y1 = _box_stats(box)
        h = max(1.0, y1 - y0)
        heights.append(h)
        items.append(
            {
                "x0": x0,
                "x1": x1,
                "y0": y0,
                "y1": y1,
                "yc": (y0 + y1) / 2.0,
                "h": h,
                "text": str(txt).strip(),
                "score": float(score) if isinstance(score, (int, float)) else None,
            }
        )

    if not items:
        return []

    heights_sorted = sorted(heights)
    median_h = heights_sorted[len(heights_sorted) // 2]

    # Env tuning: allow stricter/looser row grouping.
    try:
        tol_factor = float(os.getenv("PADDLEOCR_ROW_TOL_FACTOR", "0.60"))
    except Exception:
        tol_factor = 0.60

    y_tol = max(6.0, tol_factor * float(median_h))

    # Build rows
    rows: List[dict] = []
    for it in sorted(items, key=lambda d: (d["yc"], d["x0"])):
        placed = False
        for r in rows:
            if abs(it["yc"] - r["yc"]) <= y_tol:
                r["items"].append(it)
                # update centroid
                r["yc"] = (r["yc"] * (len(r["items"]) - 1) + it["yc"]) / float(len(r["items"]))
                placed = True
                break
        if not placed:
            rows.append({"yc": it["yc"], "items": [it]})

    rows.sort(key=lambda r: r["yc"])

    try:
        col_sep = os.getenv("PADDLEOCR_COL_SEP", " \t ")
    except Exception:
        col_sep = " \t "

    out_lines: List[str] = []
    for r in rows:
        r_items = sorted(r["items"], key=lambda d: d["x0"])
        # join tokens in that row using a separator that preserves column-like spacing
        line = col_sep.join([d["text"] for d in r_items]).strip()
        if line:
            out_lines.append(line)

    return out_lines


class PaddleOCRExtractor:
    """Extract text from PDFs using PaddleOCR locally."""

    def __init__(self, options: PaddleOCROptions | None = None):
        self.options = options or PaddleOCROptions()
        self._ocr = None

    def _get_ocr(self):
        if self._ocr is not None:
            return self._ocr

        PaddleOCR = _ensure_paddleocr()

        use_gpu = self.options.use_gpu
        if use_gpu is None:
            use_gpu = _env_flag("PADDLEOCR_USE_GPU", "0")

        kwargs = {
            "lang": self.options.lang,
            "use_angle_cls": self.options.use_angle_cls,
            "use_gpu": bool(use_gpu),
            "show_log": False,
        }
        # Optional detection tuning (useful for scans)
        if self.options.det_db_box_thresh is not None:
            kwargs["det_db_box_thresh"] = float(self.options.det_db_box_thresh)
        if self.options.det_db_thresh is not None:
            kwargs["det_db_thresh"] = float(self.options.det_db_thresh)

        self._ocr = PaddleOCR(**kwargs)
        return self._ocr

    def extract_pdf_text(self, pdf_path: str | Path, *, dpi: int = 300) -> str:
        images = _pdf_to_images(pdf_path, dpi=dpi)
        return self.extract_images_text(images)

    def extract_images_text(self, images: Iterable["Image.Image"]) -> str:
        ocr = self._get_ocr()

        parts: List[str] = []
        for img in images:
            # PaddleOCR input varies by version; safest is a numpy array (RGB ok for PaddleOCR).
            try:
                import numpy as np  # type: ignore

                img_arr = np.array(img)
            except Exception:
                img_arr = img

            result = ocr.ocr(img_arr, cls=self.options.use_angle_cls)
            # result format: list[ [ [box, (text, score)], ... ] ] per image
            if not result:
                continue
            lines = result[0] if isinstance(result, list) and len(result) > 0 else []
            if not lines:
                continue

            ordered_lines = _order_lines(lines)
            if ordered_lines:
                parts.append("\n".join(ordered_lines))

        return "\n\n".join(parts).strip() + ("\n" if parts else "")
