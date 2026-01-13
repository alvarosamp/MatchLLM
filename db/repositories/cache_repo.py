from __future__ import annotations

import json
import math
from typing import Any

from sqlalchemy.orm import Session

from db.models.cache import DocumentCache, MatchCache


def _coerce_json_dict(value: Any) -> dict | None:
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


def _is_bad_number(value: Any, *, unit: str | None = None) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        try:
            if isinstance(value, float) and math.isnan(value):
                return True
        except Exception:
            pass
        # 0 costuma ser OCR/parse ruim para specs; preserva o valor antigo.
        if value == 0 and (unit or ""):
            return True
        return False
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"", "nan", "null", "none"}:
            return True
        # strings numéricas também podem ser avaliadas
        try:
            f = float(s.replace(",", "."))
            if math.isnan(f):
                return True
            if f == 0 and (unit or ""):
                return True
        except Exception:
            pass
        return False
    return False


def _merge_meta_json(existing: dict | None, incoming: dict | None) -> dict | None:
    existing = _coerce_json_dict(existing) or {}
    incoming = _coerce_json_dict(incoming) or {}
    if not existing and not incoming:
        return None

    # Normaliza o campo 'ocr' caso tenha sido persistido como string JSON.
    if "ocr" in existing:
        existing_ocr = _coerce_json_dict(existing.get("ocr"))
        if existing_ocr is not None:
            existing["ocr"] = existing_ocr
    if "ocr" in incoming:
        incoming_ocr = _coerce_json_dict(incoming.get("ocr"))
        if incoming_ocr is not None:
            incoming["ocr"] = incoming_ocr

    merged = dict(existing)
    for k, v in incoming.items():
        if v is None:
            continue
        merged[k] = v
    return merged


def _merge_produto_json(existing: dict, incoming: dict) -> dict:
    if not isinstance(existing, dict):
        existing = {}
    if not isinstance(incoming, dict):
        return existing

    merged = dict(existing)

    for top_key in ("nome", "tipo_produto"):
        new_val = incoming.get(top_key)
        if isinstance(new_val, str) and new_val.strip():
            merged[top_key] = new_val

    old_attrs = existing.get("atributos") if isinstance(existing.get("atributos"), dict) else {}
    new_attrs = incoming.get("atributos") if isinstance(incoming.get("atributos"), dict) else {}
    attrs = dict(old_attrs)
    for k, new_obj in new_attrs.items():
        old_obj = attrs.get(k) if isinstance(attrs.get(k), dict) else {}
        if not isinstance(new_obj, dict):
            continue
        new_val = new_obj.get("valor")
        new_unit = new_obj.get("unidade")
        old_val = old_obj.get("valor")
        old_unit = old_obj.get("unidade")

        chosen_unit = new_unit or old_unit
        if _is_bad_number(new_val, unit=chosen_unit):
            # não substitui por 0/NaN/vazio
            attrs[k] = {"valor": old_val, "unidade": chosen_unit}
        else:
            attrs[k] = {"valor": new_val, "unidade": chosen_unit}

    if attrs:
        merged["atributos"] = attrs
    return merged


def _merge_edital_json(existing: dict, incoming: dict) -> dict:
    if not isinstance(existing, dict):
        existing = {}
    if not isinstance(incoming, dict):
        return existing

    merged = dict(existing)
    old_reqs = existing.get("requisitos") if isinstance(existing.get("requisitos"), dict) else {}
    new_reqs = incoming.get("requisitos") if isinstance(incoming.get("requisitos"), dict) else {}
    reqs = dict(old_reqs)

    for k, new_obj in new_reqs.items():
        old_obj = reqs.get(k) if isinstance(reqs.get(k), dict) else {}
        if not isinstance(new_obj, dict):
            continue

        unit = new_obj.get("unidade") or old_obj.get("unidade")
        merged_obj = dict(old_obj)
        merged_obj["unidade"] = unit

        for field in ("valor", "valor_min", "valor_max"):
            if field in new_obj:
                new_val = new_obj.get(field)
                if not _is_bad_number(new_val, unit=unit):
                    merged_obj[field] = new_val

        if "obrigatorio" in new_obj and new_obj.get("obrigatorio") is not None:
            merged_obj["obrigatorio"] = bool(new_obj.get("obrigatorio"))

        reqs[k] = merged_obj

    if reqs:
        merged["requisitos"] = reqs
    return merged


def get_document_cache(
    db: Session,
    *,
    doc_type: str,
    sha256: str,
    hint_key: str | None = None,
):
    return (
        db.query(DocumentCache)
        .filter_by(doc_type=doc_type, sha256=sha256, hint_key=hint_key)
        .first()
    )


def upsert_document_cache(
    db: Session,
    *,
    doc_type: str,
    sha256: str,
    hint_key: str | None,
    original_name: str | None,
    extracted_json: dict,
    meta_json: dict | None = None,
):
    rec = get_document_cache(db, doc_type=doc_type, sha256=sha256, hint_key=hint_key)
    if rec:
        rec.original_name = original_name or rec.original_name
        # Merge conservador: não sobrescreve valores bons com 0/NaN/vazio.
        try:
            if doc_type == "produto":
                rec.extracted_json = _merge_produto_json(rec.extracted_json or {}, extracted_json or {})
            elif doc_type == "edital":
                rec.extracted_json = _merge_edital_json(rec.extracted_json or {}, extracted_json or {})
            else:
                rec.extracted_json = extracted_json
        except Exception:
            rec.extracted_json = extracted_json

        rec.meta_json = _merge_meta_json(rec.meta_json, meta_json)
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


def get_match_cache(db: Session, *, edital_sha256: str, produto_sha256: str, settings_sig: str):
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
    result_json: dict,
    meta_json: dict | None = None,
):
    rec = get_match_cache(db, edital_sha256=edital_sha256, produto_sha256=produto_sha256, settings_sig=settings_sig)
    if rec:
        rec.result_json = result_json
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
