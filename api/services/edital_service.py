import shutil 
import secrets
from pathlib import Path
from core.pipeline import process_edital, match_produto_edital
from api.models.edital import Produto

DATA_EDITAIS_DIR = Path("data/editais")
DATA_EDITAIS_DIR.mkdir(parents=True, exist_ok=True)


def salvar_edital_upload(file) -> tuple[int, str]:
    """
    Salva o arquivo PDF enviado e retorna (edital_id, caminho).
    edital_id aqui está simulando. Depois você pode integrar com DB.
    """
    edital_id = secrets.randbelow(1_000_000_000)
    filename = f"edital_{edital_id}.pdf"
    dest_path = DATA_EDITAIS_DIR / filename

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file, f)

    return edital_id, str(dest_path)


def processar_edital(file) -> dict:
    edital_id, pdf_path = salvar_edital_upload(file)
    result = process_edital(pdf_path, edital_id)
    return result


def rodar_match(produto: Produto, edital_id: int, consulta: str, model: str | None = None) -> str:
    return match_produto_edital(produto.dict(), edital_id, consulta, model=model)