import faiss
import numpy as np
import pickle 
from typing import List

class VectorIndex:
    """
    Indexador vetorial usando FAISS
    Guarda:
    - o índice FAISS
    - lista de chunks associados a cada vetor
    """

    def __init__(self, dim: int = 768):
        self.index = faiss.IndexFlatL2(dim)
        self.chunks: List[str] = []

    def add(self, embeddings, chunks: list[str]):
        """
        Adiciona embeddings e chunks ao índice
        embeddings: matriz numpy de vetores
        chunks: lista de strings correspondentes
        """
        # Normaliza para uma matriz 2D (n, d) de float32
        if isinstance(embeddings, np.ndarray):
            arr = embeddings.astype('float32')
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
        else:
            # lista de vetores -> empilha
            emb_list = [np.asarray(e, dtype='float32').reshape(1, -1) for e in embeddings]
            arr = np.vstack(emb_list) if len(emb_list) > 0 else np.empty((0, self.index.d), dtype='float32')

        cur_dim = arr.shape[1] if arr.size > 0 else self.index.d

        if hasattr(self.index, 'd') and self.index.d != cur_dim:
            # Recria índice com dimensão correta
            self.index = faiss.IndexFlatL2(cur_dim)

        if arr.shape[0] > 0:
            self.index.add(arr)
        self.chunks.extend(chunks)
    
    def search(self, query_embedding, top_k: int = 5) -> List[str]:
        """
        Busca top_k chunks mais proximos do embedding de consulta
        """

        query_embedding = np.array([query_embedding]).astype('float32')
        distances, ids = self.index.search(query_embedding, top_k)
        return [self.chunks[i] for i in ids[0] if i < len(self.chunks)]

    def save(self, index_path : str, chunks_path : str):
        """
        Salva o índice FAISS e os chunks em arquivos separados
        """
        faiss.write_index(self.index, index_path)
        with open(chunks_path, 'wb') as f:
            pickle.dump(self.chunks, f)

    def load(self, index_path : str, chunks_path : str):
        """
        Carrega indice FAISS + chunks de disco
        """
        self.index = faiss.read_index(index_path)
        with open(chunks_path, 'rb') as f:
            self.chunks = pickle.load(f)