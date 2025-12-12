import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pipeline import process_edital, match_produto_edital

# Produto estruturado manualmente (por enquanto)
produto = {
    "nome": "Bateria Moura 12MVA-7",
    "atributos": {
        "tensao": "12V",
        "capacidade_ah": 7,
        "temperatura_max": "50C",
        "tipo": "VRLA AGM"
    }
}

edital_path = "C:\\Users\\vish8\\OneDrive\\Documentos\\MatchLLM\\data\\editais\\EDITAL_DO_PREGAO_ELETRONICO_N_242025__MATERIAL_DE_INFORMATICA_anx7532518935684159076.pdf"
edital_id = 1

# Processa edital
process_edital(edital_path, edital_id)

# Roda match
resultado = match_produto_edital(
    produto_json=produto,
    edital_id=edital_id,
    consulta_textual="bateria 12 volts 7 ah vrla"
)

print("\n=== RESULTADO FINAL ===")
print(resultado)
