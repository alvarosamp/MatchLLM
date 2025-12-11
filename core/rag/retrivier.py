from core.preprocess.embeddings import Embedder
from core.vectorstore.index import VectorIndex

class RAGRetrivier:
    """  
    Responsavel por:
     -> transformar a consulta em embedding
        -> buscar os chunks mais relevantes no indice vetorial
    """

    def __init__(self, embedder : Embedder, index : VectorIndex):
        self.embedder = embedder
        self.index = index

    def search(self, query : str, top_k : int = 5) -> list[str]:
        """
        Dada uma consulta em texto, retorna os top_k chunks mais relevantes
        """
        query_vec = self.embedder.encode([query])[0]
        results = self.index.search(query_vec, top_k=top_k)
        return results 