from __future__ import annotations

from sqlalchemy.orm import Session

from db.models.editais import Edital


def create_edital(db: Session, *, nome: str | None = None, caminho_pdf: str | None = None) -> Edital:
    rec = Edital(nome=nome, caminho_pdf=caminho_pdf)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec
