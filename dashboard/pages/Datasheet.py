import json
from pathlib import Path
import streamlit as st

from core.ocr.extractor import PDFExtractor
from core.preprocess.product_extractor import ProductExtractor

PRODUTOS_DIR = Path("data/produtos")
PRODUTOS_DIR.mkdir(parents=True, exist_ok=True)

st.title("Datasheet do Produto (PDF)")

uploaded = st.file_uploader("Envie o PDF do datasheet do produto", type=["pdf"])
if uploaded is not None and st.button("Extrair e salvar produto"):
    # Salvar PDF em data/produtos
    pdf_path = PRODUTOS_DIR / uploaded.name
    pdf_path.write_bytes(uploaded.getvalue())

    # Extrair texto
    extractor = PDFExtractor()
    text = extractor.extract(str(pdf_path))
    if not text or not text.strip():
        st.error("Não foi possível extrair texto do PDF.")
    else:
        # Extrair produto via LLM
        pe = ProductExtractor()
        raw = pe.extract(text)
        try:
            produto = json.loads(raw)
        except Exception:
            st.error("Falha ao interpretar o JSON retornado pelo LLM. Conteúdo bruto:")
            st.code(raw)
        else:
            # Salvar como JSON para uso posterior no Match
            nome = produto.get("nome", uploaded.name.replace(".pdf", ""))
            dest = PRODUTOS_DIR / f"{nome}.json"
            dest.write_text(json.dumps(produto, ensure_ascii=False, indent=2), encoding="utf-8")
            st.success(f"Produto salvo em {dest}")
            st.json(produto)

st.subheader("Produtos extraídos")
for p in PRODUTOS_DIR.glob("*.json"):
    st.write(p.name)
