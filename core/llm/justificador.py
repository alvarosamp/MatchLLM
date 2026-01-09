import json
import re
import os
from typing import Any, Dict
from core.llm.client import LLMClient


JUSTIFICATION_PROMPT = """
Você é um analista técnico responsável por justificar resultados de conformidade
em processos de licitação pública.

Regras obrigatórias:
- NÃO decida se atende ou não.
- NÃO altere os resultados fornecidos.
- APENAS explique tecnicamente o motivo de cada resultado.
- Use SOMENTE os dados fornecidos nos casos.
- Seja objetivo (1–3 frases por requisito) e inclua números/unidades.
- Se o status for DUVIDA, diga explicitamente qual dado faltou.
- NÃO invente informações.

Casos para justificar (JSON):
{casos}

Saída (JSON estrito, sem markdown):
{
    "justificativas": {
        "<requisito>": "<texto da justificativa>"
    }
}
"""


class JustificationGenerator:
    def __init__(self, model: str | None = None):
        model_eff = model or os.getenv("LLM_MODEL_JUSTIFICADOR") or None
        self.llm = LLMClient(model=model_eff)
        self._llm_unavailable = False
        self._llm_disabled = str(os.getenv("LLM_DISABLE", "0")).lower() in ("1", "true", "yes")

    def _safe_json_load(self, text: str) -> dict | None:
        if "```" in text:
            text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "").strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        try:
            s = text.find("{")
            e = text.rfind("}")
            if s != -1 and e != -1 and e > s:
                return json.loads(text[s:e + 1])
        except Exception:
            pass

        return None

    def generate(
        self,
        produto_json: Dict[str, Any],
        edital_json: Dict[str, Any],
        matching: Dict[str, str],
        score: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        atributos = produto_json.get("atributos") if isinstance(produto_json.get("atributos"), dict) else {}
        reqs = edital_json.get("requisitos") if isinstance(edital_json.get("requisitos"), dict) else {}

        casos = []
        for requisito, status in (matching or {}).items():
            regra = reqs.get(requisito) if isinstance(reqs, dict) else None
            prod_attr = atributos.get(requisito) if isinstance(atributos, dict) else None
            casos.append(
                {
                    "requisito": requisito,
                    "status": status,
                    "regra": regra if isinstance(regra, dict) else None,
                    "produto": prod_attr if isinstance(prod_attr, dict) else None,
                }
            )

        raw = None
        if not (self._llm_disabled or self._llm_unavailable):
            # NÃO usar .format aqui porque o template contém chaves '{' '}' literais do JSON.
            prompt = JUSTIFICATION_PROMPT.replace(
                "{casos}",
                json.dumps(casos, ensure_ascii=False, indent=2),
            )

            try:
                raw = self.llm.generate(prompt)
            except Exception:
                # Não derruba o pipeline: cai no fallback determinístico.
                self._llm_unavailable = True
                raw = None

        if isinstance(raw, dict):
            out = raw
        elif isinstance(raw, str):
            parsed = self._safe_json_load(raw)
            if parsed:
                # Aceita dois formatos:
                # 1) {"justificativas": {...}}
                # 2) {...} (map direto requisito->texto)
                if isinstance(parsed, dict) and "justificativas" in parsed and isinstance(parsed.get("justificativas"), dict):
                    out = parsed
                elif isinstance(parsed, dict) and all(isinstance(k, str) for k in parsed.keys()):
                    expected = set(matching.keys()) if isinstance(matching, dict) else set()
                    if expected and any(k in expected for k in parsed.keys()):
                        out = {"justificativas": parsed}
                    else:
                        out = None
                else:
                    out = None
            else:
                out = None
        else:
            out = None

        if out is None and not (self._llm_disabled or self._llm_unavailable):
            # Retry com prompt mais simples (modelos pequenos às vezes falham no formato do prompt grande)
            try:
                req_keys = list(matching.keys())
                if req_keys:
                    prompt2 = (
                        "Retorne APENAS JSON válido (sem markdown) no formato:\n"
                        "{\n  \"justificativas\": {\n    \"<requisito>\": \"<texto curto e técnico>\"\n  }\n}\n\n"
                        "Regras:\n"
                        "- Use EXATAMENTE as chaves de requisito fornecidas.\n"
                        "- Se faltar dado para justificar, diga explicitamente o que faltou.\n"
                        "- Inclua números e unidades (esperado vs observado) quando houver.\n\n"
                        f"Chaves: {json.dumps(req_keys, ensure_ascii=False)}\n\n"
                        f"Casos (JSON): {json.dumps(casos, ensure_ascii=False)}\n"
                    )
                    raw2 = self.llm.generate(prompt2)
                    if isinstance(raw2, str):
                        parsed2 = self._safe_json_load(raw2)
                        if isinstance(parsed2, dict) and isinstance(parsed2.get("justificativas"), dict):
                            out = parsed2
            except Exception:
                pass

        # Se ainda não tiver, cai no fallback determinístico
        if out is None:
            out = {"justificativas": {}}

        # Normaliza/garante coerência com o matching (evita o LLM contradizer o código).
        just_map = out.get("justificativas") if isinstance(out.get("justificativas"), dict) else {}
        def _fmt_rule(rule: dict | None) -> str:
            if not isinstance(rule, dict):
                return "(regra ausente)"
            vmin = rule.get("valor_min")
            vmax = rule.get("valor_max")
            u = rule.get("unidade")
            if vmin is None and vmax is None:
                return "(regra sem valor numérico)"
            if vmin is not None and vmax is not None and vmin == vmax:
                return f"esperado = {vmin}{(' ' + str(u)) if u else ''}".strip()
            parts = []
            if vmin is not None:
                parts.append(f"esperado >= {vmin}")
            if vmax is not None:
                parts.append(f"esperado <= {vmax}")
            if u:
                parts.append(str(u))
            return " ".join(parts)

        def _fmt_prod(attr: dict | None) -> str:
            if not isinstance(attr, dict):
                return "observado: (atributo ausente no produto)"
            v = attr.get("valor")
            u = attr.get("unidade")
            if v is None:
                return f"observado: (valor ausente){(' ' + str(u)) if u else ''}".strip()
            return f"observado: {v}{(' ' + str(u)) if u else ''}".strip()

        def _fallback_text(req: str, status: str) -> str:
            regra = reqs.get(req) if isinstance(reqs, dict) else None
            prod_attr = atributos.get(req) if isinstance(atributos, dict) else None
            if status == "ATENDE":
                return f"ATENDE pela regra de comparação ({_fmt_rule(regra)}; {_fmt_prod(prod_attr)})."
            if status == "NAO_ATENDE":
                if req not in atributos:
                    return f"NAO_ATENDE porque o produto não informou este atributo ({_fmt_rule(regra)})."
                return f"NAO_ATENDE pela comparação ({_fmt_rule(regra)}; {_fmt_prod(prod_attr)})."
            return f"DUVIDA por informação insuficiente ({_fmt_rule(regra)}; {_fmt_prod(prod_attr)})."

        fixed: Dict[str, str] = {}
        for requisito, status in (matching or {}).items():
            txt = just_map.get(requisito)
            if not isinstance(txt, str) or not txt.strip():
                fixed[requisito] = _fallback_text(requisito, status)
                continue
            low = txt.lower()
            if status == "ATENDE" and ("nao atende" in low or "não atende" in low):
                fixed[requisito] = "Marcado como ATENDE pela regra de comparação; justificativa do modelo estava inconsistente e foi substituída."
            elif status == "NAO_ATENDE" and (" atende" in low and "nao atende" not in low and "não atende" not in low):
                fixed[requisito] = "Marcado como NAO_ATENDE pela regra de comparação; justificativa do modelo estava inconsistente e foi substituída."
            else:
                fixed[requisito] = txt.strip()

        # Sempre adiciona uma justificativa global (LLM quando disponível; fallback determinístico).
        if "_global" not in fixed:
            status_geral = None
            score_percent = None
            key_info = None
            seq_info = None
            if isinstance(score, dict):
                status_geral = score.get("status_geral")
                score_percent = score.get("score_percent")
                key_info = score.get("key_requirements")
                seq_info = score.get("sequence_filter")

            def _fallback_global() -> str:
                parts = []
                if status_geral:
                    parts.append(f"Status geral: {status_geral}.")
                if score_percent is not None:
                    parts.append(f"Score: {score_percent}%." )
                if isinstance(seq_info, dict) and seq_info.get("configured"):
                    parts.append(
                        f"Filtro por sequência: final={seq_info.get('final_status')}, override={seq_info.get('override_applied')}. "
                        f"Presentes: {seq_info.get('present_in_edital')}."
                    )
                # Resume requisitos-chave, se existirem
                if isinstance(key_info, dict) and (key_info.get("present_in_edital") or key_info.get("configured")):
                    present = key_info.get("present_in_edital") or []
                    policy = key_info.get("policy")
                    atende = key_info.get("atende")
                    total = key_info.get("total")
                    nao = key_info.get("nao_atende")
                    duv = key_info.get("duvida")
                    parts.append(
                        f"Requisitos-chave (policy={policy}): {atende}/{total} atende, {nao} não atende, {duv} dúvida. Presentes: {present}."
                    )
                return " ".join([p for p in parts if p]).strip() or "Resumo indisponível."

            global_txt = None
            if not (self._llm_disabled or self._llm_unavailable):
                try:
                    payload = {
                        "status_geral": status_geral,
                        "score_percent": score_percent,
                        "key_requirements": key_info,
                        "matching_counts": {
                            "total": len(matching or {}),
                            "atende": sum(1 for s in (matching or {}).values() if s == "ATENDE"),
                            "nao_atende": sum(1 for s in (matching or {}).values() if s == "NAO_ATENDE"),
                            "duvida": sum(1 for s in (matching or {}).values() if s == "DUVIDA"),
                        },
                    }
                    prompt_global = (
                        "Você vai explicar objetivamente o MOTIVO do status final de uma comparação de produto vs edital.\n"
                        "Regras:\n"
                        "- Não invente números/itens que não estejam no JSON.\n"
                        "- Cite os requisitos-chave quando existirem (ex.: tensao_v).\n"
                        "- Produza um texto curto (2–5 frases).\n\n"
                        "Entrada (JSON):\n"
                        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
                        "Saída: retorne APENAS o texto (sem markdown)."
                    )
                    global_txt = self.llm.generate(prompt_global)
                    if isinstance(global_txt, str):
                        global_txt = global_txt.strip()
                    else:
                        global_txt = None
                except Exception:
                    self._llm_unavailable = True
                    global_txt = None

            fixed["_global"] = global_txt if (isinstance(global_txt, str) and global_txt) else _fallback_global()

        return {"justificativas": fixed}
