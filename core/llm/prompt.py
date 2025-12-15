MATCH_PROMPT = """
Você é um especialista em análise técnica de licitações.

Tarefa:
Comparar as características do produto com os requisitos do edital.

Produto (JSON):
{produto}

Trechos relevantes do edital:
{edital}

INSTRUÇÕES DE SAÍDA (STRICT MODE):
- Responda EXCLUSIVAMENTE em JSON.
- Não inclua nenhum texto antes ou depois do JSON.
- Se alguma informação for desconhecida, use "N/A" no campo correspondente.
- NÃO explique fora do JSON.
- NÃO use markdown.
- Gere de 1 a 5 itens baseados SOMENTE nos trechos do edital.
- Não repita o exemplo abaixo; preencha com dados concretos.
- Se não houver requisito identificável, retorne um único item com "requisito": "N/A", "valor_produto": "N/A" e "status": "DUVIDA".

Estrutura EXATA esperada:
[
  {{
    "requisito": "texto do requisito avaliado",
    "valor_produto": "valor correspondente no produto (ou 'N/A')",
    "status": "ATENDE" | "NAO_ATENDE" | "DUVIDA",
    "justificativa": "explicação curta, objetiva e técnica"
  }}
]
"""

# Prompt para extrair itens/requisitos do edital em JSON estruturado
REQUIREMENTS_PROMPT = """
Você é um especialista em leitura de editais. Extraia os requisitos solicitados e suas descrições
dos trechos do edital fornecidos. Responda EXCLUSIVAMENTE em JSON (sem markdown, sem explicações).

Entrada (trechos do edital):
{edital}

Saída (JSON estrito):
[
  {{
    "item_id": "identificador curto ou número se houver",
    "titulo": "título/assunto do requisito, se existir, senão resumo curto",
    "descricao": "descrição objetiva do que é exigido",
    "criterios": ["pontos ou critérios relevantes, se existirem"]
  }}
]

Regras:
- Liste de 5 a 30 itens relevantes. Agrupe subtópicos quando fizer sentido.
- Se não houver itens claros, retorne um único com "titulo": "N/A" e "descricao": "N/A".
- Não inclua texto fora do JSON.
"""

# Prompt para comparar um produto com a lista de requisitos do edital
MATCH_ITEMS_PROMPT = """
Você é um analista técnico. Compare o produto com cada requisito do edital e retorne um veredito
por item. Responda EXCLUSIVAMENTE em JSON (sem markdown, sem explicações).

Produto (JSON):
{produto}

Requisitos do edital (JSON):
{requisitos}

Saída (JSON estrito):
[
  {{
    "item_id": "mesmo item_id do requisito",
    "requisito": "título ou resumo do requisito",
    "valor_produto": "valor/atributo do produto correspondente ou 'N/A'",
    "status": "ATENDE" | "NAO_ATENDE" | "DUVIDA",
    "justificativa": "motivo objetivo do veredito (se não atende, explique o que falta)"
  }}
]

Regras:
- Baseie-se APENAS nas informações do produto e nos requisitos.
- Se faltar dado no produto, use 'N/A' e marque como 'DUVIDA' ou 'NAO_ATENDE' conforme o caso.
- Não inclua texto fora do JSON.
"""
