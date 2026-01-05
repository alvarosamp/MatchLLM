from core.llm.client import LLMClient
import json
import re
from typing import Optional, Dict, Any


EDITAL_EXTRACTION_PROMPT = """
Você é um especialista técnico em leitura de editais de licitação pública.

Tarefa:
- Ler o texto do edital ou do item do edital.
- Identificar o tipo principal do produto.
- Extrair SOMENTE requisitos técnicos obrigatórios ou mensuráveis.
- Interpretar corretamente termos como:
  - "mínimo", "no mínimo", ">=" → valor_min
  - "máximo", "<=" → valor_max
  - valores exatos → valor_min = valor_max
- Não inventar requisitos.
- Se um requisito não estiver explícito, NÃO incluir.

Regras obrigatórias:
- Responder EXCLUSIVAMENTE em JSON válido.
- Não usar markdown.
- Não usar comentários.
- Não incluir texto fora do JSON.
- Padronizar chaves em minúsculas com underscore.
- Usar números quando possível.

Formato OBRIGATÓRIO:

{
  "item": "",
  "tipo_produto": "",
  "requisitos": {
    "<nome_atributo>": {
      "valor_min": null,
      "valor_max": null,
      "unidade": null,
      "obrigatorio": true
    }
  }
}

Texto do edital:
{text}
"""


class EditalExtractor:
    def __init__(self):
        self.llm = LLMClient()

    def _safe_json_load(self, text: str) -> Optional[Dict[str, Any]]:
        if "```" in text:
            text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "").strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
        except Exception:
            pass

        return None

    def extract(self, edital_text: str) -> Dict[str, Any]:
        # 🔥 SUBSTITUIÇÃO SEGURA (SEM format)
        prompt = EDITAL_EXTRACTION_PROMPT.replace("{text}", edital_text)

        try:
            response = self.llm.generate(prompt)
        except Exception:
            return {
                "item": None,
                "tipo_produto": None,
                "requisitos": {}
            }

        if isinstance(response, dict):
            return response

        if isinstance(response, str):
            parsed = self._safe_json_load(response)
            if parsed:
                return parsed

        return {
            "item": None,
            "tipo_produto": None,
            "requisitos": {}
        }
