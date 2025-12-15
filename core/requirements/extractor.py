from __future__ import annotations
from typing import List, Dict, Any
from core.llm.client import LLMClient
from core.llm.prompt import REQUIREMENTS_PROMPT
import json

class RequirementExtractor:
    """
    Extrai itens/requisitos de trechos do edital usando LLM, retornando uma lista de dicts.
    """
    def __init__(self, model: str | None = None):
        self.llm = LLMClient(model=model)

    def extract(self, edital_text: str) -> List[Dict[str, Any]]:
        prompt = REQUIREMENTS_PROMPT.format(edital=edital_text)
        raw = self.llm.generate(prompt)
        # Tenta normalizar como JSON de lista
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return [raw]
        if isinstance(raw, str):
            # 1) direto
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return [data]
            except Exception:
                pass
            # 2) cerca de código
            try:
                if "```" in raw:
                    first = raw.find("```")
                    last = raw.rfind("```")
                    if first != -1 and last != -1 and last > first:
                        inner = raw[first+3:last].strip()
                        if inner.lower().startswith("json"):
                            inner = inner[4:].strip()
                        data = json.loads(inner)
                        if isinstance(data, list):
                            return data
                        if isinstance(data, dict):
                            return [data]
            except Exception:
                pass
            # 3) maior bloco [ ... ]
            try:
                s = raw.find('[')
                e = raw.rfind(']')
                if s != -1 and e != -1 and e > s:
                    snippet = raw[s:e+1]
                    data = json.loads(snippet)
                    if isinstance(data, list):
                        return data
            except Exception:
                pass
        # fallback mínimo
        return [{"item_id": "N/A", "titulo": "N/A", "descricao": "N/A", "criterios": []}]
