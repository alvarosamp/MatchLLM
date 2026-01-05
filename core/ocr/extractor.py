import os
import time
import pdfplumber


class PDFExtractor:
    """
    Extrai texto de PDFs com fallback automático:
    1) Texto nativo (PDF com texto embutido)
    2) OCR via Gemini (PDF escaneado / imagem)

    Requer:
    - pdfplumber
    - google-generativeai
    - Variável de ambiente: GEMINI_API_KEY ou GOOGLE_API_KEY
    """

    def __init__(self):
        self._gemini_model = None

    # ------------------------------------------------------------------
    # 1) Extração nativa (PDF com texto embutido)
    # ------------------------------------------------------------------
    def extract_text_native(self, pdf_path: str) -> str | None:
        """
        Extrai texto de PDFs que possuem texto embutido.
        Retorna None se não houver texto útil.
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                texto = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        texto.append(page_text)

            text = "\n".join(texto).strip()
            return text if text else None

        except Exception as e:
            print(f"[native] Erro ao extrair texto nativo: {e}")
            return None

    # ------------------------------------------------------------------
    # 2) OCR via Gemini (fallback)
    # ------------------------------------------------------------------
    def extract_text_gemini(self, pdf_path: str) -> str:
        """
        Extrai texto usando Gemini (Google Generative AI) via Files API.
        """

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY ou GOOGLE_API_KEY não definida.")

        try:
            import google.generativeai as genai
        except ImportError as e:
            raise RuntimeError(
                "Pacote 'google-generativeai' não instalado."
            ) from e

        genai.configure(api_key=api_key)

        # Lista de modelos tentados (do mais novo para o mais estável)
        models = [
            os.getenv("GEMINI_OCR_MODEL"),
            "models/gemini-2.5-flash",
            "models/gemini-2.5-pro",
            "models/gemini-flash-latest",
            "models/gemini-pro-latest",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ]

        # Remove None e duplicados
        models = list(dict.fromkeys(filter(None, models)))

        # Upload do PDF (feito uma única vez)
        uploaded = genai.upload_file(pdf_path)

        while getattr(uploaded, "state", None) and uploaded.state.name == "PROCESSING":
            time.sleep(1)
            uploaded = genai.get_file(uploaded.name)

        if uploaded.state.name != "ACTIVE":
            raise RuntimeError(f"Falha no upload do PDF (estado={uploaded.state.name})")

        prompt = (
            "Extraia TODO o texto legível deste PDF em ordem correta. "
            "Não explique, não resuma, não altere o conteúdo. "
            "Retorne apenas o texto bruto."
        )

        last_error = None

        for model_name in models:
            try:
                print(f"[gemini] Tentando modelo: {model_name}")
                model = genai.GenerativeModel(model_name)
                response = model.generate_content([prompt, uploaded])

                text = getattr(response, "text", None)

                if not text:
                    try:
                        text = response.candidates[0].content.parts[0].text
                    except Exception:
                        text = None

                if text and text.strip():
                    print(f"[gemini] OCR bem-sucedido com: {model_name}")
                    return text.strip()

            except Exception as e:
                last_error = e
                print(f"[gemini] Falha com {model_name}: {e}")

        raise RuntimeError(f"Nenhum modelo Gemini produziu texto. Último erro: {last_error}")

    # ------------------------------------------------------------------
    # Pipeline principal
    # ------------------------------------------------------------------
    def extract(self, pdf_path: str) -> str:
        """
        Pipeline de extração com fallback automático.
        """

        # 1) Texto nativo
        text = self.extract_text_native(pdf_path)
        if text:
            return text

        # 2) OCR via Gemini
        try:
            return self.extract_text_gemini(pdf_path)
        except Exception as e:
            print(f"[extract] Falha total na extração: {e}")
            return ""
