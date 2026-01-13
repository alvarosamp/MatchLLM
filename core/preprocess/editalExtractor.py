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
        def _focus_text_for_hint(text: str, hint: str | None) -> str:
            """Reduz o texto para trechos/linhas que mencionam o produto.

            Ajuda especialmente no fallback heurístico: evita capturar números
            de itens não relacionados (ex.: requisitos de informática quando o
            produto é bateria).
            """
            try:
                h = (hint or "").strip().lower()
                if not h:
                    return text

                def _is_battery(hh: str) -> bool:
                    return any(w in hh for w in ("bateria", "no-break", "nobreak", "vrla", "agm", "ah"))

                if not _is_battery(h):
                    return text

                keywords = ("bateria", "no-break", "nobreak", "vrla", "agm", "ah", "wp")
                lines = (text or "").splitlines()
                keep: set[int] = set()
                for i, line in enumerate(lines):
                    ll = (line or "").lower()
                    if any(k in ll for k in keywords):
                        keep.add(i)
                        # specs frequentemente vêm logo abaixo
                        keep.add(i + 1)
                        keep.add(i + 2)
                kept_lines = [lines[i] for i in sorted(keep) if 0 <= i < len(lines)]
                focused = "\n".join([ln for ln in kept_lines if ln and ln.strip()]).strip()
                return focused or text
            except Exception:
                return text

        # Se o LLM já falhou anteriormente (timeout/conexão) ou foi desabilitado,
        # usa heurística para manter o pipeline funcional.
        if self._llm_disabled or self._llm_unavailable:
            out = self._heuristic_extract(_focus_text_for_hint(edital_text, produto_hint))

            # Filtra requisitos heurísticos por tipo quando possível.
            try:
                hint = (produto_hint or "").strip().lower()
                if hint:
                    def _is_battery(h: str) -> bool:
                        return any(w in h for w in ("bateria", "no-break", "nobreak", "vrla", "agm", "ah"))

                    if _is_battery(hint):
                        allowed = {
                            "tensao_v",
                            "capacidade_ah",
                            "garantia_meses",
                            "peso_kg",
                            "comprimento_mm",
                            "largura_mm",
                            "altura_mm",
                        }
                        reqs = out.get("requisitos") if isinstance(out, dict) else None
                        if isinstance(reqs, dict) and reqs:
                            out["requisitos"] = {k: v for k, v in reqs.items() if k in allowed}
            except Exception:
                pass

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

        def _to_num(v):
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                s = v.strip()
                if not s:
                    return None
                # aceita formatos PT-BR e EN ("1.234,56" / "1234.56")
                try:
                    if "," in s and "." in s:
                        return float(s.replace(".", "").replace(",", "."))
                    return float(s.replace(",", "."))
                except Exception:
                    return None
            return None

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

                vmin = _to_num(regra.get("valor_min", None))
                vmax = _to_num(regra.get("valor_max", None))
                # Requisito mensurável precisa ter pelo menos um número
                if vmin is None and vmax is None:
                    continue

                unidade = regra.get("unidade", None)
                if not isinstance(unidade, str) or not unidade.strip():
                    unidade = None
                cleaned[kk] = {
                    "valor_min": vmin,
                    "valor_max": vmax,
                    "unidade": unidade,
                    "obrigatorio": bool(regra.get("obrigatorio", True)),
                }

            out = {
                "item": item if isinstance(item, str) and item.strip() else None,
                "tipo_produto": tipo.strip() if isinstance(tipo, str) and tipo.strip() else None,
                "requisitos": cleaned,
            }

            # Se o LLM não trouxe nada mensurável, cai para heurística determinística
            if not out.get("requisitos"):
                heur = self._heuristic_extract(_focus_text_for_hint(edital_text, produto_hint))

                # Heurística pode capturar números de outros itens; filtra por tipo quando possível.
                try:
                    hint = (produto_hint or "").strip().lower()
                    if hint:
                        def _is_battery(h: str) -> bool:
                            return any(w in h for w in ("bateria", "no-break", "nobreak", "vrla", "agm", "ah"))

                        if _is_battery(hint):
                            allowed = {
                                "tensao_v",
                                "capacidade_ah",
                                "garantia_meses",
                                "peso_kg",
                                "comprimento_mm",
                                "largura_mm",
                                "altura_mm",
                            }
                            reqs = heur.get("requisitos") if isinstance(heur, dict) else None
                            if isinstance(reqs, dict) and reqs:
                                heur["requisitos"] = {k: v for k, v in reqs.items() if k in allowed}
                except Exception:
                    pass

                try:
                    heur.setdefault("_meta", {})
                    heur["_meta"].update({"llm_empty": True})
                except Exception:
                    pass
                return heur

            return out

        if isinstance(response, dict):
            return _sanitize(response)

        if isinstance(response, str):
            parsed = self._safe_json_load(response)
            if parsed:
                return _sanitize(parsed)

        # Se o LLM respondeu algo não parseável, evita retornar {} quando há specs óbvias.
        out = self._heuristic_extract(_focus_text_for_hint(edital_text, produto_hint))

        # Mesmo filtro do caso llm_empty
        try:
            hint = (produto_hint or "").strip().lower()
            if hint:
                def _is_battery(h: str) -> bool:
                    return any(w in h for w in ("bateria", "no-break", "nobreak", "vrla", "agm", "ah"))

                if _is_battery(hint):
                    allowed = {
                        "tensao_v",
                        "capacidade_ah",
                        "garantia_meses",
                        "peso_kg",
                        "comprimento_mm",
                        "largura_mm",
                        "altura_mm",
                    }
                    reqs = out.get("requisitos") if isinstance(out, dict) else None
                    if isinstance(reqs, dict) and reqs:
                        out["requisitos"] = {k: v for k, v in reqs.items() if k in allowed}
        except Exception:
            pass

        try:
            out.setdefault("_meta", {})
            out["_meta"].update({"llm_unparseable": True})
        except Exception:
            pass
        return out
