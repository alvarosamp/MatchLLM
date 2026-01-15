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
- A resposta DEVE ser um ARRAY JSON (lista) — não envie um objeto único nem texto adicional.
- Não inclua nenhum texto antes ou depois do JSON.
- Se alguma informação for desconhecida, use "N/A" no campo correspondente.
- NÃO explique fora do JSON.
- NÃO use markdown.
- Gere entre 2 e 5 itens; quando possível gere 3 itens (priorize atributos do produto).
- Para cada item inclua, além dos campos já especificados, os seguintes campos adicionais: `matched_attribute`, `confidence`, `evidence`, `missing_fields`, `suggested_fix`.
- `confidence` deve ser um número entre 0 e 1 que indica confiança do veredito.
- `evidence` é uma lista com até 2 trechos curtos do edital que embasam a decisão.
- `matched_attribute` deve ser o nome do atributo do `produto` usado para comparar (ou "N/A").
- `missing_fields` é uma lista de atributos do produto que faltaram e impediram uma avaliação plena.
- `suggested_fix` é uma ação curta (1-3 frases) que o fornecedor poderia executar para atender o requisito.
- Não repita o exemplo abaixo; preencha com dados concretos.
- Se não houver requisito identificável, retorne um único item dentro do array com "requisito": "N/A", "valor_produto": "N/A" e "status": "DUVIDA".

Prioridade de comparação (exemplos, não exaustivo):
- Se o objeto `produto` contiver a chave `atributos`, priorize gerar itens que comparem explicitamente os atributos técnicos
  presentes em `produto["atributos"]`. Exemplos de atributos: preço, tensão, corrente, potência, portas, interfaces,
  consumo, velocidade de porta, capacidade de comutação, garantia, certificações etc. Use esses como exemplos — não como
  uma lista obrigatória.

Comportamento esperado:
- Para cada atributo técnico relevante do produto, gere preferencialmente um item JSON contendo `requisito`, `valor_produto`,
  `matched_attribute`, `status`, `confidence`, `evidence`, `missing_fields`, `suggested_fix`, `justificativa` e `detalhes_tecnicos` (com `esperado`, `observado`, `comparacao`, `unidade`).
- Se o edital não mencionar o atributo, preencha `esperado` com "N/A" e marque `status` como "DUVIDA".
- Além dos atributos técnicos, ainda é aceitável gerar alguns itens administrativos (ex.: prazo, nota fiscal, forma de pagamento),
  mas priorize sempre os itens técnicos derivados dos atributos do produto.
Estrutura EXATA esperada (ARRAY JSON):
[
  {{
    "requisito": "texto do requisito avaliado",
    "valor_produto": "valor correspondente no produto (ou 'N/A')",
    "matched_attribute": "nome do atributo do produto usado para comparar (ou 'N/A')",
    "status": "ATENDE" | "NAO_ATENDE" | "DUVIDA",
    "confidence": 0.0,
    "evidence": ["trecho curto do edital 1", "trecho curto do edital 2"],
    "missing_fields": ["campo1", "campo2"],
    "suggested_fix": "ação curta que o fornecedor pode tomar para atender",
    "comparacao_tecnica": {
        "esperado": "valor esperado/padrão do edital (quando aplicável)",
        "observado": "valor observado/no produto (quando aplicável)",
        "diferenca": "texto curto explicando a diferença (ex: 'produto 10% mais caro')",
        "motivo": "por que essa diferença importa tecnicamente"
    },
    "resumo_tecnico": "frase curta explicando por que bate ou não (ex: 'Esta batendo por conta de tensao compatível')",
    "justificativa": "explicação curta, objetiva e técnica",
    "detalhes_tecnicos": {{
        "esperado": "valor esperado/padrão do edital (quando aplicável)",
        "observado": "valor observado/no produto (quando aplicável)",
        "comparacao": "MAIOR|MENOR|IGUAL|INDEFINIDO",
        "unidade": "unidade (ex: V, A, W, BRL)"
    }}
  }}
]

EXEMPLOS (responda APENAS com o ARRAY JSON):
[
  {{
    "requisito": "Tensão mínima de operação: 220V",
    "valor_produto": "220V",
    "matched_attribute": "tensao",
    "status": "ATENDE",
    "confidence": 0.9,
    "evidence": ["Item 4.1: equipamento deverá operar em 220V.", "Seção X: tensão mínima 220V exigida."],
    "missing_fields": [],
    "suggested_fix": "N/A",
    "comparacao_tecnica": {{"esperado": "220V", "observado": "220V", "diferenca": "N/A", "motivo": "Tensão compatível"}},
    "resumo_tecnico": "Tensão do produto é compatível com o edital.",
    "justificativa": "O produto opera em 220V conforme especificação do fabricante.",
    "detalhes_tecnicos": {{"esperado": "220V", "observado": "220V", "comparacao": "IGUAL", "unidade": "V"}}
  }},
  {{
    "requisito": "Preço máximo por unidade: R$ 900,00",
    "valor_produto": "R$ 1.100,00",
    "matched_attribute": "preco",
    "status": "NAO_ATENDE",
    "confidence": 0.75,
    "evidence": ["Seção 7: preço por unidade não pode exceder R$ 900,00."],
    "missing_fields": [],
    "suggested_fix": "Reduzir preço por unidade para <= R$ 900 ou oferecer desconto por volume.",
    "comparacao_tecnica": {{"esperado": "<= R$ 900,00", "observado": "R$ 1.100,00", "diferenca": "R$ 200,00 acima do máximo", "motivo": "Preço acima do limite do edital"}},
    "resumo_tecnico": "Não atende por preço acima do limite.",
    "justificativa": "O preço informado excede o limite máximo estabelecido no edital.",
    "detalhes_tecnicos": {{"esperado": "<= R$ 900,00", "observado": "R$ 1.100,00", "comparacao": "MAIOR", "unidade": "BRL"}}
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
    "justificativa": "motivo objetivo do veredito (se não atende, explique o que falta)",
    "detalhes_tecnicos": {{
        "esperado": "valor/condição esperada pelo edital (quando houver)",
        "observado": "valor do produto correspondente (quando houver)",
        "comparacao": "MAIOR|MENOR|IGUAL|INDEFINIDO",
        "unidade": "unidade (ex: V, A, W, BRL)"
    }}
  }}
]

Regras:
- Baseie-se APENAS nas informações do produto e nos requisitos.
- Se faltar dado no produto, use 'N/A' e marque como 'DUVIDA' ou 'NAO_ATENDE' conforme o caso.
- Não inclua texto fora do JSON.
"""
