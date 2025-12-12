import requests
import os


class LLMClient:
    """
    Cliente para comunicação com o LLM rodando via Ollama.

    Responsabilidades:
    - enviar prompt
    - receber resposta textual do modelo
    """

    def __init__(self):
        self.base_url = os.getenv("LLM_URL", "http://localhost:11434")
        self.model = os.getenv("LLM_MODEL", "llama3.1")

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except requests.exceptions.ConnectionError as ce:
            raise RuntimeError(
                f"Não foi possível conectar ao LLM em {self.base_url}. Verifique se o Ollama está em execução."
            ) from ce
        except requests.exceptions.HTTPError as he:
            # Inclui parte do corpo para facilitar diagnóstico
            snippet = response.text[:500] if response is not None else ""
            raise RuntimeError(
                f"Erro HTTP do LLM ({response.status_code}): {snippet}"
            ) from he
        except requests.exceptions.Timeout as te:
            raise RuntimeError("Tempo de espera excedido ao gerar resposta do LLM.") from te

    def list_models(self) -> list:
        """Lista modelos disponíveis no Ollama."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=10)
            r.raise_for_status()
            data = r.json()
            # Ollama tags: {"models": [{"name": "llama3.1"}, ...]}
            return [m.get("name") for m in data.get("models", [])]
        except Exception:
            return []

if __name__ == "__main__":
    llm = LLMClient()
    print(llm.generate("Explique o que é uma licitação em uma frase."))
