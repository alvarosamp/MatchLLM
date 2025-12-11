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