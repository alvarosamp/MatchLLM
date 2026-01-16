import pdfplumber
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Optional deps (present only in some environments)
    import google.generativeai  # type: ignore
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
    
    def extract_text_gemini(self, pdf_path: str, *, log_label: str | None = None) -> str:
        """
        Extrai texto usando o Gemini (Google Generative AI) via Files API.
        Requer a variável de ambiente GEMINI_API_KEY (ou GOOGLE_API_KEY).
        """
        label = (log_label or "doc").strip() or "doc"
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY não definida para OCR com Gemini.")
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as e:
            raise RuntimeError("Pacote 'google-generativeai' não instalado. Adicione ao requirements.txt e instale.") from e

        genai.configure(api_key=api_key)  # type: ignore[attr-defined]
        # Tenta múltiplos nomes de modelos para compatibilidade com versões da API
        preferred = os.getenv("GEMINI_OCR_MODEL", "").strip()
        base_candidates = [
            preferred or None,
            # Prefer newer 2.5 family first
            "models/gemini-2.5-flash",
            "models/gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "models/gemini-2.5-flash-8b",
            "models/gemini-2.5-pro-latest",
            "models/gemini-flash-latest",
            "models/gemini-pro-latest",
            # Older 1.5 family
            "gemini-1.5-flash-8b",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash-latest",
            "gemini-1.5-pro-latest",
        ]
        # Normalize and remove empty/None
        seen = set()
        candidates = []
        for name in base_candidates:
            if not name:
                continue
            if name in seen:
                continue
            seen.add(name)
            candidates.append(name)
        model = None
        last_err = None
        for name in candidates:
            try:
                print(f"[{label}] Tentando modelo Gemini: {name}")
                model = genai.GenerativeModel(name)  # type: ignore[attr-defined]
                # Checagem mínima: tenta um prompt trivial sem arquivo (não executa geração pesada)
                _ = getattr(model, "model_name", name)
                print(f"[{label}] Modelo Gemini selecionado: {name}")
                break
            except Exception as e:
                last_err = e
                model = None
                print(f"[{label}] Falha ao usar modelo {name}: {e}")
        if model is None:
            raise RuntimeError(f"Nenhum modelo Gemini válido encontrado. Último erro: {last_err}")

        # Faz upload do arquivo UMA vez e aguarda processamento
        uploaded = genai.upload_file(pdf_path)  # type: ignore[attr-defined]
        try:
            while getattr(uploaded, "state", None) and getattr(uploaded.state, "name", "") == "PROCESSING":
                time.sleep(1)
                uploaded = genai.get_file(uploaded.name)  # type: ignore[attr-defined]
        except Exception:
            pass

        state_name = getattr(getattr(uploaded, "state", None), "name", "ACTIVE")
        if state_name != "ACTIVE":
            raise RuntimeError(f"Falha no upload do PDF para Gemini (estado={state_name}).")

        prompt = (
            "Extraia TODO o texto legível deste PDF em ordem, sem comentários, "
            "sem explicações e sem adicionar conteúdo. Retorne apenas o texto."
        )

        # Tenta gerar conteúdo com cada modelo candidato até obter texto válido
        text = ""
        last_err = None
        for name in candidates:
            try:
                print(f"[{label}] Gerando conteúdo com modelo Gemini: {name}")
                model = genai.GenerativeModel(name)  # type: ignore[attr-defined]
                resp = model.generate_content([prompt, uploaded])
                # Extrai texto das propriedades possíveis
                txt = getattr(resp, "text", None)
                if not txt:
                    try:
                        txt = resp.candidates[0].content.parts[0].text
                    except Exception:
                        txt = None
                if txt:
                    text = txt
                    print(f"[{label}] OCR Gemini bem-sucedido com: {name}")
                    break
                else:
                    last_err = RuntimeError(f"Modelo {name} não retornou texto.")
                    print(f"[{label}] Modelo {name} retornou sem texto.")
            except Exception as e:
                last_err = e
                print(f"[{label}] Falha ao gerar com {name}: {e}")

        if not text and last_err:
            raise RuntimeError(f"Nenhum modelo Gemini produziu texto. Último erro: {last_err}")

        return text or ""

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
            "used_gemini": False,
            "native_text": False,
            "errors": [],
        }

        force_gemini = str(os.getenv("OCR_FORCE_GEMINI", "0")).lower() in ("1", "true", "yes")
        if force_gemini:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError("OCR_FORCE_GEMINI=1, mas GEMINI_API_KEY/GOOGLE_API_KEY não está definida.")
            try:
                print(f"PDFExtractor: usando OCR via Gemini (OCR_FORCE_GEMINI=1) [{label}]...")
                txt = self.extract_text_gemini(pdf_path, log_label=label)
                self.last_meta["method"] = "gemini_forced"
                self.last_meta["used_gemini"] = True
                try:
                    self.last_meta["gemini_quality"] = self._text_quality(txt)
                except Exception:
                    pass
                return txt
            except Exception as e:
                print(f"PDFExtractor: OCR Gemini falhou; caindo para fallback padrão: {e}")
                try:
                    self.last_meta["errors"].append(f"gemini_forced_failed: {e}")
                except Exception:
                    pass

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
        # 2) Gemini só entra se for forçado via OCR_FORCE_GEMINI=1.
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
