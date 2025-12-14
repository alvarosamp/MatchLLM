import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ocr.extractor import PDFExtractor
from core.ocr.normalizador import normalize_text

# Caminhos
edital_path = "C:\\Users\\vish8\\OneDrive\\Documentos\\MatchLLM\\data\\editais\\EDITAL_DO_PREGAO_ELETRONICO_N_242025__MATERIAL_DE_INFORMATICA_anx7532518935684159076.pdf"
produto_path = "C:\\Users\\vish8\\OneDrive\\Documentos\\MatchLLM\\data\\produtos\\Produto36334IdArquivo15589.pdf"

extractor = PDFExtractor()

print("=== TESTE OCR EDITAL ===")
edital_text = extractor.extract(edital_path)
edital_text = normalize_text(edital_text)
print(edital_text[:1500])  # imprime só o começo

print("\n=== TESTE OCR PRODUTO ===")
produto_text = extractor.extract(produto_path)
produto_text = normalize_text(produto_text)
print(produto_text[:1500])
