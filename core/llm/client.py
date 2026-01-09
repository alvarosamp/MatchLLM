import requests
import os
import time
from urllib.parse import urlparse, urlunparse
import logging

logger = logging.getLogger(__name__)
if not logger.handlers:
    # Configuração mínima para não quebrar quando não existe logging_config no projeto.
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


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
        # Usa modelo menor por padrão para reduzir risco de OOM
        self.model = model or os.getenv("LLM_MODEL", "llama3.2:1b")

        # Timeout configurável (segundos). Use 0 para desabilitar timeout.
        # Ex.: LLM_TIMEOUT_SECONDS=0 (sem timeout) ou LLM_TIMEOUT_SECONDS=600
        self.timeout = self._get_timeout()

    @staticmethod
    def _get_timeout():
        raw = os.getenv("LLM_TIMEOUT_SECONDS", "120")
        raw_s = str(raw or "").strip().lower()
        if raw_s in ("", "none", "null", "off", "false"):
            return None
        try:
            v = float(raw_s)
        except Exception:
            return 120
        if v <= 0:
            return None
        return v

    def _try_generate(self, base_url: str, payload: dict) -> str:
        # Retry leve para falhas transitórias (ConnectionRefused durante carga/restart do Ollama).
        retries = 3
        delay = 0.75
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                response = requests.post(
                    f"{base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
            except requests.exceptions.ConnectionError as e:
                last_exc = e
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        if last_exc:
            raise last_exc
        return ""

    def generate(self, prompt: str) -> str:
        # Allow overriding Ollama generation options via env var LLM_OPTIONS (JSON)
        options_env = os.getenv("LLM_OPTIONS", "")
        options = None
        if options_env:
            try:
                import json as _json
                options = _json.loads(options_env)
            except Exception:
                options = None

        # Default to deterministic, JSON-friendly generation
        if options is None:
            try:
                num_ctx = int(os.getenv("LLM_NUM_CTX", "2048"))
            except Exception:
                num_ctx = 2048
            options = {
                "temperature": 0,
                "top_p": 1,
                # menor contexto por padrão para reduzir uso de memória/V RAM
                "num_ctx": num_ctx,
            }

        # JSON enforcement (optional): when enabled, Ollama will enforce JSON output
        force_json = str(os.getenv("LLM_FORCE_JSON", "0")).lower() in ("1", "true", "yes")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }

        # Optional prompt logging for debugging (enable via env LLM_LOG_PROMPT=1)
        try:
            if str(os.getenv("LLM_LOG_PROMPT", "0")).lower() in ("1", "true", "yes"):
                short = (prompt[:1000] + "...") if isinstance(prompt, str) and len(prompt) > 1000 else prompt
                logger.debug("LLM_PROMPT model=%s base_url=%s prompt=%s", self.model, self.base_url, short)
        except Exception:
            pass

        if force_json:
            payload["format"] = "json"

        try:
            # Tentativa primária
            return self._try_generate(self.base_url, payload)
        except requests.exceptions.ConnectionError as ce:
            # Fallback automático: tenta localhost/127.0.0.1/ollama
            fallbacks = [
                "http://localhost:11434",
                "http://127.0.0.1:11434",
                "http://ollama:11434",
            ]

            tried = [self.base_url]
            for fb in fallbacks:
                if fb in tried:
                    continue
                try:
                    result = self._try_generate(fb, payload)
                    # Atualiza base_url para as próximas chamadas
                    self.base_url = fb
                    logger.info("LLM connected via fallback %s", fb)
                    return result
                except requests.exceptions.RequestException:
                    tried.append(fb)

            logger.exception("Falha ao conectar ao LLM. Tentativas: %s", tried)
            raise RuntimeError(
                f"Não foi possível conectar ao LLM. Tentativas: {', '.join(tried)}. Verifique se o Ollama está em execução."
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
                        logger.info("Attempting fallback model %s due to 404", fallback)
                        response2 = requests.post(
                            f"{self.base_url}/api/generate",
                            json={"model": fallback, "prompt": prompt, "stream": False},
                            timeout=self.timeout,
                        )
                        response2.raise_for_status()
                        data2 = response2.json()
                        return data2.get("response", "")
                    except Exception as e2:
                        logger.exception("Fallback model %s failed", fallback)
                        raise RuntimeError(
                            f"Modelo padrão '{self.model}' indisponível e fallback '{fallback}' falhou: {e2}"
                        ) from e2
                raise RuntimeError(
                    f"Modelo '{self.model}' não encontrado e nenhum modelo disponível no Ollama."
                )
            # Falha por falta de memória GPU: tenta automaticamente um modelo menor (ex.: 1b)
            if status == 500 and ("unable to allocate" in body.lower() or "cuda" in body.lower()):
                available = self.list_models()
                if available:
                    # Heurística simples: preferir nomes contendo '1b'
                    fallback = None
                    for name in available:
                        if "1b" in (name or "").lower():
                            fallback = name
                            break
                    if not fallback:
                        fallback = available[0]
                    try:
                        logger.warning("OOM detected for model %s, trying fallback %s", self.model, fallback)
                        payload2 = dict(payload)
                        payload2["model"] = fallback
                        data2 = self._try_generate(self.base_url, payload2)
                        # Atualiza o modelo padrao do cliente para próximas chamadas
                        self.model = fallback
                        return data2
                    except Exception as e2:
                        logger.exception("Fallback after OOM failed")
                        raise RuntimeError(
                            f"Modelo configurado '{self.model}' causou OOM; fallback '{fallback}' também falhou: {e2}"
                        ) from e2
            # Inclui parte do corpo para facilitar diagnóstico
            snippet = body[:500]
            logger.error("HTTP error from LLM (%s): %s", status, snippet)
            raise RuntimeError(
                f"Erro HTTP do LLM ({status}): {snippet}"
            ) from he
        except requests.exceptions.Timeout as te:
            logger.exception("Timeout ao gerar resposta do LLM")
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
            logger.debug("Unable to list models at %s", self.base_url)
            return []

if __name__ == "__main__":
    llm = LLMClient()
    print(llm.generate("Explique o que é uma licitação em uma frase."))
