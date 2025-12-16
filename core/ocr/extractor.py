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
                print(f"[produto] Tentando modelo Gemini: {name}")
                model = genai.GenerativeModel(name)
                # Checagem mínima: tenta um prompt trivial sem arquivo (não executa geração pesada)
                _ = getattr(model, "model_name", name)
                print(f"[produto] Modelo Gemini selecionado: {name}")
                break
            except Exception as e:
                last_err = e
                model = None
                print(f"[produto] Falha ao usar modelo {name}: {e}")
        if model is None:
            raise RuntimeError(f"Nenhum modelo Gemini válido encontrado. Último erro: {last_err}")

        # Faz upload do arquivo UMA vez e aguarda processamento
        uploaded = genai.upload_file(pdf_path)
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

        # Tenta gerar conteúdo com cada modelo candidato até obter texto válido
        text = ""
        last_err = None
        for name in candidates:
            try:
                print(f"[produto] Gerando conteúdo com modelo Gemini: {name}")
                model = genai.GenerativeModel(name)
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
                    print(f"[produto] OCR Gemini bem-sucedido com: {name}")
                    break
                else:
                    last_err = RuntimeError(f"Modelo {name} não retornou texto.")
                    print(f"[produto] Modelo {name} retornou sem texto.")
            except Exception as e:
                last_err = e
                print(f"[produto] Falha ao gerar com {name}: {e}")

        if not text and last_err:
            raise RuntimeError(f"Nenhum modelo Gemini produziu texto. Último erro: {last_err}")

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
