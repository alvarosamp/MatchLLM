from __future__ import annotations

from sqlalchemy.orm import Session

from db.models.editais import Edital


def create_edital(db: Session, *, nome: str | None, caminho_pdf: str | None) -> Edital:
    rec = Edital(nome=nome, caminho_pdf=caminho_pdf)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def get_edital(db: Session, *, edital_id: int) -> Edital | None:
    return db.query(Edital).filter_by(id=edital_id).first()
