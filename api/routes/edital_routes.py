from fastapi import APIRouter, HTTPException, UploadFile, File
from api.models.edital import Produto
from api.services.edital_service import processar_edital, rodar_match

router = APIRouter(prefix="/editais", tags=["Editais"])

@router.post("/upload")
async def upload_edital(file: UploadFile = File(...)):
    filename = (file.filename or "")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF.")

    result = processar_edital(file.file)
    return {
        "message": "Edital processado com sucesso.",
        "edital_id": result["edital_id"],
        "total_chunks": result["total_chunks"],
    }

@router.post("/match/{edital_id}")
async def match_edital(
    edital_id: int,
    produto: Produto,
    consulta: str,
):
    """
    produto: JSON com informações técnicas
    consulta: string usada para buscar trechos relevantes (ex: "switch 24 portas poe")
    """
    try:
        result = rodar_match(produto, edital_id, consulta)
        return {"edital_id": edital_id, "resultado_llm": result}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Índice do edital não encontrado. Reprocesse o edital.")