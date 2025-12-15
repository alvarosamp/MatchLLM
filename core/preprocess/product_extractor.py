from core.llm.client import LLMClient
import json
import os

PRODUCT_EXTRACTION_PROMPT = """
Você é um especialista técnico em leitura de datasheets.

Tarefa:
- Ler o texto do datasheet e extrair SOMENTE especificações técnicas úteis para comparação em licitações.
- Responda EXCLUSIVAMENTE em JSON válido (compatível com Python json.loads).
- NÃO use markdown, comentários, explicações ou texto fora do JSON.
- NÃO invente valores; quando não houver no texto, use null.
- Use números quando forem quantitativos (ex.: 24), booleanos como true/false, e strings quando houver unidades.
- Padronize chaves em minúsculas com underscore.

Texto do datasheet:
{text}

Estrutura EXATA esperada (exemplo de chaves; preencha o que existir e use null no restante):
{{
    "nome": "...",
    "atributos": {{
        "portas": null,
        "poe": null,
        "gigabit": null,
        "gerenciavel": null,
        "velocidade_porta_gbps": null,
        "capacidade_comutacao_gbps": null,
        "throughput_mpps": null,
        "padroes": [],
        "vlan": null,
        "qos": null,
        "temperatura_operacao_c": {{"min": null, "max": null}},
        "dimensoes_mm": {{"largura": null, "altura": null, "profundidade": null}},
        "peso_kg": null,
        "consumo_w": null,
        "garantia_meses": null
    }}
}}

Regras adicionais:
- Inclua somente atributos que apareçam no texto; os demais mantenha como null.
- Não inclua campos além de "nome" e "atributos" na raiz.
- O JSON final deve ser único, sem vírgula sobrando e sem texto extra.
"""

class ProductExtractor:
    def __init__(self):
        self.llm = LLMClient()

    def extract(self, datasheet_text: str) -> dict:
        prompt = PRODUCT_EXTRACTION_PROMPT.format(text=datasheet_text)
        try:
            response = self.llm.generate(prompt)
        except Exception as e:
            # Se a geração via LLM falhar (ex.: conexão/OOM), tenta OCR Gemini para melhorar texto e tenta novamente
            use_gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
            if use_gemini:
                try:
                    # Reutiliza o texto já recebido? Aqui espera-se que datasheet_text venha de OCR prévio.
                    # Como alternativa, o chamador deve fornecer texto extraído; portanto, apenas re-tenta com prompt simples.
                    response = self.llm.generate(prompt)
                except Exception:
                    # Continua para retornar estrutura mínima
                    return {
                        "nome": None,
                        "atributos": {},
                    }
            else:
                return {
                    "nome": None,
                    "atributos": {},
                }

        # Tenta parsear JSON; se falhar, retorna estrutura mínima
        if isinstance(response, dict):
            return response
        if isinstance(response, str):
            # 1) Tentativa direta
            try:
                return json.loads(response)
            except Exception:
                pass
            # 2) Remover cercas de código ```json ... ``` se existirem
            try:
                if "```" in response:
                    inner = response
                    # pega conteúdo entre a primeira e a última cerca
                    first = inner.find("```")
                    last = inner.rfind("```")
                    if first != -1 and last != -1 and last > first:
                        inner = inner[first+3:last]
                        # remove possível rótulo 'json' no início
                        inner = inner.strip()
                        if inner.lower().startswith("json"):
                            inner = inner[4:].strip()
                        return json.loads(inner)
            except Exception:
                pass
            # 3) Extrair o maior bloco entre chaves { ... }
            try:
                start = response.find("{")
                end = response.rfind("}")
                if start != -1 and end != -1 and end > start:
                    snippet = response[start:end+1]
                    return json.loads(snippet)
            except Exception:
                pass
        return {
            "nome": None,
            "atributos": {},
        }
