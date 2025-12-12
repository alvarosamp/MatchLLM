from core.llm.client import LLMClient

PRODUCT_EXTRACTION_PROMPT = """
Você é um especialista técnico.

A partir do texto abaixo (datasheet de um produto),
extraia APENAS as características técnicas relevantes
para comparação em licitações públicas.

Texto do datasheet:
{text}

Retorne EXCLUSIVAMENTE em JSON, no formato:

{
  "nome": "...",
  "atributos": {
    "tensao": "...",
    "capacidade_ah": ...,
    "tipo": "...",
    "temperatura_max": "...",
    "temperatura_min": "...",
    "garantia_meses": ...,
    "dimensoes_mm": "...",
    "peso_kg": ...
  }
}

Se alguma informação não existir, use null.
"""

class ProductExtractor:
    def __init__(self):
        self.llm = LLMClient()

    def extract(self, datasheet_text: str) -> dict:
        prompt = PRODUCT_EXTRACTION_PROMPT.format(text=datasheet_text)
        response = self.llm.generate(prompt)
        return response
