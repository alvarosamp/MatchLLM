import os
import time
import json
import requests
from typing import Any, Dict, Optional


class LLMClient:
    """
    Cliente para comunicação com o Ollama.

    Padrões:
    - Timeout configurável via env
    - Retry simples em timeout
    - Opções de geração seguras (reduzem travamento)
    """

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        self.base_url = (base_url or os.getenv("LLM_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "llama3.2:1b")

        # Timeouts
        # LLM_CONNECT_TIMEOUT: tempo para conectar
        # LLM_READ_TIMEOUT: tempo esperando resposta (geração)
        self.connect_timeout = float(os.getenv("LLM_CONNECT_TIMEOUT", "10"))
        self.read_timeout = float(os.getenv("LLM_READ_TIMEOUT", os.getenv("LLM_TIMEOUT", "120")))

        # Retry em timeout
        self.retries = int(os.getenv("LLM_RETRIES", "1"))
        self.backoff = float(os.getenv("LLM_RETRY_BACKOFF", "2"))

        # Logs
        self.log_prompt = str(os.getenv("LLM_LOG_PROMPT", "0")).lower() in ("1", "true", "yes")
        self.log_timing = str(os.getenv("LLM_LOG_TIMING", "1")).lower() in ("1", "true", "yes")

    def _default_options(self) -> Dict[str, Any]:
        # Opções de geração que ajudam a evitar travar
        # num_predict: limita tokens gerados (importante!)
        return {
            "temperature": float(os.getenv("LLM_TEMPERATURE", "0")),
            "top_p": float(os.getenv("LLM_TOP_P", "1")),
            "num_ctx": int(os.getenv("LLM_NUM_CTX", "2048")),
            "num_predict": int(os.getenv("LLM_NUM_PREDICT", "512")),
        }

    def _load_options(self) -> Dict[str, Any]:
        options_env = os.getenv("LLM_OPTIONS", "")
        if options_env:
            try:
                parsed = json.loads(options_env)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return self._default_options()

    def list_models(self) -> list[str]:
        try:
            r = requests.get(
                f"{self.base_url}/api/tags",
                timeout=(self.connect_timeout, 20),
            )
            r.raise_for_status()
            data = r.json()
            return [m.get("name") for m in data.get("models", []) if m.get("name")]
        except Exception:
            return []

    def _post_generate(self, payload: Dict[str, Any]) -> str:
        t0 = time.time()
        r = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=(self.connect_timeout, self.read_timeout),
        )
        if self.log_timing:
            dt = time.time() - t0
            print(f"[LLM] status={r.status_code} model={payload.get('model')} dt={dt:.2f}s")

        # Se vier erro HTTP, levanta com body disponível
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as he:
            body = ""
            try:
                body = r.text or ""
            except Exception:
                pass
            status = r.status_code
            snippet = body[:800]
            raise RuntimeError(f"Erro HTTP do LLM ({status}): {snippet}") from he

        data = r.json()
        return data.get("response", "")

    def generate(self, prompt: str) -> str:
        options = self._load_options()

        force_json = str(os.getenv("LLM_FORCE_JSON", "0")).lower() in ("1", "true", "yes")

        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        if force_json:
            payload["format"] = "json"

        if self.log_prompt:
            short = prompt if len(prompt) <= 1500 else (prompt[:1500] + "\n...<truncado>...")
            print(f"[LLM_PROMPT] base_url={self.base_url} model={self.model}\n{short}\n")

        attempt = 0
        last_exc: Optional[Exception] = None

        while attempt <= max(0, self.retries):
            try:
                return self._post_generate(payload)

            except requests.exceptions.ReadTimeout as te:
                last_exc = te
                attempt += 1
                if attempt > self.retries:
                    raise RuntimeError(
                        f"Timeout do Ollama após {self.read_timeout}s. "
                        f"Possível prompt grande/modelo lento. "
                        f"Tente reduzir chunks, reduzir num_ctx/num_predict ou usar modelo menor."
                    ) from te
                time.sleep(self.backoff ** attempt)

            except requests.exceptions.ConnectionError as ce:
                last_exc = ce
                raise RuntimeError(
                    f"Não foi possível conectar ao Ollama em {self.base_url}. "
                    f"Verifique se o Ollama está rodando e a porta 11434 está aberta."
                ) from ce

            except requests.exceptions.Timeout as te:
                last_exc = te
                raise RuntimeError(
                    f"Timeout genérico do Ollama (connect/read). connect={self.connect_timeout}s read={self.read_timeout}s."
                ) from te

            except RuntimeError:
                # Já vem com mensagem boa (erro HTTP do LLM)
                raise

            except Exception as e:
                last_exc = e
                raise RuntimeError(f"Falha inesperada ao chamar o LLM: {e}") from e

        # fallback (não deveria chegar aqui)
        raise RuntimeError(f"Falha ao gerar resposta do LLM: {last_exc}")
