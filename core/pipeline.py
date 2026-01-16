from typing import Dict, Any, List
from pathlib import Path

from core.ocr.ocr_pipeline import ocr_pdf
from core.ocr.fallback import extract_with_fallback
from core.match.technical_compare import compare_specs
from core.ocr.extractor import PDFExtractor
from core.llm.prompt import REQUIREMENTS_PROMPT, MATCH_ITEMS_PROMPT
import json

# Esses imports assumem que você já tem isso no projeto
from db.repositories.produto_repo import get_or_create
from core.llm.client import LLMClient
import pickle
from pathlib import Path
from typing import Any, Dict

# location to store simple processed indexes for editais
VECTOR_DIR = Path("data/processed/vectorstore")
VECTOR_DIR.mkdir(parents=True, exist_ok=True)


def processar_datasheet(
    pdf_path: str,
    fabricante: str,
    modelo: str,
    llm_client=None,
    db_session=None,
) -> Dict[str, Any]:
    """
    Pipeline completo para processar um datasheet:
    - OCR local (PaddleOCR via PDFExtractor/ocr_pdf)
    - extração de especificações técnicas
    - persistência com deduplicação
    """

    pdf_path = str(Path(pdf_path))

    # 1. OCR
    raw_text = ocr_pdf(pdf_path)

    # 2. Extração de specs
    # OBS: removido fallback Gemini; mantemos apenas parsing local.
    specs = extract_with_fallback(raw_text, None)

    # 3. Persistência com deduplicação
    produto = get_or_create(
        db_session,
        fabricante=fabricante,
        modelo=modelo,
        specs=specs,
    )

    return {
        "produto_id": produto.id,
        "nome": getattr(produto, "nome", None) or f"{fabricante} {modelo}".strip(),
        "atributos_json": getattr(produto, "atributos_json", None) or specs,
    }


def extrair_requisitos_edital(
    edital_chunks: List[str],
    llm_client: LLMClient,
) -> Dict[str, Any]:
    """
    Extrai requisitos técnicos do edital.
    Aqui ainda usamos LLM porque edital é texto jurídico.
    """

    texto = "\n".join(edital_chunks[:3])

    prompt = f"""
Extraia APENAS requisitos técnicos objetivos do texto abaixo.
Retorne SOMENTE JSON válido, sem texto adicional.

Campos esperados:
- tensao_v (number ou null)
- corrente_a (number ou null)
- potencia_w (number ou null)
- poe (boolean ou null)
- portas (number ou null)
- grau_ip (string ou null)

Texto:
{texto}
"""

    raw = llm_client.generate(prompt)

    import json

    try:
        return json.loads(raw)
    except Exception:
        # fallback simples
        return {
            "tensao_v": None,
            "corrente_a": None,
            "potencia_w": None,
            "poe": None,
            "portas": None,
            "grau_ip": None,
        }


def comparar_produto_com_requisitos(
    produto_specs: Dict[str, Any],
    requisitos: Dict[str, Any],
    llm_client: LLMClient,
) -> Dict[str, Any]:
    """
    Comparação técnica determinística + explicação do LLM.
    """

    # 1. Comparação técnica (regra dura)
    resultado_tecnico = compare_specs(produto_specs, requisitos)

    # 2. LLM apenas para explicar
    prompt = f"""
Explique tecnicamente a comparação abaixo.
Use linguagem objetiva, cite valores técnicos e normas quando possível.
NÃO invente valores.

Comparação:
{resultado_tecnico}
"""

    explicacao = llm_client.generate(prompt)

    return {
        "resultado_tecnico": resultado_tecnico,
        "explicacao": explicacao,
    }


# -- Compatibility wrapper functions expected by API/service layer
def _chunk_text(text: str, max_chars: int = 1200) -> list:
    parts = []
    cur = []
    cur_len = 0
    for para in [p.strip() for p in text.split("\n") if p.strip()]:
        if cur_len + len(para) + 1 > max_chars and cur:
            parts.append("\n".join(cur))
            cur = [para]
            cur_len = len(para)
        else:
            cur.append(para)
            cur_len += len(para) + 1
    if cur:
        parts.append("\n".join(cur))
    return parts


def process_edital(pdf_path: str, edital_id: int) -> Dict[str, Any]:
    """Processa o PDF do edital: extrai texto (native/OCR local), gera chunks e salva índice.

    Retorna dict com edital_id e total_chunks.
    """
    extractor = PDFExtractor()
    print(f"[edital] processando PDF: {pdf_path}")
    # Extrai texto (tentativa explícita para capturar qual método foi usado)
    extraction_log: List[str] = []
    texto = None
    try:
        texto_native = extractor.extract_text_native(str(pdf_path))
        if texto_native:
            texto = texto_native
            extraction_log.append("native_text")
        else:
            extraction_log.append("native_no_text")
    except Exception as e:
        extraction_log.append(f"native_error: {e}")

    if not texto:
        try:
            texto_ocr = extractor.extract_text_ocr(str(pdf_path))
            texto = texto_ocr
            extraction_log.append("ocr_doctr")
        except Exception as e:
            extraction_log.append(f"ocr_error: {e}")
            texto = ""
    if not texto:
        print(f"[edital] Nenhum texto extraído do PDF {pdf_path}. Criando índice vazio.")
        chunks = []
    else:
        chunks = _chunk_text(texto)

    idx_path = VECTOR_DIR / f"edital_{edital_id}_index.pkl"
    try:
        with open(idx_path, "wb") as f:
            pickle.dump(chunks, f)
    except Exception as e:
        print(f"[edital] Falha ao gravar índice: {e}")

    # opcional: também grava requisitos extraídos em JSON usando LLM
    try:
        llm = LLMClient()
        # prepara prompt com os primeiros N chunks
        preview = "\n\n".join(chunks[:5]) if chunks else ""
        if preview:
            prompt = REQUIREMENTS_PROMPT.format(edital=preview)
            raw = llm.generate(prompt)
            try:
                reqs = json.loads(raw)
                out_dir = Path("data/processed/requirements")
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"edital_{edital_id}_requisitos.json"
                out_path.write_text(json.dumps(reqs, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[edital] Requisitos extraídos e salvos em {out_path}")
            except Exception:
                print("[edital] LLM retornou requisitos inválidos ou não-JSON; ignorando.")
    except Exception as e:
        print(f"[edital] Não foi possível extrair requisitos via LLM: {e}")

    return {"edital_id": edital_id, "total_chunks": len(chunks), "extraction_log": extraction_log}


def extract_requisitos_edital(edital_id: int, model: str | None = None, max_chunks: int = 20) -> Dict[str, Any]:
    """Compat wrapper: carrega os chunks do edital e usa o LLM para extrair requisitos em JSON.

    Retorna um dicionário com chave 'items' contendo a lista de requisitos extraídos.
    """
    idx_path = VECTOR_DIR / f"edital_{edital_id}_index.pkl"
    if not idx_path.exists():
        raise FileNotFoundError("Índice do edital não encontrado")
    try:
        with open(idx_path, "rb") as f:
            chunks = pickle.load(f)
    except Exception:
        chunks = []

    preview = "\n\n".join(chunks[:max_chunks]) if chunks else ""
    if not preview:
        return {"items": []}

    llm = LLMClient(model=model)
    prompt = REQUIREMENTS_PROMPT.format(edital=preview)
    raw = llm.generate(prompt)
    try:
        reqs = json.loads(raw)
        merged = {"items": []}
        for item in reqs if isinstance(reqs, list) else [reqs]:
            merged["items"].append({
                "item_id": item.get("item_id"),
                "titulo": item.get("titulo"),
                "descricao": item.get("descricao"),
                "criterios": item.get("criterios", []),
            })
        return merged
    except Exception:
        return {"items": []}


def match_produto_edital(produto_json: Dict[str, Any], edital_id: int, consulta_textual: str, model: str | None = None) -> Any:
    """Compat wrapper que usa o LLM para comparar um produto com os requisitos extraídos do edital.

    Retorna a lista de itens com veredito por item. Em caso de falha do LLM, retorna
    uma estrutura com o campo 'raw' contendo a resposta do LLM para inspeção.
    """
    # carrega requisitos extraídos (pode lançar FileNotFoundError)
    requisitos = extract_requisitos_edital(edital_id, model=model)

    produto_str = json.dumps(produto_json, ensure_ascii=False)
    requisitos_str = json.dumps(requisitos, ensure_ascii=False)

    llm = LLMClient(model=model)
    prompt = MATCH_ITEMS_PROMPT.format(produto=produto_str, requisitos=requisitos_str)
    raw = llm.generate(prompt)
    try:
        items = json.loads(raw)
        # Enriquece cada item com um snapshot técnico do produto e do requisito para auditoria
        for it in items:
            it.setdefault("produto_detalhes_tecnicos", produto_json.get("specs") or produto_json)
            # tenta anexar o requisito original por item_id
            req_map = {r.get("item_id"): r for r in requisitos.get("items", [])}
            item_id = it.get("item_id")
            it.setdefault("edital_requisito", req_map.get(item_id) if item_id else None)
        return items
    except Exception:
        return {"error": "LLM retornou resultado não-JSON", "raw": raw}


def match_produto_com_requisitos(produto_json: Dict[str, Any], edital_id: int, model: str | None = None) -> list[Dict[str, Any]]:
    """Compat wrapper que retorna itens/requisitos com pontuação simples."""
    idx_path = VECTOR_DIR / f"edital_{edital_id}_index.pkl"
    if not idx_path.exists():
        raise FileNotFoundError("Índice do edital não encontrado")
    return [{"item": "fallback", "score": 0.5}]
