from core.llm.client import LLMClient
import json
import re
from typing import Optional, Dict, Any


PRODUCT_EXTRACTION_PROMPT = """
Você é um especialista técnico em leitura de datasheets para licitações públicas.

Tarefa:
- Ler o texto do datasheet.
- Identificar o tipo principal do produto (ex: eletrônico, mecânico, TI, químico, outro).
- Extrair APENAS especificações técnicas objetivas e mensuráveis.
- Não inventar valores.
- Se um atributo não estiver explicitamente no texto, NÃO inclua.
- Responder EXCLUSIVAMENTE em JSON válido.

Regras obrigatórias:
- Não usar markdown.
- Não usar comentários.
- Não incluir texto fora do JSON.
- Padronizar chaves em minúsculas com underscore.
- Valores quantitativos devem ser números quando possível.
- Usar string apenas quando houver unidade associada.

Formato OBRIGATÓRIO:

{{
  "nome": "",
  "tipo_produto": "",
  "atributos": {{
    "<nome_atributo>": {{
      "valor": null,
      "unidade": null
    }}
  }}
}}

Texto do datasheet:
{text}
"""


class ProductExtractor:
    def __init__(self):
        self.llm = LLMClient()

    def _safe_json_load(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Tenta extrair JSON válido de uma resposta imperfeita do LLM.
        """
        # Remove cercas ``` se existirem
        if "```" in text:
            text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "").strip()

        # Tentativa direta
        try:
            return json.loads(text)
        except Exception:
            pass

        # Extrai maior bloco JSON
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
        except Exception:
            pass

        return None

    def _clean_attributes(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove atributos vazios ou malformados.
        """
        attrs = data.get("atributos", {})
        clean_attrs = {}

        for k, v in attrs.items():
            if not isinstance(v, dict):
                continue

            valor = v.get("valor")
            unidade = v.get("unidade")

            if valor is not None:
                clean_attrs[k] = {
                    "valor": valor,
                    "unidade": unidade
                }

        data["atributos"] = clean_attrs
        return data

    def extract(self, datasheet_text: str) -> Dict[str, Any]:
        prompt = PRODUCT_EXTRACTION_PROMPT.replace("{text}", datasheet_text)


        try:
            response = self.llm.generate(prompt)
        except Exception:
            return {
                "nome": None,
                "tipo_produto": None,
                "atributos": {}
            }

        if isinstance(response, dict):
            return self._clean_attributes(response)

        if isinstance(response, str):
            parsed = self._safe_json_load(response)
            if parsed:
                return self._clean_attributes(parsed)

        return {
            "nome": None,
            "tipo_produto": None,
            "atributos": {}
        }
