import requests
import os


class LLMClient:
    """
    Cliente para comunicação com o LLM rodando via Ollama.

    Responsabilidades:
    - enviar prompt
    - receber resposta textual do modelo
    """

    def __init__(self, model: str | None = None, base_url: str | None = None):
        # Permite sobrescrever via parâmetro; caso contrário usa env vars com defaults
        self.base_url = base_url or os.getenv("LLM_URL", "http://localhost:11434")
        # Default alterado para um modelo menor por padrão (reduz RAM exigida)
        # Ajuste via env: export LLM_MODEL="mistral:7b-instruct-q4_0" ou "llama3:latest"
        self.model = model or os.getenv("LLM_MODEL", "llama2")

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
            # Se o modelo não for encontrado (404), tenta fallback para um modelo disponível
            status = getattr(he.response, "status_code", None) if hasattr(he, "response") else None
            body = he.response.text if hasattr(he, "response") and he.response is not None else ""
            if status == 404 and "model" in body and "not found" in body.lower():
                available = self.list_models()
                if available:
                    # escolhe o primeiro disponível
                    fallback = available[0]
                    try:
                        response2 = requests.post(
                            f"{self.base_url}/api/generate",
                            json={"model": fallback, "prompt": prompt, "stream": False},
                            timeout=120,
                        )
                        response2.raise_for_status()
                        data2 = response2.json()
                        return data2.get("response", "")
                    except Exception as e2:
                        raise RuntimeError(
                            f"Modelo padrão '{self.model}' indisponível e fallback '{fallback}' falhou: {e2}"
                        ) from e2
                raise RuntimeError(
                    f"Modelo '{self.model}' não encontrado e nenhum modelo disponível no Ollama."
                )
            # Inclui parte do corpo para facilitar diagnóstico
            snippet = body[:500]
            raise RuntimeError(
                f"Erro HTTP do LLM ({status}): {snippet}"
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
