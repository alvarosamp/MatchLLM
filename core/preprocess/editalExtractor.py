from core.llm.client import LLMClient
import json
import re
import os
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

Muito importante (para evitar lixo):
- Extraia SOMENTE requisitos técnicos do produto (especificações, dimensões, elétricos, performance, conectividade, garantia).
- NÃO extraia requisitos jurídicos/administrativos/comerciais, por exemplo: certidões, habilitação, modalidade, número do processo, ata, registro de preços, prazos de proposta, documentos, obrigações trabalhistas.
- Cada requisito deve ser MENSURÁVEL: precisa ter valor numérico (mínimo/máximo/exato) e, quando aplicável, unidade.
- Se você não conseguir preencher pelo menos um de (valor_min, valor_max) com número, NÃO inclua o requisito.
- Use chaves CANÔNICAS quando possível (exemplos):
    - tensao_v, corrente_a, potencia_w, capacidade_ah
    - peso_kg, comprimento_mm, largura_mm, altura_mm
    - memoria_ram_gb, armazenamento_gb, velocidade_gbps, portas
    - garantia_meses

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

Regras IMPORTANTES:
- NÃO use chaves placeholder como "<nome_atributo>".
- Se não encontrar requisitos técnicos mensuráveis, retorne `"requisitos": {}`.
"""


class EditalExtractor:
    def __init__(self):
        self.llm = LLMClient()
        self._llm_unavailable = False
        self._llm_disabled = str(os.getenv("LLM_DISABLE", "0")).lower() in ("1", "true", "yes")

    def _heuristic_extract(self, text: str) -> Dict[str, Any]:
        """Fallback determinístico: extrai requisitos mensuráveis com regex.

        Não tenta "entender" o edital como um LLM, mas evita o caso crítico
        de retornar {} quando há requisitos óbvios no texto.
        """
        import unicodedata

        t_raw = (text or "")
        t = t_raw
        # Normaliza para facilitar regex de palavras-chave (mínimo/máximo etc.)
        t_norm = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
        t_norm_l = t_norm.lower()

        def _num(s: str):
            try:
                return float(s.replace(".", "").replace(",", ".")) if ("," in s and "." in s) else float(s.replace(",", "."))
            except Exception:
                try:
                    return float(s)
                except Exception:
                    return None

        reqs: Dict[str, Any] = {}

        def _put_exact(key: str, val, unit: str | None):
            if val is None:
                return
            cur = reqs.get(key)
            if not isinstance(cur, dict):
                reqs[key] = {"valor_min": val, "valor_max": val, "unidade": unit, "obrigatorio": True}

        def _put_min(key: str, val, unit: str | None):
            if val is None:
                return
            cur = reqs.get(key)
            if not isinstance(cur, dict):
                reqs[key] = {"valor_min": val, "valor_max": None, "unidade": unit, "obrigatorio": True}
                return
            vmin = cur.get("valor_min")
            if vmin is None or val > vmin:
                cur["valor_min"] = val
            cur["unidade"] = cur.get("unidade") or unit

        def _put_max(key: str, val, unit: str | None):
            if val is None:
                return
            cur = reqs.get(key)
            if not isinstance(cur, dict):
                reqs[key] = {"valor_min": None, "valor_max": val, "unidade": unit, "obrigatorio": True}
                return
            vmax = cur.get("valor_max")
            if vmax is None or val < vmax:
                cur["valor_max"] = val
            cur["unidade"] = cur.get("unidade") or unit

        # Garantia (meses) - tipicamente "no mínimo X meses"
        for m in re.finditer(r"garantia[^\n]{0,80}?(?:no\s+minimo|minima|minimo|>=)?\s*(\d{1,3})\s*mes", t_norm_l, flags=re.IGNORECASE):
            v = _num(m.group(1))
            _put_min("garantia_meses", int(v) if v is not None else None, "meses")

        # Tensao (V)
        for m in re.finditer(r"(?:tensao|voltagem)[^\n]{0,40}?(?:no\s+minimo|minima|minimo|>=)?\s*(\d+(?:[\.,]\d+)?)\s*v\b", t_norm_l, flags=re.IGNORECASE):
            _put_min("tensao_v", _num(m.group(1)), "V")
        for m in re.finditer(r"\b(\d+(?:[\.,]\d+)?)\s*v\b", t_norm_l, flags=re.IGNORECASE):
            _put_exact("tensao_v", _num(m.group(1)), "V")

        # Corrente (A)
        for m in re.finditer(r"\b(\d+(?:[\.,]\d+)?)\s*a\b", t_norm_l, flags=re.IGNORECASE):
            _put_exact("corrente_a", _num(m.group(1)), "A")

        # Potência (W)
        for m in re.finditer(r"\b(\d+(?:[\.,]\d+)?)\s*w\b", t_norm_l, flags=re.IGNORECASE):
            _put_exact("potencia_w", _num(m.group(1)), "W")

        # Capacidade (Ah)
        for m in re.finditer(r"\b(\d+(?:[\.,]\d+)?)\s*ah\b", t_norm_l, flags=re.IGNORECASE):
            _put_exact("capacidade_ah", _num(m.group(1)), "Ah")

        # Memória RAM (GB)
        for m in re.finditer(r"\bno\s+minimo\s*(\d{1,4})\s*gb\b[^\n]{0,20}?(?:ram|memoria)", t_norm_l, flags=re.IGNORECASE):
            _put_min("memoria_ram_gb", _num(m.group(1)), "GB")
        for m in re.finditer(r"\b(\d{1,4})\s*gb\b[^\n]{0,20}?(?:ram|memoria)", t_norm_l, flags=re.IGNORECASE):
            _put_exact("memoria_ram_gb", _num(m.group(1)), "GB")

        # Armazenamento (GB/TB)
        for m in re.finditer(r"\bno\s+minimo\s*(\d{2,5})\s*(gb|tb)\b", t_norm_l, flags=re.IGNORECASE):
            val = _num(m.group(1))
            unit = (m.group(2) or "").upper()
            if val is not None and unit == "TB":
                val = val * 1024
            _put_min("armazenamento_gb", val, "GB")

        # Portas (ex.: 8 portas / interfaces de rede 8)
        for m in re.finditer(r"\b(\d{1,3})\s*(?:portas|ports)\b", t_norm_l, flags=re.IGNORECASE):
            _put_exact("portas", int(_num(m.group(1)) or 0) or None, None)
        for m in re.finditer(r"interfaces\s+de\s+rede\s*(\d{1,3})\b", t_norm_l, flags=re.IGNORECASE):
            _put_exact("portas", int(_num(m.group(1)) or 0) or None, None)

        # Velocidade/throughput (Gbps)
        for m in re.finditer(r"\b(\d+(?:[\.,]\d+)?)\s*gbps\b", t_norm_l, flags=re.IGNORECASE):
            _put_exact("velocidade_gbps", _num(m.group(1)), "Gbps")

        # PoE (booleano) - presença do termo já é um requisito relevante
        if re.search(r"\bpoe\b", t_norm_l, flags=re.IGNORECASE):
            reqs.setdefault("poe", {"valor_min": None, "valor_max": None, "unidade": None, "obrigatorio": True})

        return {"item": None, "tipo_produto": None, "requisitos": reqs}

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

    def extract(self, edital_text: str, produto_hint: str | None = None) -> Dict[str, Any]:
        # Se o LLM já falhou anteriormente (timeout/conexão) ou foi desabilitado,
        # usa heurística para manter o pipeline funcional.
        if self._llm_disabled or self._llm_unavailable:
            out = self._heuristic_extract(edital_text)
            try:
                out["_meta"] = {"llm_skipped": True}
            except Exception:
                pass
            return out

        # Evita estourar contexto do modelo (num_ctx). O RAG já reduz bastante, mas editais
        # ainda podem ser longos dependendo do chunking/top_k.
        max_chars = int(os.getenv("EDITAL_TEXT_MAX_CHARS", "25000"))
        if edital_text and len(edital_text) > max_chars:
            edital_text = edital_text[:max_chars]

        # 🔥 SUBSTITUIÇÃO SEGURA (SEM format)
        prompt = EDITAL_EXTRACTION_PROMPT
        if produto_hint and str(produto_hint).strip():
            hint = str(produto_hint).strip()
            # Ajuda quando o edital tem múltiplos itens (ex.: "material de informática").
            # Direciona o modelo a extrair requisitos do item que descreve o produto.
            prompt = (
                prompt
                + "\n\nContexto adicional (muito importante):\n"
                + f"- Produto para comparação: {hint}\n"
                + "- Extraia requisitos apenas do item/descrição no edital/termo de referência que corresponde a esse produto.\n"
                + "- Se houver vários itens, ignore os que não são deste produto.\n"
            )
        prompt = prompt.replace("{text}", edital_text)

        try:
            response = self.llm.generate(prompt)
        except Exception as e:
            # Marca como indisponível para evitar repetição de timeouts em loops (fullscan)
            self._llm_unavailable = True
            out = self._heuristic_extract(edital_text)
            try:
                out["_meta"] = {"llm_error": str(e)}
            except Exception:
                pass
            return out

        def _sanitize(data: Dict[str, Any]) -> Dict[str, Any]:
            item = data.get("item")
            tipo = data.get("tipo_produto")
            requisitos = data.get("requisitos") if isinstance(data.get("requisitos"), dict) else {}
            cleaned: Dict[str, Any] = {}
            for k, regra in requisitos.items():
                if not isinstance(k, str) or not k.strip():
                    continue
                kk = k.strip()
                # Rejeita chaves absurdas ou claramente inválidas (ex.: sequências só de números/pontos).
                if len(kk) > 80:
                    continue
                if re.fullmatch(r"[0-9.\-_/\\\s]+", kk or ""):
                    continue
                if not re.search(r"[A-Za-zÀ-ÿ]", kk):
                    continue
                if "<" in kk or ">" in kk or "nome_atributo" in kk.lower():
                    continue
                if not isinstance(regra, dict):
                    continue
                cleaned[kk] = {
                    "valor_min": regra.get("valor_min", None),
                    "valor_max": regra.get("valor_max", None),
                    "unidade": regra.get("unidade", None),
                    "obrigatorio": bool(regra.get("obrigatorio", True)),
                }

            return {
                "item": item if isinstance(item, str) and item.strip() else None,
                "tipo_produto": tipo.strip() if isinstance(tipo, str) and tipo.strip() else None,
                "requisitos": cleaned,
            }

        if isinstance(response, dict):
            return _sanitize(response)

        if isinstance(response, str):
            parsed = self._safe_json_load(response)
            if parsed:
                return _sanitize(parsed)

        return {
            "item": None,
            "tipo_produto": None,
            "requisitos": {}
        }
