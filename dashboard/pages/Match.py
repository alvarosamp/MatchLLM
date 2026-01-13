import os
import json
import io
import re
import time
import zipfile
import hashlib
import sys
from pathlib import Path

import streamlit as st


def _ensure_repo_root_on_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "core").is_dir():
            sys.path.insert(0, str(parent))
            return


_ensure_repo_root_on_path()


def _repo_root() -> Path:
    # dashboard/pages/Match.py -> dashboard/pages -> dashboard -> repo root
    return Path(__file__).resolve().parents[2]

try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)

    # Quando o Streamlit roda local (Windows), o .env do projeto costuma ser o do docker-compose
    # (ex.: DATABASE_URL apontando para host "postgres"). Isso quebra fora do Docker.
    # Mantemos a possibilidade de override pelo ambiente do usuário (override=False) e,
    # se ainda assim estiver apontando para "postgres", caímos no SQLite local removendo a env var.
    try:
        db_url = (os.getenv("DATABASE_URL") or "").strip()
        if db_url and "@postgres:" in db_url and os.name == "nt":
            os.environ.pop("DATABASE_URL", None)
    except Exception:
        pass
except Exception:
    pass

from core.Pipeline.pipeline import MatchPipeline
from core.ocr.extractor import PDFExtractor
from db.session import SessionLocal, init_db
from db.repositories.cache_repo import (
    get_document_cache,
    upsert_document_cache,
    get_match_cache,
    upsert_match_cache,
)
from core.ocr.normalizador import normalize_text, normalize_text_preserve_newlines
from core.utils.emailer import is_valid_email, send_email


UPLOAD_DIR = _repo_root() / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_DIR = _repo_root() / "resultados_e2e_local"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Versão do cache: incremente quando mudar lógica de extração/matching.
# Evita reutilizar resultados antigos persistidos em DB.
CACHE_VERSION = 2


def _safe_filename(name: str) -> str:
    name = (name or "arquivo").strip()
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    return name[:120] or "arquivo"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _settings_signature(payload: dict) -> str:
    # JSON estável -> bom para cache
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _summarize_ocr_meta(meta: object) -> dict:
    d = _normalize_ocr_meta(meta)
    if not isinstance(d, dict):
        return {"method": None, "used_gemini": None, "chars": None, "words": None, "alnum_ratio": None, "errors": None}
    q = d.get("native_quality") or d.get("ocr_quality") or d.get("gemini_quality") or {}
    if not isinstance(q, dict):
        q = {}
    return {
        "method": d.get("method"),
        "used_gemini": d.get("used_gemini"),
        "chars": q.get("chars"),
        "words": q.get("words"),
        "alnum_ratio": q.get("alnum_ratio"),
        "errors": d.get("errors"),
    }


def _client_summary(result: dict) -> dict:
    """Resumo enxuto para o cliente: status, score e o que bateu/não bateu."""
    if not isinstance(result, dict):
        return {
            "status_geral": "ERRO",
            "score_percent": None,
            "atende": [],
            "nao_atende": [],
            "duvida": [],
            "itens": [],
        }

    score = result.get("score") if isinstance(result.get("score"), dict) else {}
    matching = result.get("matching") if isinstance(result.get("matching"), dict) else {}
    edital_json = result.get("edital_json") if isinstance(result.get("edital_json"), dict) else {}
    produto_json = result.get("produto_json") if isinstance(result.get("produto_json"), dict) else {}
    justificativas = result.get("justificativas") if isinstance(result.get("justificativas"), dict) else {}

    reqs = edital_json.get("requisitos") if isinstance(edital_json.get("requisitos"), dict) else {}
    attrs = produto_json.get("atributos") if isinstance(produto_json.get("atributos"), dict) else {}

    atende: list[str] = []
    nao_atende: list[str] = []
    duvida: list[str] = []

    for k, stt in matching.items():
        if stt == "ATENDE":
            atende.append(k)
        elif stt == "NAO_ATENDE":
            nao_atende.append(k)
        else:
            duvida.append(k)

    atende.sort()
    nao_atende.sort()
    duvida.sort()

    # Regra de status para o cliente (pedido):
    # - Se 2+ itens baterem => APROVADO
    # - Se 1 item bater e não for principal => DUVIDOSO
    # - Se nenhum item bater => REPROVADO
    # Observação: para baterias/no-break, por padrão os itens principais são tensao_v e capacidade_ah.
    def _parse_principais() -> list[str]:
        raw = str(os.getenv("IMPORTANT_REQUIREMENTS", "") or "").strip()
        if not raw:
            return []
        raw = raw.replace(";", ",")
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            parts = [p.strip() for p in raw.split() if p.strip()]
        seen: set[str] = set()
        out: list[str] = []
        for k in parts:
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out

    tipo_produto = str(produto_json.get("tipo_produto") or "").strip().lower()
    nome_produto = str(produto_json.get("nome") or "").strip().lower()
    is_battery = any(w in (tipo_produto + " " + nome_produto) for w in ("bateria", "no-break", "nobreak", "vrla", "agm"))

    principais = _parse_principais()
    if not principais and is_battery:
        principais = ["tensao_v", "capacidade_ah"]

    # contabiliza apenas requisitos presentes no edital
    atende_reqs = [k for k in reqs.keys() if matching.get(k) == "ATENDE"]
    status_cliente: str
    if len(atende_reqs) >= 2:
        status_cliente = "APROVADO"
    elif len(atende_reqs) == 0:
        status_cliente = "REPROVADO"
    else:
        unico = atende_reqs[0]
        status_cliente = "APROVADO" if (unico in principais) else "DUVIDOSO"

    itens: list[dict] = []
    for k in sorted(reqs.keys()):
        req_obj = reqs.get(k) if isinstance(reqs.get(k), dict) else {}
        prod_obj = attrs.get(k) if isinstance(attrs.get(k), dict) else {}
        itens.append(
            {
                "chave": k,
                "status": matching.get(k),
                "obrigatorio": req_obj.get("obrigatorio"),
                "requisito": {
                    "valor": req_obj.get("valor"),
                    "valor_min": req_obj.get("valor_min"),
                    "valor_max": req_obj.get("valor_max"),
                    "unidade": req_obj.get("unidade"),
                },
                "produto": {
                    "valor": prod_obj.get("valor"),
                    "unidade": prod_obj.get("unidade"),
                },
                "justificativa": justificativas.get(k),
            }
        )

    return {
        "status_geral": status_cliente,
        "score_percent": score.get("score_percent"),
        "obrigatorios_atende": score.get("obrigatorios_atende"),
        "obrigatorios_total": score.get("obrigatorios_total"),
        "obrigatorios_nao_atende": score.get("obrigatorios_nao_atende"),
        "obrigatorios_duvida": score.get("obrigatorios_duvida"),
        "principais": principais,
        "atende": atende,
        "nao_atende": nao_atende,
        "duvida": duvida,
        "itens": itens,
    }


@st.cache_resource
def _get_pipeline(
    embed_model: str,
    top_k_edital_chunks: int,
    enable_justification: bool,
    llm_model: str | None,
) -> MatchPipeline:
    return MatchPipeline(
        embed_model=embed_model,
        top_k_edital_chunks=top_k_edital_chunks,
        enable_justification=enable_justification,
        llm_model=llm_model,
    )


st.title("Match (PDF do Edital x PDF do Produto)")
st.caption("Fluxo guiado: envie os dois PDFs, clique em Executar, revise o resultado e baixe o JSON.")

with st.expander("Diagnóstico (paths)"):
    st.write({
        "repo_root": str(_repo_root()),
        "upload_dir": str(UPLOAD_DIR),
        "results_dir": str(RESULTS_DIR),
    })

st.info(
    "Na primeira execução pode demorar mais (download do modelo de embeddings).\n"
    "Se o LLM estiver habilitado, confirme que o Ollama está rodando (por padrão: http://localhost:11434)."
)

col1, col2 = st.columns(2)
with col1:
    edital_pdfs = st.file_uploader(
        "1) Arquivos dos Editais (PDF ou TXT; pode enviar vários)",
        type=["pdf", "txt"],
        accept_multiple_files=True,
    )
with col2:
    produto_pdfs = st.file_uploader(
        "2) Arquivos dos Produtos (datasheets; PDF ou TXT; pode enviar vários)",
        type=["pdf", "txt"],
        accept_multiple_files=True,
    )


def _decode_text_bytes(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="ignore")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text or "", encoding="utf-8", errors="ignore")


def _coerce_json_dict(value: object) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _normalize_ocr_meta(meta: object) -> dict | None:
    d = _coerce_json_dict(meta)
    if d is not None:
        return d
    return meta if isinstance(meta, dict) else None


def _meta_used_gemini(meta: object) -> bool:
    d = _normalize_ocr_meta(meta)
    if not isinstance(d, dict):
        return False
    return bool(d.get("used_gemini") or d.get("method") in {"gemini", "gemini_forced"})


def _needs_refresh_produto(produto_json: object) -> bool:
    if not isinstance(produto_json, dict):
        return True
    attrs = produto_json.get("atributos")
    return not isinstance(attrs, dict) or len(attrs) == 0


def _needs_refresh_edital(edital_json: object) -> bool:
    if not isinstance(edital_json, dict):
        return True
    reqs = edital_json.get("requisitos")
    return not isinstance(reqs, dict) or len(reqs) == 0


def _set_force_gemini_ocr(enabled: bool) -> None:
    os.environ["OCR_FORCE_GEMINI"] = "1" if enabled else "0"


def _pdf_extract(extractor: object, pdf_path: str, label: str | None) -> str:
    """Compatibilidade: evita quebrar quando o processo está com PDFExtractor antigo.

    Tenta chamar com `log_label=...` e faz fallback para `extract(path)`.
    """
    try:
        return extractor.extract(pdf_path, log_label=label)  # type: ignore[attr-defined]
    except TypeError:
        return extractor.extract(pdf_path)  # type: ignore[attr-defined]


def _ocr_to_zip(
    extractor: PDFExtractor,
    files: list[dict],
    doc_type: str,
) -> tuple[bytes, list[dict]]:
    """Extrai texto de PDFs/TXTs e empacota em ZIP (raw + normalizado)."""
    summary: list[dict] = []
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rec in files:
            src_path: Path = rec["path"]
            orig_name: str = rec["orig"]
            sha: str = rec["sha"]

            try:
                if src_path.suffix.lower() == ".txt":
                    text_raw = _decode_text_bytes(rec["bytes"])
                    ocr_meta = None
                else:
                    text_raw = _pdf_extract(extractor, str(src_path), doc_type)
                    ocr_meta = _normalize_ocr_meta(getattr(extractor, "last_meta", None))

                if doc_type == "edital":
                    text_norm = normalize_text_preserve_newlines(text_raw or "")
                else:
                    text_norm = normalize_text(text_raw or "")

                base = _safe_filename(f"{doc_type}__{Path(orig_name).stem}")
                zf.writestr(f"texto_raw__{base}.txt", text_raw or "")
                zf.writestr(f"texto_norm__{base}.txt", text_norm or "")

                summary.append(
                    {
                        "tipo": doc_type,
                        "arquivo": orig_name,
                        "sha256": sha,
                        "chars_raw": len(text_raw or ""),
                        "chars_norm": len(text_norm or ""),
                        "ocr_meta": ocr_meta,
                    }
                )
            except Exception as e:
                summary.append(
                    {
                        "tipo": doc_type,
                        "arquivo": orig_name,
                        "sha256": sha,
                        "erro": str(e),
                    }
                )

        zf.writestr("ocr_resumo.json", json.dumps(summary, ensure_ascii=False, indent=2))

    zip_buf.seek(0)
    return zip_buf.getvalue(), summary

with st.expander("Configurações (opcional)"):
    top_k = st.slider("Trechos do edital usados (top_k)", min_value=3, max_value=25, value=10, step=1)
    enable_justification = st.checkbox("Gerar justificativas via LLM", value=True)
    llm_model = st.text_input("Modelo do LLM (opcional)", value="")
    llm_timeout = st.number_input(
        "Timeout do LLM (segundos)",
        min_value=0,
        value=int(float(os.getenv("LLM_TIMEOUT_SECONDS", "600") or 600)),
        step=30,
        help="0 = sem timeout. Aumente se o Ollama estiver demorando para responder.",
    )
    embed_model = st.text_input("Modelo de embeddings", value="intfloat/e5-base-v2")
    extract_strategy = st.selectbox(
        "Estratégia de extração do edital",
        options=["rag_then_full", "rag", "fullscan"],
        index=0,
        help="rag_then_full = tenta RAG e, se não extrair nada, faz fullscan como fallback.",
    )
    save_text = st.checkbox("Salvar textos extraídos (debug)", value=False)
    out_name = st.text_input("Nome do arquivo de saída", value="resultado_final.json")

    gemini_key_present = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    force_gemini_ocr = st.checkbox(
        "Forçar OCR Gemini (se houver chave)",
        value=gemini_key_present,
        help="Se marcado, PDFs serão extraídos via Gemini OCR sempre que possível.",
    )

    always_ocr_edital = st.checkbox(
        "Sempre refazer OCR do edital ao executar",
        value=True,
        help="Ao clicar em 'Executar Match', sempre refaz o OCR/texto do edital (1x por edital nesta execução) e re-extrai o JSON do edital a partir desse texto.",
    )

    recipient_email = st.text_input("Email para receber os resultados (opcional)", value="")

    st.caption(
        "Dica: se o edital for muito grande e o RAG não achar requisitos, teste 'fullscan' (mais lento)."
    )


btn1, btn2 = st.columns(2)
with btn1:
    ocr_clicked = st.button("OCR")
with btn2:
    run_clicked = st.button("Executar Match", type="primary")


if ocr_clicked:
    if not edital_pdfs and not produto_pdfs:
        st.error("Envie ao menos 1 arquivo antes de rodar OCR.")
        st.stop()

    ts_ocr = time.strftime("%Y%m%d_%H%M%S")

    saved_editais_ocr: list[dict] = []
    for uf in (edital_pdfs or []):
        b = uf.getvalue()
        sha = _sha256_bytes(b)
        name = f"{ts_ocr}__{_safe_filename(uf.name)}"
        path = UPLOAD_DIR / name
        path.write_bytes(b)
        saved_editais_ocr.append({"orig": uf.name, "path": path, "sha": sha, "bytes": b})

    saved_produtos_ocr: list[dict] = []
    for uf in (produto_pdfs or []):
        b = uf.getvalue()
        sha = _sha256_bytes(b)
        name = f"{ts_ocr}__{_safe_filename(uf.name)}"
        path = UPLOAD_DIR / name
        path.write_bytes(b)
        saved_produtos_ocr.append({"orig": uf.name, "path": path, "sha": sha, "bytes": b})

    _set_force_gemini_ocr(bool(force_gemini_ocr and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))))
    extractor = PDFExtractor()

    zip_parts: list[tuple[str, bytes]] = []
    all_summary: list[dict] = []

    if saved_editais_ocr:
        zip_bytes, summary = _ocr_to_zip(extractor, saved_editais_ocr, doc_type="edital")
        zip_parts.append(("editais", zip_bytes))
        all_summary.extend(summary)

    if saved_produtos_ocr:
        zip_bytes, summary = _ocr_to_zip(extractor, saved_produtos_ocr, doc_type="produto")
        zip_parts.append(("produtos", zip_bytes))
        all_summary.extend(summary)

    # Empacota em um ZIP único (cliente baixa 1 arquivo)
    final_zip = io.BytesIO()
    with zipfile.ZipFile(final_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ocr_resumo.json", json.dumps(all_summary, ensure_ascii=False, indent=2))
        for part_name, part_zip_bytes in zip_parts:
            with zipfile.ZipFile(io.BytesIO(part_zip_bytes), mode="r") as zpart:
                for member in zpart.infolist():
                    zf.writestr(f"{part_name}/{member.filename}", zpart.read(member.filename))
    final_zip.seek(0)

    st.subheader("OCR concluído")
    st.dataframe(all_summary, use_container_width=True)
    st.download_button(
        "Baixar textos (ZIP)",
        data=final_zip,
        file_name=_safe_filename(f"ocr_textos_{ts_ocr}.zip"),
        mime="application/zip",
    )

    with st.expander("Prévia (primeiros 2k chars)"):
        for rec in all_summary[:10]:
            st.write(f"{rec.get('tipo')}: {rec.get('arquivo')}")
            # não temos o texto aqui; a prévia é intencionalmente só do resumo
            st.json(rec)

if run_clicked:
    if not edital_pdfs or not produto_pdfs:
        st.error("Envie pelo menos 1 edital e 1 produto antes de executar.")
        st.stop()

    # Aplica timeout escolhido antes de qualquer chamada ao LLM
    try:
        os.environ["LLM_TIMEOUT_SECONDS"] = str(int(llm_timeout))
    except Exception:
        pass

    _set_force_gemini_ocr(bool(force_gemini_ocr and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))))

    total_runs = len(edital_pdfs) * len(produto_pdfs)
    if total_runs > 50:
        st.warning(
            f"Você selecionou {len(edital_pdfs)} editais e {len(produto_pdfs)} produtos "
            f"({total_runs} execuções). Isso pode demorar bastante."
        )

    # Garante tabelas do cache
    init_db()
    db = SessionLocal()

    ts = time.strftime("%Y%m%d_%H%M%S")

    saved_editais: list[dict] = []
    for uf in edital_pdfs:
        b = uf.getvalue()
        sha = _sha256_bytes(b)
        name = f"{ts}__{_safe_filename(uf.name)}"
        path = UPLOAD_DIR / name
        path.write_bytes(b)
        saved_editais.append({"orig": uf.name, "path": path, "sha": sha, "bytes": b})

    saved_produtos: list[dict] = []
    for uf in produto_pdfs:
        b = uf.getvalue()
        sha = _sha256_bytes(b)
        name = f"{ts}__{_safe_filename(uf.name)}"
        path = UPLOAD_DIR / name
        path.write_bytes(b)
        saved_produtos.append({"orig": uf.name, "path": path, "sha": sha, "bytes": b})

    os.environ["EDITAL_EXTRACT_STRATEGY"] = str(extract_strategy)
    os.environ["PIPELINE_SAVE_TEXT"] = "1" if save_text else "0"

    pipeline = _get_pipeline(
        embed_model=embed_model.strip() or "intfloat/e5-base-v2",
        top_k_edital_chunks=int(top_k),
        enable_justification=bool(enable_justification),
        llm_model=(llm_model.strip() or None),
    )

    save_local = st.checkbox("Salvar resultados também em resultados_e2e_local", value=True)

    settings = {
        "embed_model": embed_model.strip() or "intfloat/e5-base-v2",
        "top_k": int(top_k),
        "enable_justification": bool(enable_justification),
        "llm_model": (llm_model.strip() or None),
        "extract_strategy": str(extract_strategy),
        "cache_version": int(CACHE_VERSION),
    }
    settings_sig = _settings_signature(settings)

    results: list[dict] = []
    summary_rows: list[dict] = []

    run_logs: list[dict] = []

    refreshed_produtos: set[str] = set()
    refreshed_editais: set[str] = set()

    edital_text_cache: dict[str, dict] = {}
    if always_ocr_edital:
        with st.status("OCR dos editais (pré-processamento)...", expanded=False) as st_ocr:
            ok_count = 0
            empty_count = 0
            err_count = 0
            for edt in saved_editais:
                try:
                    if edt["path"].suffix.lower() == ".txt":
                        edt_text_raw = _decode_text_bytes(edt["bytes"])
                        edt_ocr_meta = None
                    else:
                        edt_text_raw = _pdf_extract(pipeline.pdf, str(edt["path"]), "edital")
                        edt_ocr_meta = _normalize_ocr_meta(getattr(pipeline.pdf, "last_meta", None))
                    edt_text = normalize_text_preserve_newlines(edt_text_raw or "")
                    edital_text_cache[edt["sha"]] = {
                        "text_raw": edt_text_raw or "",
                        "text": edt_text,
                        "ocr_meta": edt_ocr_meta,
                    }

                    is_empty = len((edt_text_raw or "").strip()) < 50
                    if is_empty:
                        empty_count += 1
                    else:
                        ok_count += 1

                    run_logs.append(
                        {
                            "stage": "ocr_edital_pre",
                            "arquivo": edt.get("orig"),
                            "sha256": edt.get("sha"),
                            "chars_raw": len(edt_text_raw or ""),
                            **_summarize_ocr_meta(edt_ocr_meta),
                        }
                    )
                except Exception as e:
                    edital_text_cache[edt["sha"]] = {"text_raw": "", "text": "", "ocr_meta": {"erro": str(e)}}

                    err_count += 1
                    run_logs.append(
                        {
                            "stage": "ocr_edital_pre",
                            "arquivo": edt.get("orig"),
                            "sha256": edt.get("sha"),
                            "erro": str(e),
                        }
                    )

            label = f"OCR dos editais pronto (ok={ok_count}, vazio={empty_count}, erro={err_count})"
            state = "complete" if err_count == 0 else "error"
            st_ocr.update(label=label, state=state)

    progress = st.progress(0)
    done = 0

    with st.status("Executando em lote...", expanded=True) as status:
        for edital in saved_editais:
            for produto in saved_produtos:
                done += 1
                status.update(
                    label=f"({done}/{total_runs}) Edital='{edital['orig']}' x Produto='{produto['orig']}'",
                    state="running",
                )
                progress.progress(int(done * 100 / max(1, total_runs)))

                try:
                    # 1) Cache do resultado completo (par + config)
                    cached_match = None
                    # Se o usuário pediu para sempre refazer OCR/extração do edital,
                    # não faz sentido reaproveitar resultado antigo do match.
                    if not always_ocr_edital:
                        cached_match = get_match_cache(
                            db,
                            edital_sha256=edital["sha"],
                            produto_sha256=produto["sha"],
                            settings_sig=settings_sig,
                        )
                    if cached_match:
                        result = cached_match.result_json
                        result.setdefault("debug", {})
                        result["debug"].update({"cache": {"hit": True, "level": "match"}})
                        try:
                            run_logs.append(
                                {
                                    "stage": "match_cache",
                                    "edital": edital.get("orig"),
                                    "produto": produto.get("orig"),
                                    "settings_sig": settings_sig,
                                    "hit": True,
                                }
                            )
                        except Exception:
                            pass
                    else:
                        # 2) Cache do produto (por hash do PDF)
                        prod_doc = get_document_cache(
                            db,
                            doc_type="produto",
                            sha256=produto["sha"],
                            hint_key=f"v{CACHE_VERSION}",
                        )
                        if prod_doc:
                            produto_json = prod_doc.extracted_json
                            ocr_meta_prod = _normalize_ocr_meta((prod_doc.meta_json or {}).get("ocr"))
                            prod_cache_hit = True
                        else:
                            if produto["path"].suffix.lower() == ".txt":
                                produto_text_raw = _decode_text_bytes(produto["bytes"])
                                ocr_meta_prod = None
                            else:
                                produto_text_raw = _pdf_extract(pipeline.pdf, str(produto["path"]), "produto")
                                ocr_meta_prod = _normalize_ocr_meta(getattr(pipeline.pdf, "last_meta", None))
                            produto_text = normalize_text(produto_text_raw or "")
                            produto_json = pipeline.product_extractor.extract(produto_text)
                            upsert_document_cache(
                                db,
                                doc_type="produto",
                                sha256=produto["sha"],
                                hint_key=f"v{CACHE_VERSION}",
                                original_name=produto["orig"],
                                extracted_json=produto_json,
                                meta_json={"ocr": ocr_meta_prod, "settings": settings},
                            )
                            prod_cache_hit = False

                        # Log do produto
                        try:
                            attrs = produto_json.get("atributos") if isinstance(produto_json, dict) else None
                            run_logs.append(
                                {
                                    "stage": "produto_extract",
                                    "produto": produto.get("orig"),
                                    "sha256": produto.get("sha"),
                                    "cache_hit": bool(prod_cache_hit),
                                    "ocr": _summarize_ocr_meta(ocr_meta_prod),
                                    "attrs_count": len(attrs) if isinstance(attrs, dict) else None,
                                    "llm_error": (produto_json.get("_meta") or {}).get("llm_error") if isinstance(produto_json, dict) else None,
                                }
                            )
                        except Exception:
                            pass

                        # Refresh conservador: se veio vazio do cache ou não usou Gemini com 'forçar' habilitado.
                        force_now = bool(force_gemini_ocr and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")))
                        should_refresh_prod = (
                            produto["sha"] not in refreshed_produtos
                            and produto["path"].suffix.lower() != ".txt"
                            and (_needs_refresh_produto(produto_json) or (force_now and not _meta_used_gemini(ocr_meta_prod)))
                        )
                        if should_refresh_prod:
                            refreshed_produtos.add(produto["sha"])
                            prev_force = os.getenv("OCR_FORCE_GEMINI", "0")
                            try:
                                _set_force_gemini_ocr(True)
                                produto_text_raw = _pdf_extract(pipeline.pdf, str(produto["path"]), "produto")
                                ocr_meta_prod = _normalize_ocr_meta(getattr(pipeline.pdf, "last_meta", None))
                                produto_text = normalize_text(produto_text_raw or "")
                                produto_json_new = pipeline.product_extractor.extract(produto_text)

                                upsert_document_cache(
                                    db,
                                    doc_type="produto",
                                    sha256=produto["sha"],
                                    hint_key=f"v{CACHE_VERSION}",
                                    original_name=produto["orig"],
                                    extracted_json=produto_json_new or {},
                                    meta_json={"ocr": ocr_meta_prod, "settings": settings, "refreshed": True},
                                )
                                if produto_json_new:
                                    produto_json = produto_json_new
                                prod_cache_hit = False
                            finally:
                                _set_force_gemini_ocr(prev_force == "1")

                        # 3) Cache do edital (hash + hint_key)
                        produto_hint = (
                            (produto_json.get("tipo_produto") or "") + " " + (produto_json.get("nome") or "")
                        ).strip() or None
                        hint_key_base = (produto_json.get("tipo_produto") or "").strip().lower() or "generic"
                        hint_key = f"{hint_key_base}|v{CACHE_VERSION}"
                        # Se always_ocr_edital estiver ligado, ignora cache do edital e re-extrai a partir do OCR desta execução.
                        if always_ocr_edital:
                            pre = edital_text_cache.get(edital["sha"], {})
                            edital_text = pre.get("text") or ""
                            ocr_meta_edt = pre.get("ocr_meta")
                            edital_context, selected_chunks = pipeline._build_edital_context(edital_text, produto_hint)
                            extract_strategy_eff = str(extract_strategy).strip().lower()
                            fullscan_debug = {}
                            if extract_strategy_eff == "fullscan":
                                edital_json, fullscan_debug = pipeline._extract_edital_fullscan(edital_text, produto_hint)
                            else:
                                source_text = edital_context if edital_context else edital_text
                                edital_json = pipeline.edital_extractor.extract(source_text, produto_hint=produto_hint)
                                try:
                                    reqs = edital_json.get("requisitos") if isinstance(edital_json, dict) else None
                                    if (
                                        isinstance(reqs, dict)
                                        and len(reqs) == 0
                                        and edital_context
                                        and edital_text
                                        and edital_text != edital_context
                                    ):
                                        edital_json = pipeline.edital_extractor.extract(edital_text, produto_hint=produto_hint)
                                except Exception:
                                    pass

                                try:
                                    reqs2 = edital_json.get("requisitos") if isinstance(edital_json, dict) else None
                                    if extract_strategy_eff == "rag_then_full" and isinstance(reqs2, dict) and len(reqs2) == 0:
                                        edital_json, fullscan_debug = pipeline._extract_edital_fullscan(edital_text, produto_hint)
                                except Exception:
                                    pass

                            edital_json = pipeline._postprocess_edital_json(edital_json, produto_json)

                            # Log da extração do edital
                            try:
                                reqs_now = edital_json.get("requisitos") if isinstance(edital_json, dict) else None
                                run_logs.append(
                                    {
                                        "stage": "edital_extract",
                                        "edital": edital.get("orig"),
                                        "sha256": edital.get("sha"),
                                        "hint_key": hint_key,
                                        "strategy": extract_strategy_eff,
                                        "chunks_usados": len(selected_chunks),
                                        "cache_hit": False,
                                        "ocr": _summarize_ocr_meta(ocr_meta_edt),
                                        "reqs_count": len(reqs_now) if isinstance(reqs_now, dict) else None,
                                    }
                                )
                            except Exception:
                                pass

                            debug = {
                                "ocr_edital": ocr_meta_edt,
                                "edital_chunks_usados": len(selected_chunks),
                                "edital_extract_strategy": extract_strategy_eff,
                                **(fullscan_debug or {}),
                            }
                            upsert_document_cache(
                                db,
                                doc_type="edital",
                                sha256=edital["sha"],
                                hint_key=hint_key,
                                original_name=edital["orig"],
                                extracted_json=edital_json,
                                meta_json={"ocr": ocr_meta_edt, "debug": debug, "settings": settings, "hint_key": hint_key, "refreshed": True},
                            )
                            edt_cache_hit = False
                        else:
                            edt_doc = get_document_cache(
                                db,
                                doc_type="edital",
                                sha256=edital["sha"],
                                hint_key=hint_key,
                            )
                            if edt_doc:
                                edital_json = edt_doc.extracted_json
                                ocr_meta_edt = _normalize_ocr_meta((edt_doc.meta_json or {}).get("ocr"))
                                edt_cache_hit = True
                                debug = (edt_doc.meta_json or {}).get("debug", {})
                            else:
                                if edital["path"].suffix.lower() == ".txt":
                                    edital_text_raw = _decode_text_bytes(edital["bytes"])
                                    ocr_meta_edt = None
                                else:
                                    edital_text_raw = _pdf_extract(pipeline.pdf, str(edital["path"]), "edital")
                                    ocr_meta_edt = _normalize_ocr_meta(getattr(pipeline.pdf, "last_meta", None))
                                edital_text = normalize_text_preserve_newlines(edital_text_raw or "")

                                # Reproduz a lógica do pipeline para extrair requisitos com estratégia escolhida
                                edital_context, selected_chunks = pipeline._build_edital_context(edital_text, produto_hint)
                                extract_strategy_eff = str(extract_strategy).strip().lower()
                                fullscan_debug = {}
                                if extract_strategy_eff == "fullscan":
                                    edital_json, fullscan_debug = pipeline._extract_edital_fullscan(edital_text, produto_hint)
                                else:
                                    source_text = edital_context if edital_context else edital_text
                                    edital_json = pipeline.edital_extractor.extract(source_text, produto_hint=produto_hint)
                                    try:
                                        reqs = edital_json.get("requisitos") if isinstance(edital_json, dict) else None
                                        if (
                                            isinstance(reqs, dict)
                                            and len(reqs) == 0
                                            and edital_context
                                            and edital_text
                                            and edital_text != edital_context
                                        ):
                                            edital_json = pipeline.edital_extractor.extract(edital_text, produto_hint=produto_hint)
                                    except Exception:
                                        pass

                                    try:
                                        reqs2 = edital_json.get("requisitos") if isinstance(edital_json, dict) else None
                                        if extract_strategy_eff == "rag_then_full" and isinstance(reqs2, dict) and len(reqs2) == 0:
                                            edital_json, fullscan_debug = pipeline._extract_edital_fullscan(edital_text, produto_hint)
                                    except Exception:
                                        pass

                                edital_json = pipeline._postprocess_edital_json(edital_json, produto_json)

                                debug = {
                                    "ocr_edital": ocr_meta_edt,
                                    "edital_chunks_usados": len(selected_chunks),
                                    "edital_extract_strategy": extract_strategy_eff,
                                    **(fullscan_debug or {}),
                                }
                                upsert_document_cache(
                                    db,
                                    doc_type="edital",
                                    sha256=edital["sha"],
                                    hint_key=hint_key,
                                    original_name=edital["orig"],
                                    extracted_json=edital_json,
                                    meta_json={"ocr": ocr_meta_edt, "debug": debug, "settings": settings, "hint_key": hint_key},
                                )
                                edt_cache_hit = False

                            try:
                                reqs_now = edital_json.get("requisitos") if isinstance(edital_json, dict) else None
                                run_logs.append(
                                    {
                                        "stage": "edital_extract",
                                        "edital": edital.get("orig"),
                                        "sha256": edital.get("sha"),
                                        "hint_key": hint_key,
                                        "strategy": str(extract_strategy).strip().lower(),
                                        "cache_hit": bool(edt_cache_hit),
                                        "ocr": _summarize_ocr_meta(ocr_meta_edt),
                                        "reqs_count": len(reqs_now) if isinstance(reqs_now, dict) else None,
                                    }
                                )
                            except Exception:
                                pass

                        # Refresh conservador do edital (1x): se veio vazio do cache ou não usou Gemini com 'forçar' habilitado.
                        force_now = bool(force_gemini_ocr and (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")))
                        edt_refresh_key = f"{edital['sha']}|{hint_key}"
                        should_refresh_edt = (
                            edt_refresh_key not in refreshed_editais
                            and edital["path"].suffix.lower() != ".txt"
                            and (_needs_refresh_edital(edital_json) or (force_now and not _meta_used_gemini(ocr_meta_edt)))
                        )
                        if should_refresh_edt:
                            refreshed_editais.add(edt_refresh_key)
                            prev_force = os.getenv("OCR_FORCE_GEMINI", "0")
                            try:
                                _set_force_gemini_ocr(True)
                                edital_text_raw = _pdf_extract(pipeline.pdf, str(edital["path"]), "edital")
                                ocr_meta_edt = _normalize_ocr_meta(getattr(pipeline.pdf, "last_meta", None))
                                edital_text = normalize_text_preserve_newlines(edital_text_raw or "")

                                edital_context, selected_chunks = pipeline._build_edital_context(edital_text, produto_hint)
                                extract_strategy_eff = str(extract_strategy).strip().lower()
                                fullscan_debug = {}
                                if extract_strategy_eff == "fullscan":
                                    edital_json_new, fullscan_debug = pipeline._extract_edital_fullscan(edital_text, produto_hint)
                                else:
                                    source_text = edital_context if edital_context else edital_text
                                    edital_json_new = pipeline.edital_extractor.extract(source_text, produto_hint=produto_hint)
                                    try:
                                        reqs = edital_json_new.get("requisitos") if isinstance(edital_json_new, dict) else None
                                        if (
                                            isinstance(reqs, dict)
                                            and len(reqs) == 0
                                            and edital_context
                                            and edital_text
                                            and edital_text != edital_context
                                        ):
                                            edital_json_new = pipeline.edital_extractor.extract(edital_text, produto_hint=produto_hint)
                                    except Exception:
                                        pass

                                    try:
                                        reqs2 = edital_json_new.get("requisitos") if isinstance(edital_json_new, dict) else None
                                        if extract_strategy_eff == "rag_then_full" and isinstance(reqs2, dict) and len(reqs2) == 0:
                                            edital_json_new, fullscan_debug = pipeline._extract_edital_fullscan(edital_text, produto_hint)
                                    except Exception:
                                        pass

                                edital_json_new = pipeline._postprocess_edital_json(edital_json_new, produto_json)
                                if edital_json_new:
                                    edital_json = edital_json_new

                                debug = {
                                    "ocr_edital": ocr_meta_edt,
                                    "edital_chunks_usados": len(selected_chunks),
                                    "edital_extract_strategy": extract_strategy_eff,
                                    **(fullscan_debug or {}),
                                }
                                upsert_document_cache(
                                    db,
                                    doc_type="edital",
                                    sha256=edital["sha"],
                                    hint_key=hint_key,
                                    original_name=edital["orig"],
                                    extracted_json=edital_json_new or {},
                                    meta_json={
                                        "ocr": ocr_meta_edt,
                                        "debug": debug,
                                        "settings": settings,
                                        "hint_key": hint_key,
                                        "refreshed": True,
                                    },
                                )
                                edt_cache_hit = False
                            finally:
                                _set_force_gemini_ocr(prev_force == "1")

                        # 4) Agora roda só o determinístico + justificativas (sem OCR/extraction)
                        debug2 = {
                            "ocr_edital": ocr_meta_edt,
                            "ocr_produto": ocr_meta_prod,
                            "cache": {
                                "hit": False,
                                "produto": prod_cache_hit,
                                "edital": edt_cache_hit,
                                "hint_key": hint_key,
                            },
                        }
                        try:
                            if isinstance(debug, dict):
                                debug2.update(debug)
                        except Exception:
                            pass

                        result = pipeline.run_with_extracted(
                            edital_json=edital_json,
                            produto_json=produto_json,
                            edital_pdf_path=str(edital["path"]),
                            produto_pdf_path=str(produto["path"]),
                            debug=debug2,
                        )

                        upsert_match_cache(
                            db,
                            edital_sha256=edital["sha"],
                            produto_sha256=produto["sha"],
                            settings_sig=settings_sig,
                            result_json=result,
                            meta_json={"settings": settings},
                        )

                    # Enriquecimento: anexa resumo cliente no próprio result JSON (para baixar 1 arquivo por par).
                    try:
                        if isinstance(result, dict):
                            result["cliente"] = _client_summary(result)
                    except Exception:
                        pass

                    score = result.get("score") if isinstance(result, dict) else {}
                    row = {
                        "edital": edital["orig"],
                        "produto": produto["orig"],
                        "status_geral": score.get("status_geral"),
                        "score_percent": score.get("score_percent"),
                    }
                    results.append(
                        {
                            "edital_file": edital["orig"],
                            "produto_file": produto["orig"],
                            "result": result,
                        }
                    )
                    summary_rows.append(row)

                    if save_local:
                        base_name = (
                            f"resultado__{Path(edital['orig']).stem}__{Path(produto['orig']).stem}.json"
                        )
                        out_path = RESULTS_DIR / _safe_filename(base_name)
                        try:
                            MatchPipeline.save_result(result, str(out_path))
                        except Exception:
                            pass
                except Exception as e:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    summary_rows.append(
                        {
                            "edital": edital["orig"],
                            "produto": produto["orig"],
                            "status_geral": "ERRO",
                            "score_percent": None,
                            "erro": str(e),
                        }
                    )

        status.update(label="Concluído", state="complete")

    st.subheader("Resumo")
    st.dataframe(summary_rows, use_container_width=True)

    # Gera ZIP com todos os resultados (e erros) para o cliente baixar
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "resumo.json",
            json.dumps(summary_rows, ensure_ascii=False, indent=2),
        )

        # Resumo enxuto (cliente)
        resumo_cliente = []
        for rec in results:
            resumo_cliente.append(
                {
                    "edital": rec.get("edital_file"),
                    "produto": rec.get("produto_file"),
                    **_client_summary(rec.get("result") if isinstance(rec, dict) else {}),
                }
            )
        zf.writestr(
            "resumo_cliente.json",
            json.dumps(resumo_cliente, ensure_ascii=False, indent=2),
        )

        for rec in results:
            edital_stem = Path(rec["edital_file"]).stem
            produto_stem = Path(rec["produto_file"]).stem
            fname = _safe_filename(f"resultado__{edital_stem}__{produto_stem}.json")
            zf.writestr(fname, json.dumps(rec["result"], ensure_ascii=False, indent=2))
    zip_buf.seek(0)

    st.subheader("Download")
    st.download_button(
        "Baixar resultados (ZIP)",
        data=zip_buf,
        file_name=_safe_filename(f"resultados_{ts}.zip"),
        mime="application/zip",
    )

    if recipient_email and recipient_email.strip():
        if st.button("Enviar resultados por email"):
            if not is_valid_email(recipient_email):
                st.error("Email inválido.")
            else:
                try:
                    send_email(
                        to_email=recipient_email.strip(),
                        subject=f"MatchLLM - Resultados (ZIP) {ts}",
                        body_text=(
                            "Segue em anexo o ZIP com os resultados do match (inclui resumo.json).\n\n"
                            "Obs.: é necessário configurar SMTP_* no ambiente onde o Streamlit está rodando."
                        ),
                        attachments=[(
                            _safe_filename(f"resultados_{ts}.zip"),
                            zip_buf.getvalue(),
                            "application/zip",
                        )],
                    )
                    st.success("Email enviado com sucesso.")
                except Exception as e:
                    st.error(f"Falha ao enviar email: {e}")

    st.subheader("Resultado (cliente)")
    if results:
        for rec in results:
            edital_file = rec.get("edital_file")
            produto_file = rec.get("produto_file")
            result_obj = rec.get("result") if isinstance(rec, dict) else {}

            resumo = _client_summary(result_obj if isinstance(result_obj, dict) else {})

            st.markdown(f"**{edital_file}  x  {produto_file}**")
            st.write(
                {
                    "status_geral": resumo.get("status_geral"),
                    "score_percent": resumo.get("score_percent"),
                    "obrigatorios_atende/total": f"{resumo.get('obrigatorios_atende')}/{resumo.get('obrigatorios_total')}",
                }
            )

            # Diagnóstico rápido quando vier vazio
            if (resumo.get("obrigatorios_total") in (0, None)) and not (resumo.get("itens") or []):
                dbg = (result_obj or {}).get("debug") if isinstance(result_obj, dict) else {}
                if isinstance(dbg, dict):
                    st.warning(
                        "Nenhum requisito foi extraído para este par (por isso score 0/0). "
                        "Abra 'Logs' abaixo para ver OCR/chunks/extração."
                    )

            cols = st.columns(3)
            with cols[0]:
                st.write("Atendeu")
                st.write(resumo.get("atende") or [])
            with cols[1]:
                st.write("Não atendeu")
                st.write(resumo.get("nao_atende") or [])
            with cols[2]:
                st.write("Dúvida")
                st.write(resumo.get("duvida") or [])

            st.divider()

            # Itens detalhados
            itens = resumo.get("itens") or []
            if itens:
                st.write("Itens (detalhado)")
                st.dataframe(itens, use_container_width=True)
    else:
        st.info("Nenhum resultado gerado (só erros). Veja a tabela de resumo.")

    with st.expander("Logs (OCR/extração/match)"):
        if run_logs:
            st.dataframe(run_logs, use_container_width=True)
            st.download_button(
                "Baixar logs (JSON)",
                data=json.dumps(run_logs, ensure_ascii=False, indent=2),
                file_name=_safe_filename(f"logs_{ts}.json"),
                mime="application/json",
            )
        else:
            st.write("Sem logs nesta execução.")

    try:
        db.close()
    except Exception:
        pass
