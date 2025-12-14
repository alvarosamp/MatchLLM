from fastembed import TextEmbedding
import numpy as np

class Embedder:
    """
    Wrapper para o modelo de embeddings (FastEmbed E5)\
    Usado tanto para chunks de texto quanto para consultas.
    """

    def __init__(self, model_name: str = "intfloat/e5-base-v2"):
        # FastEmbed carrega modelos leves baseados em ONNX (CPU-only)
        self.model = TextEmbedding(model=model_name)

    def encode(self, texts: list[str]):
        """
        Recebe lista de textos e retorna matriz de embbedings (numpy array)
        """
        # Retorna matriz numpy float32, compatível com FAISS
        embeddings = list(self.model.embed(texts))
        return np.array(embeddings, dtype=np.float32)