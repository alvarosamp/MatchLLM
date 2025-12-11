MATCH_PROMPT = """
Você é um especialista em análise técnica de licitações.

Tarefa:
Comparar as características do produto com os requisitos do edital.

Produto (JSON):
{produto}

Trechos relevantes do edital:
{edital}

Responda EXCLUSIVAMENTE em JSON, com a estrutura:
[
  {{
    "requisito": "texto do requisito avaliado",
    "valor_produto": "valor correspondente no produto (ou 'N/A')",
    "status": "ATENDE" | "NAO_ATENDE" | "DUVIDA",
    "justificativa": "explicação curta, objetiva e técnica"
  }}
]
"""
