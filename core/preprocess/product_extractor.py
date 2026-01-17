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

Estrutura EXEMPLO esperada (use como modelo — NÃO liste explicitamente todos os atributos):
{{
    "nome": "...",
    "tipo_produto": "...",
    "atributos": {{
        "<atributo_tecnico>": {{"valor": null, "unidade": null}},
        "<outro_atributo>": {{"valor": null, "unidade": null}}
    }}
}}

Regras adicionais:
- Inclua somente atributos que apareçam no texto; os demais mantenha como null.
- Evite um conjunto fixo de chaves — o extractor deve inferir e retornar apenas os atributos relevantes
  para o tipo de produto (ex.: elétricos vs mecânicos).
- Use os exemplos acima apenas como referência; não os considere mandatórios.
- O JSON final deve ser único, sem vírgula sobrando e sem texto extra.

Regras de formatação dos atributos:
- Para cada atributo em `atributos`, use SEMPRE o formato {"valor": ..., "unidade": ...}.
- `valor` deve ser number/boolean/string ou null.
- `unidade` deve ser string (ex.: "V", "W", "Gbps", "mm", "kg") ou null.

Regras IMPORTANTES:
- NÃO use chaves placeholder como "<nome_atributo>".
- Se não encontrar nenhum requisito/atributo técnico confiável, retorne:
    {"nome": null, "tipo_produto": null, "atributos": {}}.
"""

class ProductExtractor:
    def __init__(self):
        self.llm = LLMClient()
        self._llm_unavailable = False

        # Permite desabilitar LLM explicitamente e usar apenas heurística.
        self._llm_disabled = str(os.getenv("LLM_DISABLE", "0")).lower() in ("1", "true", "yes")

    def _select_text_window(self, text: str) -> str:
        max_chars = int(os.getenv("PRODUCT_TEXT_MAX_CHARS", "24000"))
        t = (text or "").strip()
        if len(t) <= max_chars:
            return t

        # Para datasheets, specs às vezes ficam no fim (tabelas/rodapé). Usa início+fim.
        head = t[: int(max_chars * 0.6)]
        tail = t[-int(max_chars * 0.4) :]
        return head + "\n\n...<truncado>...\n\n" + tail

    def _sanitize(self, data: dict) -> dict:
        if not isinstance(data, dict):
            return {"nome": None, "tipo_produto": None, "atributos": {}}

        nome = data.get("nome")
        tipo = data.get("tipo_produto")
        atributos = data.get("atributos") if isinstance(data.get("atributos"), dict) else {}

        cleaned: dict = {}
        for k, v in atributos.items():
            if not isinstance(k, str) or not k.strip():
                continue
            kk = k.strip()
            if "<" in kk or ">" in kk or "nome_atributo" in kk.lower():
                continue
            if not isinstance(v, dict):
                # aceita formato antigo e converte
                cleaned[kk] = {"valor": v, "unidade": None}
                continue
            cleaned[kk] = {"valor": v.get("valor", None), "unidade": v.get("unidade", None)}

        return {
            "nome": nome if isinstance(nome, str) and nome.strip() else None,
            "tipo_produto": tipo if isinstance(tipo, str) and tipo.strip() else None,
            "atributos": cleaned,
        }

    def _heuristic_extract(self, text: str) -> dict:
        import re

        t = (text or "")
        attrs: dict = {}

        def _put(key: str, value, unit: str | None):
            if key not in attrs and value is not None:
                attrs[key] = {"valor": value, "unidade": unit}

        # Preço (BRL)
        m = re.search(r"R\$\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?)", t)
        if m:
            raw = m.group(1)
            try:
                v = float(raw.replace(".", "").replace(",", "."))
            except Exception:
                v = None
            _put("preco_brl", v, "BRL")

        # Tensao / corrente / potencia
        m = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*V\b", t, flags=re.IGNORECASE)
        if m:
            _put("tensao_v", float(m.group(1).replace(",", ".")), "V")
        # "12 Volts" / "12 Volt"
        m = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*Volt(?:s)?\b", t, flags=re.IGNORECASE)
        if m:
            _put("tensao_v", float(m.group(1).replace(",", ".")), "V")
        m = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*A\b", t, flags=re.IGNORECASE)
        if m:
            _put("corrente_a", float(m.group(1).replace(",", ".")), "A")
        m = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*W\b", t, flags=re.IGNORECASE)
        if m:
            _put("potencia_w", float(m.group(1).replace(",", ".")), "W")

        # Capacidade elétrica (Ah)
        m = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*Ah\b", t, flags=re.IGNORECASE)
        if m:
            _put("capacidade_ah", float(m.group(1).replace(",", ".")), "Ah")

        # Garantia (meses)
        m = re.search(r"\bgarantia\s*[:\-]?\s*(\d{1,3})\s*mes(?:es)?\b", t, flags=re.IGNORECASE)
        if m:
            _put("garantia_meses", int(m.group(1)), "meses")

        # Memória RAM (GB)
        m = re.search(r"\b(\d{1,3})\s*(?:GB|G)\s*(?:RAM|mem[oó]ria)\b", t, flags=re.IGNORECASE)
        if m:
            _put("memoria_ram_gb", int(m.group(1)), "GB")

        # Armazenamento (GB/TB) - tenta SSD/HDD/NVMe
        m = re.search(
            r"\b(\d{2,4})\s*(GB|TB)\s*(?:SSD|HDD|NVME|NVMe|M\.2)?\b",
            t,
            flags=re.IGNORECASE,
        )
        if m:
            val = int(m.group(1))
            unit = m.group(2).upper()
            gb = val * 1024 if unit == "TB" else val
            _put("armazenamento_gb", gb, "GB")

        # Frequência (GHz)
        m = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*GHz\b", t, flags=re.IGNORECASE)
        if m:
            _put("frequencia_ghz", float(m.group(1).replace(",", ".")), "GHz")

        # Núcleos / cores
        m = re.search(r"\b(\d{1,2})\s*(?:cores|núcleos|nucleos)\b", t, flags=re.IGNORECASE)
        if m:
            _put("cores", int(m.group(1)), None)

        # Tela (polegadas)
        m = re.search(r"\b(\d{1,2}(?:[\.,]\d)?)\s*(?:\"|pol|polegadas|inch|in)\b", t, flags=re.IGNORECASE)
        if m:
            _put("tela_polegadas", float(m.group(1).replace(",", ".")), "pol")

        # Resolução (WxH)
        m = re.search(r"\b(\d{3,4})\s*[xX]\s*(\d{3,4})\b", t)
        if m:
            _put("resolucao_largura_px", int(m.group(1)), "px")
            _put("resolucao_altura_px", int(m.group(2)), "px")

        # Peso (kg)
        m = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*kg\b", t, flags=re.IGNORECASE)
        if m:
            _put("peso_kg", float(m.group(1).replace(",", ".")), "kg")

        # Portas
        m = re.search(r"\b(\d{1,3})\s*(?:portas|ports)\b", t, flags=re.IGNORECASE)
        if m:
            _put("portas", int(m.group(1)), None)

        # Gbps
        m = re.search(r"\b(\d+(?:[\.,]\d+)?)\s*Gbps\b", t, flags=re.IGNORECASE)
        if m:
            _put("velocidade_gbps", float(m.group(1).replace(",", ".")), "Gbps")

        return {"nome": None, "tipo_produto": None, "atributos": attrs}

    def extract(self, datasheet_text: str) -> dict:
        # Não use .format aqui: o prompt contém JSON com chaves { }.
        prompt = PRODUCT_EXTRACTION_PROMPT.replace("{text}", self._select_text_window(datasheet_text))
        # Se o LLM estiver indisponível (timeout/conexão) ou desabilitado, usa heurística direto.
        if self._llm_disabled or self._llm_unavailable:
            return self._sanitize(self._heuristic_extract(datasheet_text))

        try:
            response = self.llm.generate(prompt)
        except Exception as e:
            # Evita travar o pipeline: marca LLM como indisponível e volta para heurística.
            self._llm_unavailable = True
            out = self._sanitize(self._heuristic_extract(datasheet_text))
            # Anexa meta para debug (não quebra consumers).
            try:
                out["_meta"] = {"llm_error": str(e)}
            except Exception:
                pass
            return out

        # Tenta parsear JSON; se falhar, retorna estrutura mínima
        if isinstance(response, dict):
            out = self._sanitize(response)
            if not out.get("atributos"):
                return self._sanitize(self._heuristic_extract(datasheet_text))
            return out
        if isinstance(response, str):
            # 1) Tentativa direta
            try:
                out = self._sanitize(json.loads(response))
                if not out.get("atributos"):
                    return self._sanitize(self._heuristic_extract(datasheet_text))
                return out
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
                        out = self._sanitize(json.loads(inner))
                        if not out.get("atributos"):
                            return self._sanitize(self._heuristic_extract(datasheet_text))
                        return out
            except Exception:
                pass
            # 3) Extrair o maior bloco entre chaves { ... }
            try:
                start = response.find("{")
                end = response.rfind("}")
                if start != -1 and end != -1 and end > start:
                    snippet = response[start:end+1]
                    out = self._sanitize(json.loads(snippet))
                    if not out.get("atributos"):
                        return self._sanitize(self._heuristic_extract(datasheet_text))
                    return out
            except Exception:
                pass
        return {
            "nome": None,
            "tipo_produto": None,
            "atributos": self._heuristic_extract(datasheet_text).get("atributos", {}),
        }
