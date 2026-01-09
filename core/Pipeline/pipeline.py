import json
import os
from typing import Any, Dict, List, Tuple
from pathlib import Path

from core.ocr.extractor import PDFExtractor
from core.ocr.normalizador import normalize_text, normalize_text_preserve_newlines

from core.preprocess.chunker import chunk_text
from core.preprocess.embeddings import Embedder

from core.preprocess.product_extractor import ProductExtractor
from core.preprocess.editalExtractor import EditalExtractor

from core.match.matching_engine import MatchingEngine
from core.match.scoring import compute_score
from core.llm.justificador import JustificationGenerator


def _cosine_sim_matrix(q_vec, mat):
    # q_vec: (d,), mat: (n, d)
    import numpy as np

    q = q_vec / (np.linalg.norm(q_vec) + 1e-9)
    m = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    return (m @ q).astype(float)


class MatchPipeline:
    """
    Pipeline E2E:
    - OCR + normalização
    - Chunk + embeddings no edital
    - Recupera trechos mais relevantes
    - Extrai JSON produto e JSON edital (requisitos)
    - Matching determinístico
    - Score final
    - Justificativa (LLM) opcional
    """

    def __init__(
        self,
        embed_model: str = "intfloat/e5-base-v2",
        top_k_edital_chunks: int = 10,
        enable_justification: bool = True,
        llm_model: str | None = None,
    ):
        self.pdf = PDFExtractor()
        self.embedder = Embedder(model_name=embed_model)
        self.top_k = int(top_k_edital_chunks)

        self.product_extractor = ProductExtractor()
        self.edital_extractor = EditalExtractor()
        self.engine = MatchingEngine()

        self.enable_justification = bool(enable_justification)
        self.justifier = JustificationGenerator(model=llm_model) if self.enable_justification else None

    def _build_edital_context(self, edital_text: str, produto_hint: str | None) -> Tuple[str, List[str]]:
        """
        Faz RAG simples: seleciona chunks do edital mais relevantes.
        Retorna (contexto_texto, chunks_selecionados)
        """
        max_tokens = int(os.getenv("EDT_CHUNK_MAX_TOKENS", "200"))
        chunks = chunk_text(edital_text, max_tokens=max_tokens)

        # Evita explodir custo/tempo em editais gigantes
        if len(chunks) == 0:
            return "", []

        # Embeddings dos chunks
        chunk_vecs = self.embedder.encode(chunks)

        # Query embedding
        # Query mais "esperta": puxa chunks onde normalmente aparecem os requisitos mensuráveis.
        # Importante porque, se o produto_hint vier vazio, a busca genérica tende a trazer trechos jurídicos.
        base_terms = (
            "requisitos técnicos especificações obrigatórias características técnicas "
            "no mínimo mínimo máximo deverá deve conter "
            "memória ram armazenamento ssd hdd processador cpu ghz núcleo cores "
            "tela polegadas resolução hd full hd 4k "
            "ethernet portas poe usb hdmi wi-fi bluetooth "
            "tensão v corrente a potência w consumo "
            "garantia meses"
        )
        query = f"{base_terms} {produto_hint}".strip() if produto_hint else base_terms
        q_vec = self.embedder.encode([query])[0]

        sims = _cosine_sim_matrix(q_vec, chunk_vecs)
        # pega top_k índices
        idxs = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[: self.top_k]
        selected = [chunks[i] for i in idxs]

        # junta contexto
        context = "\n\n".join(selected)
        return context, selected

    def _merge_requisitos(self, base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        """Merge conservador de requisitos.

        - Mantém o menor valor_min (mais restritivo) e o menor valor_max (mais restritivo)
        - Se unidades divergirem, zera unidade (evita falso positivo)
        - obrigatorio: True se qualquer fonte marcar como obrigatório
        """
        if not isinstance(base, dict):
            base = {}
        if not isinstance(incoming, dict):
            return base

        def _is_spurious_zero(v, unit: str | None) -> bool:
            if v is None:
                return False
            try:
                fv = float(v)
            except Exception:
                return False
            if abs(fv) > 1e-12:
                return False
            u = (unit or "").strip().lower()
            # Para estas unidades, 0 geralmente indica falha de extração (não requisito real).
            return u in ("v", "a", "w", "ah", "kg", "mes", "meses", "mês")

        def _pick_min(a, b, unit: str | None):
            if a is None:
                return b
            if b is None:
                return a
            try:
                if _is_spurious_zero(b, unit) and not _is_spurious_zero(a, unit):
                    return a
                return a if a <= b else b
            except Exception:
                return a

        def _pick_max(a, b, unit: str | None):
            if a is None:
                return b
            if b is None:
                return a
            try:
                if _is_spurious_zero(b, unit) and not _is_spurious_zero(a, unit):
                    return a
                return a if a <= b else b
            except Exception:
                return a

        for k, regra in incoming.items():
            if not isinstance(k, str) or not k.strip():
                continue
            if not isinstance(regra, dict):
                continue

            kk = k.strip()
            cur = base.get(kk)
            if not isinstance(cur, dict):
                cur = {}

            u1 = cur.get("unidade")
            u2 = regra.get("unidade")
            unidade = u1 or u2
            if u1 and u2 and u1 != u2:
                unidade = None

            vmin = _pick_min(cur.get("valor_min"), regra.get("valor_min"), unidade)
            vmax = _pick_max(cur.get("valor_max"), regra.get("valor_max"), unidade)

            obrig = bool(cur.get("obrigatorio", True)) or bool(regra.get("obrigatorio", True))

            base[kk] = {
                "valor_min": vmin,
                "valor_max": vmax,
                "unidade": unidade,
                "obrigatorio": obrig,
            }
        return base

    def _extract_edital_fullscan(self, edital_text: str, produto_hint: str | None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Varre o edital inteiro por janelas/chunks e faz merge dos requisitos.

        Isso evita depender de um único contexto RAG e cobre o PDF todo,
        respeitando o limite de contexto do LLM por chamada.
        """
        max_tokens = int(os.getenv("EDITAL_FULLSCAN_CHUNK_MAX_TOKENS", "220"))
        # 0 = sem limite (lê o edital inteiro)
        max_chunks = int(os.getenv("EDITAL_FULLSCAN_MAX_CHUNKS", "0"))
        # Defaults mais econômicos: menos chamadas ao LLM (mas ainda cobre todos os chunks).
        window = int(os.getenv("EDITAL_FULLSCAN_WINDOW_CHUNKS", "6"))
        stride = int(os.getenv("EDITAL_FULLSCAN_STRIDE_CHUNKS", "6"))
        if window <= 0:
            window = 1
        if stride <= 0:
            stride = 1

        chunks_all = chunk_text(edital_text or "", max_tokens=max_tokens)
        chunks = chunks_all[:max_chunks] if max_chunks > 0 else chunks_all

        merged_reqs: Dict[str, Any] = {}
        llm_calls = 0

        log_path = os.getenv("EDITAL_FULLSCAN_LOG_PATH")
        log_file = None
        try:
            if log_path:
                lp = Path(log_path)
                lp.parent.mkdir(parents=True, exist_ok=True)
                log_file = lp.open("a", encoding="utf-8")
        except Exception:
            log_file = None

        # Varredura por janelas para dar contexto suficiente ao LLM e reduzir número de chamadas.
        # Ex.: window=3, stride=3 => percorre 0-2, 3-5, 6-8, ...
        i = 0
        while i < len(chunks):
            window_chunks = chunks[i : i + window]
            text = "\n\n".join([c for c in window_chunks if c and c.strip()]).strip()
            if text:
                extracted = self.edital_extractor.extract(text, produto_hint=produto_hint)
                llm_calls += 1
                reqs = extracted.get("requisitos") if isinstance(extracted, dict) else None
                if isinstance(reqs, dict) and reqs:
                    merged_reqs = self._merge_requisitos(merged_reqs, reqs)

                if log_file:
                    try:
                        rec = {
                            "window_start": i,
                            "window_end": min(i + window - 1, len(chunks) - 1),
                            "llm_call": llm_calls,
                            "req_keys": sorted(list(reqs.keys())) if isinstance(reqs, dict) else [],
                            "reqs": reqs if isinstance(reqs, dict) else {},
                        }
                        log_file.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        log_file.flush()
                    except Exception:
                        pass
            i += stride

        try:
            if log_file:
                log_file.close()
        except Exception:
            pass

        out = {
            "item": None,
            "tipo_produto": None,
            "requisitos": merged_reqs,
        }
        debug = {
            "fullscan_chunks_total": len(chunks_all),
            "fullscan_chunks_usados": len(chunks),
            "fullscan_llm_calls": llm_calls,
            "fullscan_chunk_max_tokens": max_tokens,
            "fullscan_window_chunks": window,
            "fullscan_stride_chunks": stride,
        }
        return out, debug

    def _postprocess_edital_json(self, edital_json: Dict[str, Any], produto_json: Dict[str, Any]) -> Dict[str, Any]:
        """Limpa/normaliza requisitos do edital para ficarem comparáveis."""
        if not isinstance(edital_json, dict):
            return {"item": None, "tipo_produto": None, "requisitos": {}}

        reqs = edital_json.get("requisitos")
        if not isinstance(reqs, dict) or not reqs:
            edital_json["requisitos"] = {}
            return edital_json

        import re
        try:
            import unicodedata
        except Exception:
            unicodedata = None

        blacklist = (
            "certidao", "certidão", "habilit", "jurid", "juríd", "ata", "registro", "pregao", "pregão",
            "processo", "modalidade", "document", "proposta", "licit", "contrat", "cnd", "icms",
            "trabalh", "aprendiz", "cargos", "debitos", "débito", "fiscal", "tabela", "sessao", "sessão",
        )

        def _canon(s: str) -> str:
            s = (s or "").strip().lower()
            if unicodedata:
                s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
            s = re.sub(r"[^a-z0-9]+", "_", s)
            s = re.sub(r"_+", "_", s).strip("_")
            return s

        # mapa simples de sinônimos -> chave canônica
        synonym_map = {
            "tensao": "tensao_v",
            "voltagem": "tensao_v",
            "tensao_nominal": "tensao_v",
            "corrente": "corrente_a",
            "corrente_maxima": "corrente_a",
            "potencia": "potencia_w",
            "capacidade": "capacidade_ah",
            "capacidade_bateria": "capacidade_ah",
            "peso": "peso_kg",
            "comprimento": "comprimento_mm",
            "largura": "largura_mm",
            "altura": "altura_mm",
            "garantia": "garantia_meses",
            "portas": "portas",
        }

        def _parse_from_text(key: str) -> dict:
            """Tenta inferir valor/unidade quando o LLM colocou números dentro da chave."""
            k = (key or "")
            out: dict = {}
            # 12V
            m = re.search(r"(\d+(?:[\.,]\d+)?)\s*v\b", k, flags=re.IGNORECASE)
            if m:
                v = float(m.group(1).replace(",", "."))
                out["tensao_v"] = {"valor_min": v, "valor_max": v, "unidade": "V"}
            # 7Ah
            m = re.search(r"(\d+(?:[\.,]\d+)?)\s*ah\b", k, flags=re.IGNORECASE)
            if m:
                v = float(m.group(1).replace(",", "."))
                out["capacidade_ah"] = {"valor_min": v, "valor_max": v, "unidade": "Ah"}
            # 2.1 kg
            m = re.search(r"(\d+(?:[\.,]\d+)?)\s*kg\b", k, flags=re.IGNORECASE)
            if m:
                v = float(m.group(1).replace(",", "."))
                out["peso_kg"] = {"valor_min": v, "valor_max": v, "unidade": "kg"}
            # mm
            m = re.search(r"(\d+(?:[\.,]\d+)?)\s*mm\b", k, flags=re.IGNORECASE)
            if m:
                v = float(m.group(1).replace(",", "."))
                out["dimensao_mm"] = {"valor_min": v, "valor_max": v, "unidade": "mm"}
            # meses
            m = re.search(r"(\d{1,3})\s*mes", k, flags=re.IGNORECASE)
            if m:
                v = int(m.group(1))
                out["garantia_meses"] = {"valor_min": v, "valor_max": v, "unidade": "meses"}
            return out

        cleaned: Dict[str, Any] = {}
        for raw_key, rule in reqs.items():
            if not isinstance(raw_key, str) or not raw_key.strip():
                continue
            key0 = raw_key.strip()
            key_l = key0.lower()

            # filtro de itens claramente não técnicos
            if any(b in key_l for b in blacklist):
                continue

            k = _canon(key0)
            # remove chaves muito genéricas que vêm de texto jurídico
            if k in ("descricao", "descrição", "numero", "número", "marca", "modalidade"):
                continue

            k = synonym_map.get(k, k)

            if not isinstance(rule, dict):
                rule = {"valor_min": None, "valor_max": None, "unidade": None, "obrigatorio": True}

            vmin = rule.get("valor_min")
            vmax = rule.get("valor_max")
            unidade = rule.get("unidade")

            # Descarta regras claramente inválidas (ex.: 0.0 Ah/V/W etc.), que costumam vir de falha do LLM.
            try:
                u0 = (unidade or "").strip().lower()
                if vmin is not None and vmax is not None:
                    fvmin = float(vmin)
                    fvmax = float(vmax)
                    if abs(fvmin) < 1e-12 and abs(fvmax) < 1e-12 and u0 in ("v", "a", "w", "ah", "kg", "mes", "meses", "mês"):
                        continue
            except Exception:
                pass

            # Se não vier valor, tenta parsear da chave; se achar múltiplos (ex.: 12V e 7Ah),
            # cria requisitos canônicos separados para permitir matching.
            if vmin is None and vmax is None:
                parsed_map = _parse_from_text(key0)
                if parsed_map:
                    for ck, pv in parsed_map.items():
                        # mapeia dimensões genéricas
                        if ck == "dimensao_mm":
                            # não sabemos qual dimensão; não cria requisito para evitar falso match
                            continue
                        cleaned.setdefault(ck, {
                            "valor_min": None,
                            "valor_max": None,
                            "unidade": None,
                            "obrigatorio": True,
                        })
                        cur = cleaned[ck]
                        cur["valor_min"] = pv.get("valor_min")
                        cur["valor_max"] = pv.get("valor_max")
                        cur["unidade"] = pv.get("unidade")
                        cur["obrigatorio"] = True
                    # Já tratou; não cria o requisito com a chave original
                    continue

            # Se ainda não tiver valor numérico, descarta (evita lixo do LLM)
            if vmin is None and vmax is None:
                continue

            cleaned.setdefault(k, {
                "valor_min": None,
                "valor_max": None,
                "unidade": None,
                "obrigatorio": True,
            })

            # merge conservador
            cur = cleaned[k]
            try:
                if cur.get("valor_min") is None or (vmin is not None and vmin < cur.get("valor_min")):
                    cur["valor_min"] = vmin
            except Exception:
                pass
            try:
                if cur.get("valor_max") is None or (vmax is not None and vmax < cur.get("valor_max")):
                    cur["valor_max"] = vmax
            except Exception:
                pass

            u1 = cur.get("unidade")
            u2 = unidade
            if u1 and u2 and u1 != u2:
                cur["unidade"] = None
            else:
                cur["unidade"] = u1 or u2

            cur["obrigatorio"] = bool(cur.get("obrigatorio", True)) or bool(rule.get("obrigatorio", True))

        edital_json["requisitos"] = cleaned
        return edital_json

    def run(self, edital_pdf_path: str, produto_pdf_path: str) -> Dict[str, Any]:
        # 1) OCR
        edital_text_raw = self.pdf.extract(edital_pdf_path)
        ocr_meta_edital = getattr(self.pdf, "last_meta", None)

        produto_text_raw = self.pdf.extract(produto_pdf_path)
        ocr_meta_produto = getattr(self.pdf, "last_meta", None)

        # 2) Normalização
        # Para edital, preserva \n para manter estrutura (itens/anexos) e melhorar chunking.
        edital_text = normalize_text_preserve_newlines(edital_text_raw or "")
        produto_text = normalize_text(produto_text_raw or "")

        # Debug opcional: salva os textos pós-OCR para você inspecionar qualidade/trechos.
        if str(os.getenv("PIPELINE_SAVE_TEXT", "0")).lower() in ("1", "true", "yes"):
            out_dir = Path(os.getenv("PIPELINE_TEXT_DIR") or "resultados_e2e_local")
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                e_stem = Path(edital_pdf_path).stem
                p_stem = Path(produto_pdf_path).stem
                # RAW (mais útil para inspecionar qualidade de OCR/nativo)
                (out_dir / f"texto_raw__edital__{e_stem}.txt").write_text(edital_text_raw or "", encoding="utf-8")
                (out_dir / f"texto_raw__produto__{p_stem}.txt").write_text(produto_text_raw or "", encoding="utf-8")
                # Normalizado (uma linha só; útil para o pipeline, menos legível)
                (out_dir / f"texto_norm__edital__{e_stem}.txt").write_text(edital_text, encoding="utf-8")
                (out_dir / f"texto_norm__produto__{p_stem}.txt").write_text(produto_text, encoding="utf-8")
            except Exception:
                pass

        # 3) Extrai produto (LLM)
        produto_json = self.product_extractor.extract(produto_text)

        produto_hint = (produto_json.get("tipo_produto") or "") + " " + (produto_json.get("nome") or "")
        produto_hint = produto_hint.strip()
        if not produto_hint:
            # fallback: tenta montar um hint mínimo a partir de alguns atributos comuns
            attrs = produto_json.get("atributos") if isinstance(produto_json.get("atributos"), dict) else {}
            tensao = (attrs.get("tensao_v") or {}).get("valor") if isinstance(attrs.get("tensao_v"), dict) else None
            cap = (attrs.get("capacidade_ah") or {}).get("valor") if isinstance(attrs.get("capacidade_ah"), dict) else None
            if tensao or cap:
                parts = ["bateria", "no-break"]
                if tensao is not None:
                    parts.append(f"{tensao}V")
                if cap is not None:
                    parts.append(f"{cap}Ah")
                produto_hint = " ".join(parts)
        produto_hint = produto_hint.strip() or None

        # 4) RAG simples no edital (reduz tokens)
        edital_context, selected_chunks = self._build_edital_context(edital_text, produto_hint)

        # 5) Extrai requisitos do edital (LLM, mas só no contexto)
        extract_strategy = str(os.getenv("EDITAL_EXTRACT_STRATEGY", "rag_then_full")).strip().lower()
        fullscan_debug: Dict[str, Any] = {}

        if extract_strategy == "fullscan":
            edital_json, fullscan_debug = self._extract_edital_fullscan(edital_text, produto_hint)
        else:
            source_text = edital_context if edital_context else edital_text
            edital_json = self.edital_extractor.extract(source_text, produto_hint=produto_hint)
            # Se o RAG não extraiu nada, tenta texto completo (uma chamada).
            try:
                reqs = edital_json.get("requisitos") if isinstance(edital_json, dict) else None
                if (
                    isinstance(reqs, dict)
                    and len(reqs) == 0
                    and edital_context
                    and edital_text
                    and edital_text != edital_context
                ):
                    edital_json = self.edital_extractor.extract(edital_text, produto_hint=produto_hint)
            except Exception:
                pass

            # Opcional: fullscan como fallback final (cobre o edital todo)
            try:
                reqs2 = edital_json.get("requisitos") if isinstance(edital_json, dict) else None
                if extract_strategy == "rag_then_full" and isinstance(reqs2, dict) and len(reqs2) == 0:
                    edital_json, fullscan_debug = self._extract_edital_fullscan(edital_text, produto_hint)
            except Exception:
                pass

        # Pós-processa para remover lixo (jurídico) e padronizar chaves/valores.
        edital_json = self._postprocess_edital_json(edital_json, produto_json)

        # 6) Matching determinístico
        matching = self.engine.compare(produto_json, edital_json)

        # 7) Score final
        score = compute_score(matching, edital_json)

        # 8) Justificativas (LLM só explica)
        justificativas = {"justificativas": {}}
        if self.enable_justification and self.justifier and matching:
            justificativas = self.justifier.generate(
                produto_json=produto_json,
                edital_json=edital_json,
                matching=matching,
                score=score,
            )
        elif self.enable_justification:
            # Quando não há requisitos extraídos, não há o que justificar por item.
            justificativas = {"justificativas": {"_global": "Nenhum requisito técnico foi extraído do edital; não foi possível justificar o match por item."}}

        return {
            "produto_pdf": produto_pdf_path,
            "edital_pdf": edital_pdf_path,
            "produto_json": produto_json,
            "edital_json": edital_json,
            "matching": matching,
            "score": score,
            "justificativas": justificativas.get("justificativas", {}),
            "debug": {
                "ocr_edital": ocr_meta_edital,
                "ocr_produto": ocr_meta_produto,
                "edital_chunks_total": len(chunk_text(edital_text, max_tokens=400)),
                "edital_chunks_usados": len(selected_chunks),
                "edital_extract_strategy": extract_strategy,
                **(fullscan_debug or {}),
            },
        }

    @staticmethod
    def save_result(result: Dict[str, Any], out_path: str) -> None:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
