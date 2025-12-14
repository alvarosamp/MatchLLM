import pdfplumber

class PDFExtractor:
    """
    Extrai o texto de um pdf
    1 -> Tenta ler o arquivo nativo (PDF DIGGERIDO)
    2-> Se nao der, roda o OCR (PDF IMAGEM)
    """

    def __init__(self):
        # Adia carregamento do modelo OCR para evitar falhas quando não instalado
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
        Extrai o texto de pdf escaneados usando ocr
        Retorna o texto extraido
        """
        try:
            from doctr.io import DocumentFile
            from doctr.models import ocr_predictor
        except ImportError:
            raise RuntimeError(
                "OCR não disponível: instale 'python-doctr' e dependências (torch/torchvision)."
            )

        if self.ocr_model is None:
            self.ocr_model = ocr_predictor(pretrained=True)

        doc = DocumentFile.from_pdf(pdf_path)
        result = self.ocr_model(doc)
        return result.render()
    
    def extract(self, pdf_path: str) -> str:
        """
        Extrai o texto de um pdf, tentando primeiro o metodo nativo
        e depois o OCR se necessario
        Retorna o texto extraido
        """
        texto = self.extract_text_native(pdf_path)
        if texto is not None:
            return texto
        # Sem texto nativo, tenta OCR se disponível
        try:
            return self.extract_text_ocr(pdf_path)
        except RuntimeError as e:
            # OCR não instalado; informa e retorna string vazia para seguir fluxo
            print(str(e))
            return ""
