from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Body
from pathlib import Path
import shutil
import uuid
from db.session import SessionLocal, init_db
from sqlalchemy.orm import Session
from core.pipeline import processar_datasheet
from typing import Optional
from db.repositories.produto_repo import get_or_create
from db.models.produtos import Produto

router = APIRouter(prefix="/produtos", tags=["Produtos"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/upload")
async def upload_produto(file: UploadFile = File(...), fabricante: str | None = None, modelo: str | None = None, db: Session = Depends(get_db)):
    """Faz upload de um datasheet PDF, processa (OCR/extrai specs) e persiste o produto no banco.

    Retorna o registro do produto criado/recuperado.
    """
    filename = file.filename or f"datasheet_{uuid.uuid4().hex}.pdf"
    dest_dir = Path("data") / "produtos"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # ensure DB tables exist
    init_db()

    try:
    # processar_datasheet expects: pdf_path, fabricante, modelo, db_session
        fabricante_val = fabricante or "desconhecido"
        modelo_val = modelo or dest_path.stem
        out = processar_datasheet(str(dest_path), fabricante_val, modelo_val, None, db)
        return {"message": "produto processado", "produto": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao processar datasheet: {e}")


@router.post("/json")
async def upload_produto_json(produto: dict = Body(...), fabricante: Optional[str] = None, modelo: Optional[str] = None, db: Session = Depends(get_db)):
    """Persiste um produto já extraído (JSON) no banco de dados.

    Espera um objeto JSON semelhante ao que o runner gera:
    {"nome": ..., "atributos": {...}, "origem": ...}
    """
    init_db()
    # Mantém compatibilidade com payloads antigos
    fab = fabricante or produto.get("fabricante") or produto.get("origem")
    mod = modelo or produto.get("modelo")
    nome = produto.get("nome")
    if not (isinstance(nome, str) and nome.strip()):
        # fallback: junta fabricante/modelo
        nome = f"{fab or ''} {mod or ''}".strip() or "desconhecido"

    specs = produto.get("atributos") or produto.get("atributos_json") or produto.get("specs") or produto
    try:
        prod = get_or_create(db, nome=nome, atributos_json=specs)
        return {"produto_id": prod.id, "nome": prod.nome, "atributos_json": prod.atributos_json}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao persistir produto JSON: {e}")


@router.get("/")
async def listar_produtos(db: Session = Depends(get_db)):
    """Lista produtos persistidos no banco (desenvolvimento)."""
    init_db()
    try:
        produtos = db.query(Produto).all()
        out = []
        for p in produtos:
            out.append({"id": p.id, "nome": p.nome, "atributos_json": p.atributos_json, "criado_em": str(p.criado_em)})
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
