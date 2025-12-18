from typing import Dict, Any, List
from pathlib import Path

from core.ocr.ocr_pipeline import ocr_pdf
from core.ocr.fallback import extract_with_fallback
from core.match.technical_compare import compare_specs

# Esses imports assumem que você já tem isso no projeto
from database.repositories.produto_repo import get_or_create
from core.llm.client import LLMClient


def processar_datasheet(
    pdf_path: str,
    fabricante: str,
    modelo: str,
    gemini_client,
    db_session,
) -> Dict[str, Any]:
    """
    Pipeline completo para processar um datasheet:
    - OCR local
    - fallback Gemini se OCR falhar
    - extração de especificações técnicas
    - persistência com deduplicação
    """

    pdf_path = str(Path(pdf_path))

    # 1. OCR
    raw_text = ocr_pdf(pdf_path)

    # 2. Extração de specs com fallback
    specs = extract_with_fallback(raw_text, gemini_client)

    # 3. Persistência com deduplicação
    produto = get_or_create(
        db_session,
        fabricante=fabricante,
        modelo=modelo,
        specs=specs,
    )

    return {
        "produto_id": produto.id,
        "fabricante": fabricante,
        "modelo": modelo,
        "specs": specs,
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
