import json
from typing import Dict, List, Any

from core.llm.client import LLMClient
from core.pipeline import (
    comparar_produto_com_requisitos,
    extrair_requisitos_edital,
)


class Matcher:
    """
    Responsável por orquestrar:
    - extração de requisitos do edital
    - comparação técnica com o produto
    - explicação técnica via LLM
    """

    def __init__(self, llm_client: LLMClient | None = None, model: str | None = None):
        self.llm_client = llm_client or LLMClient(model=model)

    def compare(
        self,
        produto: Dict[str, Any],
        edital_chunks: List[str],
    ) -> Dict[str, Any]:
        """
        produto: JSON técnico do produto (já normalizado)
        edital_chunks: trechos relevantes do edital
        """

        # 1. Extrair requisitos técnicos do edital
        requisitos = extrair_requisitos_edital(
            edital_chunks=edital_chunks,
            llm_client=self.llm_client,
        )

        # 2. Comparação técnica + explicação
        resultado = comparar_produto_com_requisitos(
            produto_specs=produto,
            requisitos=requisitos,
            llm_client=self.llm_client,
        )

        return {
            "requisitos": requisitos,
            "resultado": resultado,
        }
