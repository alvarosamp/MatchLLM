from __future__ import annotations

from sqlalchemy.orm import Session

from db.models.matches import Match


def create_match(
    db: Session,
    *,
    edital_id: int | None,
    produto_id: int | None,
    consulta: str | None,
    resultado_llm: dict | list | str | None,
) -> Match:
    # JSON column aceita dict/list; se vier string, embrulha para manter estrutura
    payload = resultado_llm
    if isinstance(resultado_llm, str):
        payload = {"raw": resultado_llm}

    rec = Match(
        edital_id=edital_id,
        produto_id=produto_id,
        consulta=consulta,
        resultado_llm=payload,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec
