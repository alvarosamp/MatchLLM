import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ocr.extractor import PDFExtractor
from core.ocr.normalizador import normalize_text
from core.preprocess.chunker import chunk_text
from core.preprocess.embeddings import Embedder
from core.vectorstore.index import VectorIndex

edital_path = "C:\\Users\\vish8\\OneDrive\\Documentos\\MatchLLM\\data\\editais\\EDITAL_DO_PREGAO_ELETRONICO_N_242025__MATERIAL_DE_INFORMATICA_anx7532518935684159076.pdf"

# OCR
extractor = PDFExtractor()
text = normalize_text(extractor.extract(edital_path))

# Chunking
chunks = chunk_text(text)

print(f"Total de chunks: {len(chunks)}")

# Embeddings
embedder = Embedder()
vectors = embedder.encode(chunks)

# Indexação
index = VectorIndex()
index.add(vectors, chunks)

# Consulta de teste
query = "bateria 12 volts 7 ah"
query_vec = embedder.encode([query])[0]

results = index.search(query_vec, top_k=5)

print("\n=== TRECHOS ENCONTRADOS ===")
for r in results:
    print("-" * 80)
    print(r[:500])
