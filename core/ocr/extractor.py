import pdfplumber
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Optional deps (present only in some environments)
    import doctr  # type: ignore

class PDFExtractor:
    """
    Extrai o texto de um pdf
    1 -> Tenta ler o arquivo nativo (PDF DIGGERIDO)
    2-> Se nao der, roda o OCR (PDF IMAGEM)
    """

    def __init__(self):
        # Adia carregamento do modelo OCR para evitar falhas quando não instalado
        self.ocr_model = None
        # Meta do último extract() para debug (método usado, erros etc.)
        self.last_meta: dict = {}

    @staticmethod
    def _text_quality(text: str) -> dict:
        t = text or ""
        chars = len(t)
        if chars == 0:
            return {"chars": 0, "words": 0, "alnum_ratio": 0.0}
        words = len(t.split())
        alnum = sum(1 for c in t if c.isalnum())
        return {
            "chars": chars,
            "words": words,
            "alnum_ratio": float(alnum) / float(chars) if chars else 0.0,
        }

    def _is_usable_text(self, text: str) -> bool:
        q = self._text_quality(text)
        try:
            min_chars = int(os.getenv("OCR_MIN_CHARS", "800"))
        except Exception:
            min_chars = 800
        try:
            min_words = int(os.getenv("OCR_MIN_WORDS", "120"))
        except Exception:
            min_words = 120
        try:
            min_ratio = float(os.getenv("OCR_MIN_ALNUM_RATIO", "0.12"))
        except Exception:
            min_ratio = 0.12
        return q["chars"] >= min_chars and q["words"] >= min_words and q["alnum_ratio"] >= min_ratio

    def extract_text_native(self, pdf_path: str) -> str | None:
        """
        Extrai texto de PDF que possuem texto embutido
        Retorna None se der erro ou nao tiver texto util
        """
        try: 
            with pdfplumber.open(pdf_path) as pdf:
                texto = ""
                for pagina in pdf.pages:
                    page_txt = pagina.extract_text()
                    if page_txt:
                        texto += page_txt + "\n"
            return texto if texto.strip() else None
        except Exception as e:
            print(f"Erro ao extrair texto nativo: {e}")
            return None
        
    def extract_text_ocr(self, pdf_path: str) -> str:
        """
        Extrai o texto de pdf escaneados usando OCR local.

        Backend padrão: PaddleOCR (idioma pt).
        Fallback: python-doctr (se instalado).
        """
        # 1) PaddleOCR (preferencial)
        try:
            from PaddleOCr.paddle_ocr_extractor import PaddleOCRExtractor

            dpi = int(os.getenv("PADDLEOCR_DPI", "300"))
            ex = PaddleOCRExtractor()
            return ex.extract_pdf_text(pdf_path, dpi=dpi)
        except Exception as e:
            # Mantém motivo para debug; cai para fallback
            raise RuntimeError(f"PaddleOCR falhou/indisponível: {repr(e)}")

    def extract_text_doctr(self, pdf_path: str) -> str:
        """Fallback OCR: python-doctr (antigo backend local)."""
        try:
            from doctr.io import DocumentFile  # type: ignore
            from doctr.models import ocr_predictor  # type: ignore
        except ImportError:
            raise RuntimeError(
                "OCR (doctr) não disponível: instale 'python-doctr' e dependências (torch/torchvision)."
            )

        if self.ocr_model is None:
            self.ocr_model = ocr_predictor(pretrained=True)

        doc = DocumentFile.from_pdf(pdf_path)
        result = self.ocr_model(doc)
        return result.render()

    def extract(self, pdf_path: str, *, log_label: str | None = None) -> str:
        """
        Extrai o texto de um pdf, tentando primeiro o metodo nativo
        e depois o OCR se necessario
        Retorna o texto extraido
        """
        label = (log_label or "doc").strip() or "doc"
        self.last_meta = {
            "pdf_path": pdf_path,
            "method": None,
            "native_text": False,
            "errors": [],
        }

        texto = self.extract_text_native(pdf_path)
        if texto is not None:
            self.last_meta["native_text"] = True
            self.last_meta["native_quality"] = self._text_quality(texto)
            # Alguns PDFs escaneados retornam "texto" lixo via extractor nativo.
            # Se for baixa qualidade, tenta OCR para melhorar.
            if self._is_usable_text(texto):
                self.last_meta["method"] = "native"
                return texto
            try:
                self.last_meta["errors"].append("native_low_quality")
            except Exception:
                pass
    # Sem texto nativo, tenta OCR local.
    # 1) PaddleOCR (padrão). Se falhar, tenta Doctr (se instalado).
        try:
            txt = self.extract_text_ocr(pdf_path)
            self.last_meta["ocr_quality"] = self._text_quality(txt)
            if self._is_usable_text(txt):
                self.last_meta["method"] = "paddleocr"
                return txt
            # baixa qualidade: tenta fallback doctr
            try:
                self.last_meta["errors"].append("paddleocr_low_quality")
            except Exception:
                pass
            try:
                txt_d = self.extract_text_doctr(pdf_path)
                self.last_meta["doctr_quality"] = self._text_quality(txt_d)
                if self._is_usable_text(txt_d):
                    self.last_meta["method"] = "doctr"
                    return txt_d
                try:
                    self.last_meta["errors"].append("doctr_low_quality")
                except Exception:
                    pass
            except Exception as e2:
                try:
                    self.last_meta["errors"].append(f"doctr_failed: {e2}")
                except Exception:
                    pass

            self.last_meta["method"] = "paddleocr_low_quality"
            return txt
        except RuntimeError as e:
            msg = str(e)
            print(msg)
            try:
                self.last_meta["errors"].append(f"ocr_failed: {msg}")
            except Exception:
                pass
            self.last_meta["method"] = "none"
            return ""
