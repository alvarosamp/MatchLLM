from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from api.auth.deps import get_current_user
from core.llm.client import LLMClient
from core.llm.prompt import MATCH_ITEMS_PROMPT, REQUIREMENTS_PROMPT
from core.pipeline import _chunk_text
from core.ocr.extractor import PDFExtractor
from core.pipeline import processar_datasheet
from db.session import SessionLocal, init_db
from db.repositories.cache_repo import get_document_cache, upsert_document_cache, get_match_cache, upsert_match_cache
from db.repositories.match_repo import create_match
from db.repositories.produto_repo import get_or_create


router = APIRouter(
    prefix="/match",
    tags=["Match"],
    dependencies=[Depends(get_current_user)],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _hash_and_store_upload(upload: UploadFile, *, subdir: str) -> tuple[str, Path]:
    """Store the uploaded file on disk and return (sha256, path).

    Uses a temp file first, then renames to <sha256>.pdf to deduplicate across runs.
    """
    dest_dir = UPLOAD_DIR / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)

    tmp_path = dest_dir / f"tmp_{uuid.uuid4().hex}.pdf"
    hasher = hashlib.sha256()
    upload.file.seek(0)
    with open(tmp_path, "wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            out.write(chunk)
    sha = hasher.hexdigest()
    final_path = dest_dir / f"{sha}.pdf"
    if final_path.exists():
        try:
            tmp_path.unlink(missing_ok=True)  # py3.8+ on Windows supports missing_ok
        except Exception:
            pass
        return sha, final_path
    tmp_path.replace(final_path)
    return sha, final_path


def _extract_edital_requirements_from_pdf(pdf_path: str, *, model: str | None) -> dict:
    extractor = PDFExtractor()

    texto = ""
    extraction_log: list[str] = []
    try:
        texto_native = extractor.extract_text_native(str(pdf_path))
        if texto_native:
            texto = texto_native
            extraction_log.append("native_text")
        else:
            extraction_log.append("native_no_text")
    except Exception as e:
        extraction_log.append(f"native_error: {e}")

    if not texto:
        try:
            texto_ocr = extractor.extract_text_ocr(str(pdf_path))
            texto = texto_ocr or ""
            extraction_log.append("ocr_doctr")
        except Exception as e:
            extraction_log.append(f"ocr_error: {e}")
            try:
                texto_gemini = extractor.extract_text_gemini(str(pdf_path))
                texto = texto_gemini or ""
                extraction_log.append("gemini")
            except Exception as e2:
                extraction_log.append(f"gemini_error: {e2}")
                texto = ""

    chunks = _chunk_text(texto) if texto else []
    preview = "\n\n".join(chunks[:20]) if chunks else ""
    if not preview:
        return {"items": [], "_meta": {"extraction_log": extraction_log, "total_chunks": 0}}

    llm = LLMClient(model=model)
    prompt = REQUIREMENTS_PROMPT.format(edital=preview)
    raw = llm.generate(prompt)
    try:
        reqs = json.loads(raw)
    except Exception:
        reqs = []

    merged = {"items": []}
    for item in reqs if isinstance(reqs, list) else [reqs]:
        if not isinstance(item, dict):
            continue
        merged["items"].append(
            {
                "item_id": item.get("item_id"),
                "titulo": item.get("titulo"),
                "descricao": item.get("descricao"),
                "criterios": item.get("criterios", []),
            }
        )

    merged["_meta"] = {"extraction_log": extraction_log, "total_chunks": len(chunks)}
    return merged


def _match_from_requirements(*, produto_json: dict, requisitos_json: dict, model: str | None) -> object:
    produto_str = json.dumps(produto_json, ensure_ascii=False)
    requisitos_str = json.dumps(requisitos_json, ensure_ascii=False)
    llm = LLMClient(model=model)
    prompt = MATCH_ITEMS_PROMPT.format(produto=produto_str, requisitos=requisitos_str)
    raw = llm.generate(prompt)
    try:
        return json.loads(raw)
    except Exception:
        return {"error": "LLM retornou resultado não-JSON", "raw": raw}


@router.post("/run")
async def run_match(
    datasheet: UploadFile = File(...),
    editais: List[UploadFile] = File(...),
    consulta: str = Form(""),
    model: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """1-clique: recebe PDFs (datasheet + editais), faz OCR/extração com cache e roda match.

    - Cache de OCR/extração em `document_cache`
    - Cache de resultado em `match_cache`
    """
    init_db()

    # ---- Datasheet: OCR/specs + cache ----
    if not (datasheet.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Datasheet precisa ser PDF")

    produto_sha, datasheet_path = _hash_and_store_upload(datasheet, subdir="datasheet")
    datasheet_cache = get_document_cache(db, doc_type="datasheet", sha256=produto_sha, hint_key=None)
    datasheet_cache_hit = datasheet_cache is not None

    if datasheet_cache_hit:
        produto_payload = datasheet_cache.extracted_json
        produto_meta = datasheet_cache.meta_json or {}
    else:
        fabricante = (Path(datasheet.filename or "").stem or "desconhecido")
        modelo = fabricante
        out = processar_datasheet(str(datasheet_path), fabricante, modelo, None, db)
        # Normaliza o formato esperado pelo front: {nome, atributos}
        produto_payload = {
            "nome": f"{out.get('fabricante', '')} {out.get('modelo', '')}".strip() or (datasheet.filename or "Produto"),
            "atributos": out.get("specs") or {},
        }

        # também garante persistência em `produtos` (para histórico/consultas)
        try:
            prod_rec = get_or_create(db, nome=produto_payload["nome"], atributos_json=produto_payload["atributos"])
            produto_meta = {"produto_id": int(prod_rec.id)}
        except Exception:
            produto_meta = {}

        upsert_document_cache(
            db,
            doc_type="datasheet",
            sha256=produto_sha,
            hint_key=None,
            original_name=datasheet.filename,
            extracted_json=produto_payload,
            meta_json=produto_meta,
        )

    # ---- Editais: OCR/requisitos + cache ----
    results = []
    edital_summaries = []

    settings_sig = json.dumps(
        {
            "consulta": consulta or "",
            "model": (model or "").strip() or None,
            "prompt": "MATCH_ITEMS_PROMPT_v1",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    req_hint_key = json.dumps(
        {"model": (model or "").strip() or None, "prompt": "REQUIREMENTS_PROMPT_v1"},
        ensure_ascii=False,
        sort_keys=True,
    )

    for edital in editais:
        filename = edital.filename or "edital.pdf"
        if not filename.lower().endswith(".pdf"):
            results.append({"edital_name": filename, "error": "Edital precisa ser PDF"})
            continue

        edital_sha, edital_path = _hash_and_store_upload(edital, subdir="edital")

        cache = get_document_cache(db, doc_type="edital", sha256=edital_sha, hint_key=req_hint_key)
        cache_hit = cache is not None
        if cache_hit:
            requisitos = cache.extracted_json
            req_meta = cache.meta_json or {}
        else:
            requisitos = _extract_edital_requirements_from_pdf(str(edital_path), model=model)
            req_meta = requisitos.get("_meta") if isinstance(requisitos, dict) else {}
            upsert_document_cache(
                db,
                doc_type="edital",
                sha256=edital_sha,
                hint_key=req_hint_key,
                original_name=filename,
                extracted_json=requisitos,
                meta_json=req_meta if isinstance(req_meta, dict) else None,
            )

        # ---- Match cache ----
        cached_match = get_match_cache(db, edital_sha256=edital_sha, produto_sha256=produto_sha, settings_sig=settings_sig)
        match_cache_hit = cached_match is not None
        if match_cache_hit:
            match_result = cached_match.result_json
        else:
            match_result = _match_from_requirements(
                produto_json={"nome": produto_payload.get("nome"), **(produto_payload.get("atributos") or {})},
                requisitos_json=requisitos,
                model=model,
            )
            upsert_match_cache(
                db,
                edital_sha256=edital_sha,
                produto_sha256=produto_sha,
                settings_sig=settings_sig,
                result_json=match_result,
                meta_json={"edital_name": filename, "datasheet_name": datasheet.filename},
            )

        # Persiste também no histórico de matches (best-effort)
        try:
            create_match(
                db,
                edital_id=None,
                produto_id=(produto_meta or {}).get("produto_id"),
                consulta=consulta,
                resultado_llm={
                    "edital_name": filename,
                    "edital_sha256": edital_sha,
                    "produto_sha256": produto_sha,
                    "requisitos": requisitos,
                    "resultado": match_result,
                },
            )
        except Exception:
            pass

        results.append(
            {
                "edital_name": filename,
                "edital_sha256": edital_sha,
                "requisitos_cache_hit": cache_hit,
                "match_cache_hit": match_cache_hit,
                "resultado": match_result,
            }
        )
        edital_summaries.append({"name": filename, "sha256": edital_sha})

    return {
        "consulta": consulta,
        "model": model,
        "email": email,
        "datasheet": {
            "name": datasheet.filename,
            "sha256": produto_sha,
            "cache_hit": datasheet_cache_hit,
        },
        "produto": produto_payload,
        "editais": edital_summaries,
        "results": results,
    }
