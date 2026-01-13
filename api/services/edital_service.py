import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from core.pipeline import process_edital, match_produto_edital, extract_requisitos_edital, match_produto_com_requisitos
from api.models.edital import Produto
from db.repositories.edital_repo import create_edital

DATA_EDITAIS_DIR = Path("data/editais")
DATA_EDITAIS_DIR.mkdir(parents=True, exist_ok=True)


def salvar_edital_upload(file, *, filename: str | None, db: Session) -> tuple[int, str]:
    """Salva o PDF e cria registro em `editais`.

    Retorna (edital_id, caminho_pdf).
    """
    rec = create_edital(db, nome=filename, caminho_pdf=None)
    filename_eff = filename or f"edital_{rec.id}.pdf"
    dest_path = DATA_EDITAIS_DIR / f"edital_{rec.id}__{filename_eff}"

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file, f)

    # Atualiza caminho no registro
    rec.caminho_pdf = str(dest_path)
    db.add(rec)
    db.commit()
    db.refresh(rec)

    return int(rec.id), str(dest_path)


def processar_edital(file, *, filename: str | None, db: Session) -> dict:
    edital_id, pdf_path = salvar_edital_upload(file, filename=filename, db=db)
    result = process_edital(pdf_path, edital_id)
    return result


def rodar_match(produto: Produto, edital_id: int, consulta: str, model: str | None = None) -> str:
    return match_produto_edital(produto.dict(), edital_id, consulta, model=model)

def extrair_requisitos(edital_id: int, model: str | None = None) -> dict:
    return extract_requisitos_edital(edital_id, model=model)

def rodar_match_com_requisitos(produto: Produto, edital_id: int, model: str | None = None) -> list[dict]:
    return match_produto_com_requisitos(produto.dict(), edital_id, model=model)