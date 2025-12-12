import os
from core.ocr.extrator import PDFExtrator
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
    extractor = PDFExtrator()
    raw_text = extractor.extract(pdf_path)
    normalized_text = normalize_text(raw_text)
    chunks = chunk_text(normalized_text)
    embedder = Embedder()
    vectors = embedder.encode(chunks)
    index = VectorIndex()
    index.add(vectors, chunks)
    index_path = os.path.join(BASE_VECTOR_DIR, f"edital_{edital_id}_index.pkl")
    chunks_path = os.path.join(BASE_VECTOR_DIR, f"edital_{edital_id}_chunks.pkl")
    index.save(index_path, chunks_path)
    return {
        "index_path": index_path,
        "chunks_path": chunks_path
    }

def match_produto_edital(produto_json : dict, edital_id:int, consulta_textual : str) -> str:
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
    matcher = Matcher()
    resultado = matcher.compare(produto_json, chunks_relevantes)
    return resultado
        