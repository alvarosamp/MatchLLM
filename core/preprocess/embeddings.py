from fastembed import TextEmbedding
import numpy as np
import os

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
        # Em máquinas com pouca RAM, o ONNXRuntime pode falhar ao alocar buffers grandes.
        # Permitimos controlar o batch size via env e também fazemos fallback automático.

        batch_env = os.getenv("EMBED_BATCH_SIZE", "").strip()
        if batch_env:
            batch_sizes = [max(1, int(batch_env))]
        else:
            # sequência de fallback (maior -> menor)
            batch_sizes = [64, 32, 16, 8, 4, 2, 1]

        last_err: Exception | None = None
        for batch_size in batch_sizes:
            try:
                embeddings = list(self.model.embed(texts, batch_size=batch_size))
                return np.array(embeddings, dtype=np.float32)
            except Exception as e:
                msg = str(e).lower()
                is_alloc = (
                    "failed to allocate" in msg
                    or "allocaterawinternal" in msg
                    or "bfc_arena" in msg
                )
                if is_alloc and (not batch_env):
                    last_err = e
                    continue
                raise

        raise RuntimeError(
            "Falha ao gerar embeddings por falta de memória. "
            "Tente definir EMBED_BATCH_SIZE=4 (ou menor) no ambiente e rode novamente. "
            f"Último erro: {last_err}"
        )