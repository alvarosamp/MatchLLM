import os
from core.ocr.extractor import PDFExtractor
from core.ocr.normalizador import normalize_text
from core.preprocess.chunker import chunk_text
from core.preprocess.embeddings import Embedder
from core.vectorstore.index import VectorIndex
from core.rag.retrivier import RAGRetrivier
from core.rag.match import Matcher

BASE_VECTOR_DIR = "data/processed/vectorstore"

def process_edital(pdf_path:str, edital_id: int) -> dict:
    """
    Pipeline para ingerir um edital: 
        -> Extrai o texto do pdf (OCR se necessario)
        -> Normaliza o texto
        -> Chunkifica o texto
        -> Gera embeddings dos chunks
        -> Armazena os embeddings no indice vetorial
    """
    os.makedirs(BASE_VECTOR_DIR, exist_ok=True)
    extractor = PDFExtractor()
    raw_text = extractor.extract(pdf_path)
    normalized_text = normalize_text(raw_text)
    chunks = chunk_text(normalized_text)
    embedder = Embedder()
    vectors = embedder.encode(chunks)
    # Ajusta dimensão do índice de acordo com os embeddings gerados
    try:
        dim = int(len(vectors[0])) if hasattr(vectors, '__len__') and len(vectors) > 0 else 768
    except Exception:
        dim = 768
    index = VectorIndex(dim=dim)
    try:
        index.add(vectors, chunks)
    except AssertionError:
        # Em alguns ambientes, FAISS pode acusar mismatch de dimensão; tenta ajustar e adicionar novamente
        try:
            true_dim = int(vectors.shape[1]) if hasattr(vectors, 'shape') and len(vectors.shape) == 2 else int(len(vectors[0]))
        except Exception:
            true_dim = dim
        index = VectorIndex(dim=true_dim)
        index.add(vectors, chunks)
    index_path = os.path.join(BASE_VECTOR_DIR, f"edital_{edital_id}_index.pkl")
    chunks_path = os.path.join(BASE_VECTOR_DIR, f"edital_{edital_id}_chunks.pkl")
    index.save(index_path, chunks_path)
    return {
        "index_path": index_path,
        "chunks_path": chunks_path,
        "edital_id": edital_id,
        "total_chunks": len(chunks) if isinstance(chunks, (list, tuple)) else 0,
    }

def match_produto_edital(produto_json: dict, edital_id: int, consulta_textual: str, model: str | None = None) -> str:
    """
    Dado um produto e um edital já indexado:
    - carrega o índice do edital
    - faz busca RAG usando 'consulta_textual'
    - envia para o LLM fazer o match técnico
    """
    embedder = Embedder()
    index = VectorIndex()
    index_path = os.path.join(BASE_VECTOR_DIR, f"edital_{edital_id}_index.pkl")
    chunks_path = os.path.join(BASE_VECTOR_DIR, f"edital_{edital_id}_chunks.pkl")
    index.load(index_path, chunks_path)
    retrivier = RAGRetrivier(embedder, index)
    chunks_relevantes= retrivier.search(consulta_textual, top_k=10)
    matcher = Matcher(model=model)
    resultado = matcher.compare(produto_json, chunks_relevantes)
    return resultado
        