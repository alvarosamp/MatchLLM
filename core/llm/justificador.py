import json
import re
from typing import Any, Dict
from core.llm.client import LLMClient


JUSTIFICATION_PROMPT = """
Você é um analista técnico responsável por justificar resultados de conformidade
em processos de licitação pública.

Regras:
- NÃO decida se atende ou não.
- NÃO altere os resultados fornecidos.
- APENAS explique tecnicamente o motivo de cada resultado.
- Use somente os dados fornecidos.
- Seja objetivo e técnico.
- NÃO invente informações.

Produto (JSON):
{produto}

Edital (JSON):
{edital}

Resultado da verificação (definido por código):
{resultado}

Saída (JSON estrito):
{{
  "justificativas": {{
    "<requisito>": "<texto da justificativa>"
  }}
}}
"""


class JustificationGenerator:
    def __init__(self, model: str | None = None):
        self.llm = LLMClient(model=model)

    def _safe_json_load(self, text: str) -> dict | None:
        if "```" in text:
            text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "").strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        try:
            s = text.find("{")
            e = text.rfind("}")
            if s != -1 and e != -1 and e > s:
                return json.loads(text[s:e + 1])
        except Exception:
            pass

        return None

    def generate(
        self,
        produto_json: Dict[str, Any],
        edital_json: Dict[str, Any],
        matching: Dict[str, str],
    ) -> Dict[str, Any]:
        prompt = JUSTIFICATION_PROMPT.format(
            produto=json.dumps(produto_json, ensure_ascii=False, indent=2),
            edital=json.dumps(edital_json, ensure_ascii=False, indent=2),
            resultado=json.dumps(matching, ensure_ascii=False, indent=2),
        )

        raw = self.llm.generate(prompt)

        if isinstance(raw, dict):
            return raw

        if isinstance(raw, str):
            parsed = self._safe_json_load(raw)
            if parsed:
                return parsed

        return {"justificativas": {}}
