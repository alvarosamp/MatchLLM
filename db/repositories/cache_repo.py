from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from db.models.cache import DocumentCache, MatchCache


def get_document_cache(
    db: Session,
    *,
    doc_type: str,
    sha256: str,
    hint_key: str | None = None,
) -> DocumentCache | None:
    q = db.query(DocumentCache).filter_by(doc_type=doc_type, sha256=sha256)
    if hint_key is None:
        q = q.filter(DocumentCache.hint_key.is_(None))
    else:
        q = q.filter_by(hint_key=hint_key)
    return q.first()


def upsert_document_cache(
    db: Session,
    *,
    doc_type: str,
    sha256: str,
    extracted_json: Any,
    hint_key: str | None = None,
    original_name: str | None = None,
    meta_json: Optional[dict] = None,
) -> DocumentCache:
    rec = get_document_cache(db, doc_type=doc_type, sha256=sha256, hint_key=hint_key)
    if rec:
        rec.extracted_json = extracted_json
        if original_name:
            rec.original_name = original_name
        if meta_json is not None:
            rec.meta_json = meta_json
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec

    rec = DocumentCache(
        doc_type=doc_type,
        sha256=sha256,
        hint_key=hint_key,
        original_name=original_name,
        extracted_json=extracted_json,
        meta_json=meta_json,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def get_match_cache(
    db: Session,
    *,
    edital_sha256: str,
    produto_sha256: str,
    settings_sig: str,
) -> MatchCache | None:
    return (
        db.query(MatchCache)
        .filter_by(
            edital_sha256=edital_sha256,
            produto_sha256=produto_sha256,
            settings_sig=settings_sig,
        )
        .first()
    )


def upsert_match_cache(
    db: Session,
    *,
    edital_sha256: str,
    produto_sha256: str,
    settings_sig: str,
    result_json: Any,
    meta_json: Optional[dict] = None,
) -> MatchCache:
    rec = get_match_cache(
        db,
        edital_sha256=edital_sha256,
        produto_sha256=produto_sha256,
        settings_sig=settings_sig,
    )
    if rec:
        rec.result_json = result_json
        if meta_json is not None:
            rec.meta_json = meta_json
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec

    rec = MatchCache(
        edital_sha256=edital_sha256,
        produto_sha256=produto_sha256,
        settings_sig=settings_sig,
        result_json=result_json,
        meta_json=meta_json,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec
