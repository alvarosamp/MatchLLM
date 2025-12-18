from fastapi import APIRouter, HTTPException, UploadFile, File
import json
import logging
import asyncio
import uuid
from typing import List
from pathlib import Path

from api.models.edital import Produto
from api.services.edital_service import (
    processar_edital,
    rodar_match,
    extrair_requisitos,
    rodar_match_com_requisitos,
)

# Logger para registrar exceções completas (útil para debugar 500s)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/editais", tags=["Editais"])

# Simple in-memory job store for background match jobs (job_id -> dict)
# Structure: {job_id: {status: 'pending'|'running'|'done'|'error', result: ..., error: ...}}
JOBS: dict = {}


async def _run_match_job(job_id: str, func, *args, **kwargs):
    """Run a blocking match function in a threadpool and store the result in JOBS."""
    loop = asyncio.get_running_loop()
    JOBS[job_id] = {"status": "running"}
    try:
        result = await loop.run_in_executor(None, func, *args, **kwargs)
        JOBS[job_id] = {"status": "done", "result": result}
    except Exception as e:
        logger.exception("Job %s failed", job_id)
        JOBS[job_id] = {"status": "error", "error": str(e)}


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
        logger.exception("Falha ao processar edital")
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao processar edital: {e}",
        )


@router.post("/match/{edital_id}")
async def match_edital(
    edital_id: int,
    produto: Produto,
    consulta: str,
    model: str | None = None,
    use_requisitos: bool = False,
    async_job: bool = False,
):
    """
    produto: JSON com informações técnicas
    consulta: string usada para buscar trechos relevantes (ex: "switch 24 portas poe")
    """
    try:
        # ---------- Caminho com requisitos extraídos ----------
        if use_requisitos:
            try:
                itens = rodar_match_com_requisitos(produto, edital_id, model=model)
                return {"edital_id": edital_id, "resultado": itens}
            except FileNotFoundError:
                _ = extrair_requisitos(edital_id, model=model)
                itens = rodar_match_com_requisitos(produto, edital_id, model=model)
                return {"edital_id": edital_id, "resultado": itens}

        # ---------- Caminho assíncrono ----------
        if async_job:
            job_id = uuid.uuid4().hex
            JOBS[job_id] = {"status": "pending"}
            asyncio.create_task(
                _run_match_job(job_id, rodar_match, produto, edital_id, consulta, model)
            )
            return {
                "job_id": job_id,
                "status": "pending",
                "poll_url": f"/editais/match/job/{job_id}",
            }, 202

        # ---------- Caminho síncrono ----------
        result = rodar_match(produto, edital_id, consulta, model=model)

        # Tenta normalizar o resultado como JSON estruturado
        result_json = None
        if isinstance(result, (dict, list)):
            result_json = result
        elif isinstance(result, str):
            try:
                result_json = json.loads(result)
            except Exception:
                start = result.find("[")
                end = result.rfind("]")
                if start != -1 and end != -1 and end > start:
                    snippet = result[start : end + 1]
                    try:
                        result_json = json.loads(snippet)
                    except Exception:
                        result_json = None

        return {
            "edital_id": edital_id,
            "resultado_llm": result,
            "resultado": result_json,
        }

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Índice do edital não encontrado. Reprocesse o edital.",
        )

    except HTTPException:
        raise

    except Exception as e:
        # 🔥 AQUI ESTÁ A CORREÇÃO CERTA 🔥
        logger.exception("Falha no match")

        msg = str(e).lower()

        # Timeout / lentidão do LLM (Ollama)
        if (
            "timeout" in msg
            or "tempo de espera" in msg
            or "ollama" in msg
            or "llm" in msg
        ):
            raise HTTPException(
                status_code=504,
                detail=str(e),
            )

        # Erro real da aplicação
        raise HTTPException(
            status_code=500,
            detail=f"Falha no match: {e}",
        )


@router.get("/match/job/{job_id}")
async def get_match_job(job_id: str):
    """Retorna o status e resultado (se disponível) de um job de match agendado."""
    info = JOBS.get(job_id)
    if info is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return info


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


@router.post("/requisitos/{edital_id}")
async def gerar_requisitos(edital_id: int, model: str | None = None, max_chunks: int = 20):
    """Extrai itens/requisitos do edital já indexado e salva em JSON."""
    try:
        from core.pipeline import extract_requisitos_edital

        info = extract_requisitos_edital(
            edital_id,
            model=model,
            max_chunks=max_chunks,
        )
        return info

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Índice do edital não encontrado. Reprocesse o edital.",
        )

    except Exception as e:
        logger.exception("Falha ao extrair requisitos do edital")
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao extrair requisitos: {e}",
        )
