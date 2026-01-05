from core.llm.client import LLMClient
import json


JUSTIFICATION_PROMPT = """
Você é um analista técnico responsável por justificar resultados de conformidade
em processos de licitação pública.

Regras IMPORTANTES:
- NÃO tome decisões.
- NÃO altere os resultados fornecidos.
- APENAS explique tecnicamente o motivo de cada resultado.
- Baseie-se EXCLUSIVAMENTE nos dados fornecidos.
- Seja objetivo, técnico e claro.
- NÃO invente informações.

Dados do produto:
{produto}

Requisitos do edital:
{edital}

Resultado da verificação:
{resultado}

Formato da resposta (JSON obrigatório):

{
  "justificativas": {
    "<nome_requisito>": "<texto_da_justificativa>"
  }
}
"""


class JustificationGenerator:
    def __init__(self):
        self.llm = LLMClient()

    def generate(
        self,
        produto_json: dict,
        edital_json: dict,
        resultado_matching: dict
    ) -> dict:

        prompt = JUSTIFICATION_PROMPT.format(
            produto=json.dumps(produto_json, ensure_ascii=False, indent=2),
            edital=json.dumps(edital_json, ensure_ascii=False, indent=2),
            resultado=json.dumps(resultado_matching, ensure_ascii=False, indent=2),
        )

        response = self.llm.generate(prompt)

        if isinstance(response, dict):
            return response

        if isinstance(response, str):
            try:
                return json.loads(response)
            except Exception:
                pass

        return {"justificativas": {}}
