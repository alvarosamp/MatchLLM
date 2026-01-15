import json
import sys
from pathlib import Path
import streamlit as st


def _ensure_repo_root_on_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "core").is_dir():
            sys.path.insert(0, str(parent))
            return


_ensure_repo_root_on_path()

from core.ocr.extractor import PDFExtractor
from core.preprocess.product_extractor import ProductExtractor

PRODUTOS_DIR = Path("data/produtos")
PRODUTOS_DIR.mkdir(parents=True, exist_ok=True)

st.title("Datasheet do Produto (PDF)")

uploaded_files = st.file_uploader(
    "Envie um ou mais arquivos de datasheet (PDF ou TXT)",
    type=["pdf", "txt"],
    accept_multiple_files=True,
)

if uploaded_files and st.button("Extrair e salvar produto(s)"):
    extractor = PDFExtractor()
    pe = ProductExtractor()

    def _decode_text_bytes(data: bytes) -> str:
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return data.decode("latin-1", errors="ignore")

    for uploaded in uploaded_files:
        # Salvar PDF em data/produtos
        file_path = PRODUTOS_DIR / uploaded.name
        raw_bytes = uploaded.getvalue()
        file_path.write_bytes(raw_bytes)

        if file_path.suffix.lower() == ".txt":
            text = _decode_text_bytes(raw_bytes)
        else:
            text = extractor.extract(str(file_path))
        if not text or not text.strip():
            st.error(f"Não foi possível extrair texto do PDF: {uploaded.name}")
            continue

        produto = pe.extract(text)
        if not isinstance(produto, dict):
            st.error(f"Falha ao extrair produto do PDF: {uploaded.name}")
            st.json({"retorno": str(produto)})
            continue

        nome = (
            produto.get("nome")
            if isinstance(produto.get("nome"), str) and produto.get("nome").strip()
            else Path(uploaded.name).stem
        )
        dest = PRODUTOS_DIR / f"{nome}.json"
        dest.write_text(json.dumps(produto, ensure_ascii=False, indent=2), encoding="utf-8")
        st.success(f"Produto salvo: {dest.name}")
        with st.expander(f"Ver JSON extraído: {dest.name}"):
            st.json(produto)

st.subheader("Produtos extraídos")
for p in PRODUTOS_DIR.glob("*.json"):
    st.write(p.name)
