import json
import os
import re
import sys
import time
import hashlib
from pathlib import Path

import streamlit as st


def _ensure_repo_root_on_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "core").is_dir():
            sys.path.insert(0, str(parent))
            return


_ensure_repo_root_on_path()

from core.Pipeline.pipeline import MatchPipeline
from core.ocr.extractor import PDFExtractor
from core.ocr.normalizador import normalize_text
from db.session import SessionLocal, init_db
from db.models.cache import DocumentCache
from db.repositories.cache_repo import get_document_cache, upsert_document_cache


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


UPLOAD_DIR = _repo_root() / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    name = (name or "arquivo").strip()
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    return name[:160] or "arquivo"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_text_bytes(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="ignore")


def _load_local_editais() -> list[dict]:
    """Fallback: lista PDFs locais em data/editais (para rodar mesmo sem cache no DB)."""
    editais_dir = _repo_root() / "data" / "editais"
    if not editais_dir.exists():
        return []
    out: list[dict] = []
    for p in sorted(editais_dir.glob("*.pdf")):
        try:
            b = p.read_bytes()
        except Exception:
            continue
        out.append({"path": p, "orig": p.name, "sha": hashlib.sha256(b).hexdigest(), "bytes": b})
    return out


def _get_cached_editais(db) -> list[dict]:
    """Lista os editais já extraídos (JSON) no cache do banco."""
    rows = db.query(DocumentCache).filter(DocumentCache.doc_type == "edital").all()
    out = []
    for r in rows or []:
        try:
            reqs = (r.extracted_json or {}).get("requisitos") if isinstance(r.extracted_json, dict) else None
            out.append(
                {
                    "sha": r.sha256,
                    "hint_key": r.hint_key,
                    "orig": r.original_name or "(sem_nome)",
                    "reqs_count": len(reqs) if isinstance(reqs, dict) else None,
                    "edital_json": r.extracted_json,
                }
            )
        except Exception:
            out.append({"sha": r.sha256, "hint_key": r.hint_key, "orig": r.original_name or "(sem_nome)", "edital_json": {}})
    # ordena: mais requisitos primeiro (tende a ser melhor extração)
    out.sort(key=lambda x: (x.get("reqs_count") or 0), reverse=True)
    return out


st.title("Varredura de Editais (Datasheet → banco de editais)")
st.caption(
    "Você envia um datasheet (PDF/TXT), o sistema extrai o produto e tenta achar editais onde ele é aceito. "
    "A varredura usa o cache do banco quando possível."
)

with st.expander("Como funciona", expanded=False):
    st.markdown(
        "- 1) Faz OCR/extração do datasheet (produto) uma vez.\n"
        "- 2) Carrega todos os **editais já extraídos** no cache do banco (tabela `document_cache`).\n"
        "- 3) Para cada edital, roda o matching determinístico e ranqueia pelo score.\n"
        "\nDica: rode a página **Match** pelo menos 1 vez com alguns editais para popular o cache do banco."
    )

with st.expander("Diagnóstico (paths)"):
    st.write({"repo_root": str(_repo_root()), "upload_dir": str(UPLOAD_DIR)})


# --- Config ---
st.subheader("1) Envie o datasheet")

uploaded = st.file_uploader("Datasheet (PDF ou TXT)", type=["pdf", "txt"], accept_multiple_files=False)

col_a, col_b, col_c = st.columns(3)
with col_a:
    top_n = st.number_input("Mostrar top N", min_value=1, max_value=200, value=20, step=1)
with col_b:
    min_score = st.number_input("Score mínimo (%)", min_value=0, max_value=100, value=0, step=1)
with col_c:
    enable_justification = st.checkbox("Gerar justificativas (mais lento)", value=False)

use_local_fallback = st.checkbox(
    "Se DB não tiver editais, usar PDFs locais em data/editais (mais lento)",
    value=True,
)


def _extract_produto_from_upload(db, pipeline: MatchPipeline, extractor: PDFExtractor, uploaded_file) -> tuple[dict, dict]:
    """Extrai produto_json do upload e persiste/usa cache por sha."""
    raw_bytes = uploaded_file.getvalue()
    sha = _sha256_bytes(raw_bytes)
    hint_key = "v2"  # compatível com CACHE_VERSION do Match.py (evita duplicar demais)

    cached = get_document_cache(db, doc_type="produto", sha256=sha, hint_key=hint_key)
    if cached:
        produto_json = cached.extracted_json if isinstance(cached.extracted_json, dict) else {}
        meta = (cached.meta_json or {}) if isinstance(cached.meta_json, dict) else {}
        return produto_json, {"sha256": sha, "cache_hit": True, **meta}

    # salva upload em disco (auditoria)
    dest = UPLOAD_DIR / _safe_filename(uploaded_file.name)
    dest.write_bytes(raw_bytes)

    if dest.suffix.lower() == ".txt":
        text_raw = _decode_text_bytes(raw_bytes)
    else:
        text_raw = extractor.extract(str(dest), log_label="produto")
    produto_text = normalize_text(text_raw or "")
    produto_json = pipeline.product_extractor.extract(produto_text)

    upsert_document_cache(
        db,
        doc_type="produto",
        sha256=sha,
        hint_key=hint_key,
        original_name=uploaded_file.name,
        extracted_json=produto_json if isinstance(produto_json, dict) else {},
        meta_json={"ocr": getattr(extractor, "last_meta", None)},
    )
    return (produto_json if isinstance(produto_json, dict) else {}), {"sha256": sha, "cache_hit": False}


if uploaded and st.button("2) Varrer banco de editais"):
    init_db()
    db = SessionLocal()
    started = time.time()
    try:
        pipeline = MatchPipeline(enable_justification=bool(enable_justification))
        extractor = PDFExtractor()

        produto_json, prod_meta = _extract_produto_from_upload(db, pipeline, extractor, uploaded)
        st.success("Produto extraído")
        with st.expander("Produto (JSON)", expanded=False):
            st.json(produto_json)

        cached_editais = _get_cached_editais(db)
        if not cached_editais:
            st.warning("Nenhum edital extraído encontrado no cache do banco.")
            if use_local_fallback:
                st.info("Usando PDFs locais em data/editais como fallback (vai extrair requisitos agora).")
                local_editais = _load_local_editais()
                if not local_editais:
                    st.error("Não encontrei PDFs em data/editais.")
                    st.stop()

                # para o fallback local, precisamos extrair edital_json para cada PDF
                cached_editais = []
                for edt in local_editais:
                    # hint_key depende do tipo do produto; usamos o mesmo esquema do Match.py, mas simplificado
                    hint_key_base = (produto_json.get("tipo_produto") or "").strip().lower() or "generic"
                    hint_key = f"{hint_key_base}|v2"
                    doc = get_document_cache(db, doc_type="edital", sha256=edt["sha"], hint_key=hint_key)
                    if doc:
                        cached_editais.append(
                            {
                                "sha": doc.sha256,
                                "hint_key": doc.hint_key,
                                "orig": doc.original_name or edt["orig"],
                                "reqs_count": len((doc.extracted_json or {}).get("requisitos") or {}),
                                "edital_json": doc.extracted_json,
                            }
                        )
                        continue

                    # extrai texto + requisitos
                    texto_raw = extractor.extract(str(edt["path"]), log_label="edital")
                    from core.ocr.normalizador import normalize_text_preserve_newlines

                    edital_text = normalize_text_preserve_newlines(texto_raw or "")
                    produto_hint = ((produto_json.get("tipo_produto") or "") + " " + (produto_json.get("nome") or "")).strip() or None

                    # usa estratégia padrão do MatchPipeline
                    edital_context, _ = pipeline._build_edital_context(edital_text, produto_hint)
                    source = edital_context if edital_context else edital_text
                    edital_json = pipeline.edital_extractor.extract(source, produto_hint=produto_hint)
                    edital_json = pipeline._postprocess_edital_json(edital_json, produto_json)

                    upsert_document_cache(
                        db,
                        doc_type="edital",
                        sha256=edt["sha"],
                        hint_key=hint_key,
                        original_name=edt["orig"],
                        extracted_json=edital_json if isinstance(edital_json, dict) else {},
                        meta_json={"ocr": getattr(extractor, "last_meta", None), "hint_key": hint_key},
                    )
                    reqs = (edital_json or {}).get("requisitos") if isinstance(edital_json, dict) else None
                    cached_editais.append(
                        {
                            "sha": edt["sha"],
                            "hint_key": hint_key,
                            "orig": edt["orig"],
                            "reqs_count": len(reqs) if isinstance(reqs, dict) else None,
                            "edital_json": edital_json,
                        }
                    )

        if not cached_editais:
            st.error("Ainda não há editais para varrer.")
            st.stop()

        st.subheader("2) Resultados")
        st.caption(f"Editais no pool: {len(cached_editais)}")

        rows = []
        details = []
        prog = st.progress(0)
        for i, edt in enumerate(cached_editais, start=1):
            try:
                res = pipeline.run_with_extracted(
                    edital_json=edt.get("edital_json") or {},
                    produto_json=produto_json,
                    edital_pdf_path=None,
                    produto_pdf_path=None,
                    debug={"source": "document_cache", "edital_sha256": edt.get("sha"), "edital_hint_key": edt.get("hint_key")},
                )
                score = res.get("score") if isinstance(res, dict) else {}
                if not isinstance(score, dict):
                    score = {}
                score_percent = score.get("score_percent")
                rows.append(
                    {
                        "edital": edt.get("orig"),
                        "hint_key": edt.get("hint_key"),
                        "score_percent": score_percent,
                        "status": score.get("status_geral"),
                        "obrigatorios_atende": score.get("obrigatorios_atende"),
                        "obrigatorios_total": score.get("obrigatorios_total"),
                        "sha256": edt.get("sha"),
                    }
                )
                details.append({"edital": edt.get("orig"), "sha256": edt.get("sha"), "result": res})
            except Exception as e:
                rows.append({"edital": edt.get("orig"), "hint_key": edt.get("hint_key"), "erro": str(e), "sha256": edt.get("sha")})

            prog.progress(int(i * 100 / max(1, len(cached_editais))))

        # ordena por score desc
        def _score_val(r: dict) -> float:
            try:
                v = r.get("score_percent")
                return float(v) if v is not None else -1.0
            except Exception:
                return -1.0

        rows_sorted = sorted(rows, key=_score_val, reverse=True)
        filtered = [r for r in rows_sorted if (r.get("score_percent") is None or r.get("score_percent") >= min_score)]

        st.dataframe(filtered[: int(top_n)], use_container_width=True)

        st.subheader("3) Detalhes")
        shown = 0
        for r in filtered:
            if shown >= int(top_n):
                break
            sha = r.get("sha256")
            det = next((d for d in details if d.get("sha256") == sha), None)
            if not det:
                continue
            shown += 1
            res = det.get("result")
            score = res.get("score") if isinstance(res, dict) else {}
            if not isinstance(score, dict):
                score = {}
            title = f"{det.get('edital')}  | score={score.get('score_percent')}% | status={score.get('status_geral')}"
            with st.expander(title, expanded=False):
                st.json(
                    {
                        "edital": det.get("edital"),
                        "hint_key": r.get("hint_key"),
                        "score": score,
                        "matching": res.get("matching") if isinstance(res, dict) else None,
                        "justificativas": res.get("justificativas") if isinstance(res, dict) else None,
                    }
                )

        elapsed = time.time() - started
        st.caption(f"Concluído em {elapsed:.1f}s | produto_sha={prod_meta.get('sha256')} | cache_hit={prod_meta.get('cache_hit')}")

        # Download do resumo
        payload = {
            "produto": {"orig": uploaded.name, "sha256": prod_meta.get("sha256"), "produto_json": produto_json},
            "resultados": rows_sorted,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        st.download_button(
            "Baixar resumo (JSON)",
            data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="scan_editais_resumo.json",
            mime="application/json",
        )
    finally:
        try:
            db.close()
        except Exception:
            pass
