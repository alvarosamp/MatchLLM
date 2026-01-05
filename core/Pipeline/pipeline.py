import json
from typing import Any, Dict, List, Tuple

from core.ocr.extractor import PDFExtractor
from core.ocr.normalizador import normalize_text

from core.preprocess.chunker import chunk_text
from core.preprocess.embeddings import Embedder

from core.preprocess.product_extractor import ProductExtractor
from core.preprocess.editalExtractor import EditalExtractor

from core.match.matching_engine import MatchingEngine
from core.match.scoring import compute_score
from core.llm.justificador import JustificationGenerator


def _cosine_sim_matrix(q_vec, mat):
    # q_vec: (d,), mat: (n, d)
    import numpy as np

    q = q_vec / (np.linalg.norm(q_vec) + 1e-9)
    m = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    return (m @ q).astype(float)


class MatchPipeline:
    """
    Pipeline E2E:
    - OCR + normalização
    - Chunk + embeddings no edital
    - Recupera trechos mais relevantes
    - Extrai JSON produto e JSON edital (requisitos)
    - Matching determinístico
    - Score final
    - Justificativa (LLM) opcional
    """

    def __init__(
        self,
        embed_model: str = "intfloat/e5-base-v2",
        top_k_edital_chunks: int = 10,
        enable_justification: bool = True,
        llm_model: str | None = None,
    ):
        self.pdf = PDFExtractor()
        self.embedder = Embedder(model_name=embed_model)
        self.top_k = int(top_k_edital_chunks)

        self.product_extractor = ProductExtractor()
        self.edital_extractor = EditalExtractor()
        self.engine = MatchingEngine()

        self.enable_justification = bool(enable_justification)
        self.justifier = JustificationGenerator(model=llm_model) if self.enable_justification else None

    def _build_edital_context(self, edital_text: str, produto_hint: str | None) -> Tuple[str, List[str]]:
        """
        Faz RAG simples: seleciona chunks do edital mais relevantes.
        Retorna (contexto_texto, chunks_selecionados)
        """
        chunks = chunk_text(edital_text, max_tokens=400)

        # Evita explodir custo/tempo em editais gigantes
        if len(chunks) == 0:
            return "", []

        # Embeddings dos chunks
        chunk_vecs = self.embedder.encode(chunks)

        # Query embedding
        query = (
            f"requisitos tecnicos especificacoes obrigatorias {produto_hint}"
            if produto_hint
            else "requisitos tecnicos especificacoes obrigatorias item licitacao"
        )
        q_vec = self.embedder.encode([query])[0]

        sims = _cosine_sim_matrix(q_vec, chunk_vecs)
        # pega top_k índices
        idxs = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[: self.top_k]
        selected = [chunks[i] for i in idxs]

        # junta contexto
        context = "\n\n".join(selected)
        return context, selected

    def run(self, edital_pdf_path: str, produto_pdf_path: str) -> Dict[str, Any]:
        # 1) OCR
        edital_text = self.pdf.extract(edital_pdf_path)
        produto_text = self.pdf.extract(produto_pdf_path)

        # 2) Normalização
        edital_text = normalize_text(edital_text or "")
        produto_text = normalize_text(produto_text or "")

        # 3) Extrai produto (LLM)
        produto_json = self.product_extractor.extract(produto_text)

        produto_hint = (produto_json.get("tipo_produto") or "") + " " + (produto_json.get("nome") or "")

        # 4) RAG simples no edital (reduz tokens)
        edital_context, selected_chunks = self._build_edital_context(edital_text, produto_hint.strip() or None)

        # 5) Extrai requisitos do edital (LLM, mas só no contexto)
        edital_json = self.edital_extractor.extract(edital_context if edital_context else edital_text)

        # 6) Matching determinístico
        matching = self.engine.compare(produto_json, edital_json)

        # 7) Score final
        score = compute_score(matching, edital_json)

        # 8) Justificativas (LLM só explica)
        justificativas = {"justificativas": {}}
        if self.enable_justification and self.justifier:
            justificativas = self.justifier.generate(
                produto_json=produto_json,
                edital_json=edital_json,
                matching=matching,
            )

        return {
            "produto_pdf": produto_pdf_path,
            "edital_pdf": edital_pdf_path,
            "produto_json": produto_json,
            "edital_json": edital_json,
            "matching": matching,
            "score": score,
            "justificativas": justificativas.get("justificativas", {}),
            "debug": {
                "edital_chunks_total": len(chunk_text(edital_text, max_tokens=400)),
                "edital_chunks_usados": len(selected_chunks),
            },
        }

    @staticmethod
    def save_result(result: Dict[str, Any], out_path: str) -> None:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
