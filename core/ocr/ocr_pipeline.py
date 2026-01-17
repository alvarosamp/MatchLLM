import pdfplumber
import cv2
import numpy as np
from PIL import Image

try:
    import pytesseract  # type: ignore
except Exception:
    pytesseract = None


def ocr_pdf(path: str) -> str:
    text = ""

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"

            # OCR de imagem (opcional). Se pytesseract não estiver disponível,
            # seguimos apenas com o texto extraído nativamente do PDF.
            if pytesseract is not None:
                img = page.to_image(resolution=300).original
                gray = cv2.cvtColor(np.array(img), cv2.COLOR_BGR2GRAY)
                ocr_img = pytesseract.image_to_string(gray, lang="eng")
                text += ocr_img + "\n"

    return text
