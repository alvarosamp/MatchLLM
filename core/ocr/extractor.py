import pdfplumber
import os
import time

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
    
    def extract_text_gemini(self, pdf_path: str) -> str:
        """
        Extrai texto usando o Gemini (Google Generative AI) via Files API.
        Requer a variável de ambiente GEMINI_API_KEY (ou GOOGLE_API_KEY).
        """
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY não definida para OCR com Gemini.")
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise RuntimeError("Pacote 'google-generativeai' não instalado. Adicione ao requirements.txt e instale.") from e

        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_OCR_MODEL", "gemini-1.5-flash")
        model = genai.GenerativeModel(model_name)

        uploaded = genai.upload_file(pdf_path)
        # Aguarda processamento do arquivo
        try:
            while getattr(uploaded, "state", None) and getattr(uploaded.state, "name", "") == "PROCESSING":
                time.sleep(1)
                uploaded = genai.get_file(uploaded.name)
        except Exception:
            pass

        state_name = getattr(getattr(uploaded, "state", None), "name", "ACTIVE")
        if state_name != "ACTIVE":
            raise RuntimeError(f"Falha no upload do PDF para Gemini (estado={state_name}).")

        prompt = (
            "Extraia TODO o texto legível deste PDF em ordem, sem comentários, "
            "sem explicações e sem adicionar conteúdo. Retorne apenas o texto."
        )
        resp = model.generate_content([prompt, uploaded])
        text = getattr(resp, "text", None)
        if not text:
            # Tenta acessar candidates
            try:
                text = resp.candidates[0].content.parts[0].text
            except Exception:
                text = ""
        return text or ""

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
