from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List
from pathlib import Path
from api.models.edital import Produto
from api.services.edital_service import processar_edital, rodar_match

router = APIRouter(prefix="/editais", tags=["Editais"])

@router.post("/upload")
async def upload_edital(file: UploadFile = File(...)):
    filename = (file.filename or "")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF.")

    try:
        result = processar_edital(file.file)
        return {
            "message": "Edital processado com sucesso.",
            "edital_id": result.get("edital_id"),
            "total_chunks": result.get("total_chunks"),
        }
    except HTTPException:
        raise
    except Exception as e:
        # Retorna detalhes do erro para facilitar diagnóstico
        raise HTTPException(status_code=500, detail=f"Falha ao processar edital: {e}")

@router.post("/match/{edital_id}")
async def match_edital(
    edital_id: int,
    produto: Produto,
    consulta: str,
    model: str | None = None,
):
    """
    produto: JSON com informações técnicas
    consulta: string usada para buscar trechos relevantes (ex: "switch 24 portas poe")
    """
    try:
        result = rodar_match(produto, edital_id, consulta, model=model)
        return {"edital_id": edital_id, "resultado_llm": result}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Índice do edital não encontrado. Reprocesse o edital.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha no match: {e}")

@router.get("/ids")
async def listar_editais_indexados() -> List[int]:
    """Lista os edital_id disponíveis no vectorstore para facilitar testes."""
    ids: List[int] = []
    vector_dir = Path("data/processed/vectorstore")
    if vector_dir.exists():
        for fp in vector_dir.glob("edital_*_index.pkl"):
            try:
                id_str = fp.name.replace("edital_", "").replace("_index.pkl", "")
                ids.append(int(id_str))
            except Exception:
                continue
    return sorted(ids)