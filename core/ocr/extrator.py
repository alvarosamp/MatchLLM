import pdfplumber

# Tenta importar Doctr; se não disponível, usa fallback com PyMuPDF (fitz)
try:
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor
    _HAS_DOCTR = True
except Exception:
    _HAS_DOCTR = False
    import fitz  # PyMuPDF

class PDFExtrator:
    """
    Extrai o texto de um pdf
    1 -> Tenta ler o arquivo nativo (PDF DIGGERIDO)
    2-> Se nao der, roda o OCR (PDF IMAGEM)
    """

    def __init__(self):
        # Carrega o modelo do OCR da Doctr se disponível; caso contrário, usa fallback
        if _HAS_DOCTR:
            self.ocr_model = ocr_predictor(pretrained=True)
        else:
            self.ocr_model = None

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
        Extrai o texto de PDFs escaneados usando OCR.
        Preferencialmente usa Doctr; se indisponível, faz fallback simples
        renderizando texto por PyMuPDF (pode ter menor acurácia em PDFs imagem).
        """
        if _HAS_DOCTR and self.ocr_model is not None:
            doc = DocumentFile.from_pdf(pdf_path)
            result = self.ocr_model(doc)
            return result.render()
        # Fallback: tentar extrair texto com PyMuPDF (fitz)
        try:
            texto = []
            with fitz.open(pdf_path) as pdf:
                for page in pdf:
                    texto.append(page.get_text())
            return "\n".join(t for t in texto if t)
        except Exception as e:
            print(f"Erro no fallback de OCR (PyMuPDF): {e}")
            return ""
    
    def extract(self, pdf_path: str) -> str:
        """
        Extrai o texto de um pdf, tentando primeiro o metodo nativo
        e depois o OCR se necessario
        Retorna o texto extraido
        """
        texto = self.extract_text_native(pdf_path)
        if texto is not None:
            return texto
        else:
            return self.extract_text_ocr(pdf_path)