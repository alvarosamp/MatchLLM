from __future__ import annotations
from typing import List, Dict, Any
from core.llm.client import LLMClient
from core.llm.prompt import MATCH_ITEMS_PROMPT
import json

class ItemMatcher:
    """
    Compara produto com a lista de requisitos extraídos do edital usando LLM.
    Retorna lista de veredictos por item.
    """
    def __init__(self, model: str | None = None):
        self.llm = LLMClient(model=model)

    def match(self, produto_json: Dict[str, Any], requisitos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        prompt = MATCH_ITEMS_PROMPT.format(
            produto=json.dumps(produto_json, ensure_ascii=False),
            requisitos=json.dumps(requisitos, ensure_ascii=False)
        )
        raw = self.llm.generate(prompt)
        # normaliza resposta como lista de dicts
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return [raw]
        if isinstance(raw, str):
            # direto
            try:
                data = json.loads(raw)
                return data if isinstance(data, list) else [data]
            except Exception:
                pass
            # extrair bloco [ ... ]
            try:
                s = raw.find('[')
                e = raw.rfind(']')
                if s != -1 and e != -1 and e > s:
                    data = json.loads(raw[s:e+1])
                    return data if isinstance(data, list) else [data]
            except Exception:
                pass
        return []
