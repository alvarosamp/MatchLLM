
from sentence_transformers import SentenceTransformer 

class Embedder:
    """
    Wrapper para o modelo de embeddings (SentenceTransformers)\
    Usado tanto para chunks de texto quanto para consultas.
    """

    def __init__(self, model_name: str = "all-mpnet-base-v2"):
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]):
        """
        Recebe lista de textos e retorna matriz de embbedings ( numpy array)
        """
        return self.model.encode(texts, show_progress_bar=True)