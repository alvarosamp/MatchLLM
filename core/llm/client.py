import requests
import os
import time
from typing import Optional


class LLMClient:
    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv("LLM_URL", "http://localhost:11434")
        self.model = model or os.getenv("LLM_MODEL", "llama3.2:1b")

    def _timeout(self) -> int:
        try:
            return int(os.getenv("LLM_TIMEOUT", "180"))
        except Exception:
            return 180

    def _options(self) -> dict:
        return {
            "temperature": 0,
            "top_p": 1,
            "num_ctx": int(os.getenv("LLM_NUM_CTX", "2048")),
        }

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": self._options(),
        }

        retries = int(os.getenv("LLM_RETRIES", "2"))
        backoff = float(os.getenv("LLM_RETRY_BACKOFF", "2"))

        for attempt in range(1, retries + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self._timeout(),
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")

            except requests.exceptions.Timeout as e:
                if attempt >= retries:
                    raise RuntimeError("Tempo de espera excedido ao gerar resposta do LLM.") from e
                time.sleep(backoff ** attempt)

            except requests.exceptions.ConnectionError as e:
                raise RuntimeError(
                    "Não foi possível conectar ao Ollama. Verifique se está rodando em http://localhost:11434"
                ) from e

            except requests.exceptions.HTTPError as e:
                body = e.response.text if e.response is not None else ""
                if "unable to allocate" in body.lower() or "cuda" in body.lower():
                    raise RuntimeError("Ollama ficou sem memória ao processar o prompt.") from e
                raise RuntimeError(f"Erro HTTP do LLM: {body[:300]}") from e

        raise RuntimeError("Falha inesperada ao gerar resposta do LLM.")
