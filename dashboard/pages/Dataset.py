import os
import json
from pathlib import Path
import streamlit as st

PRODUTOS_DIR = Path("data/produtos")
PRODUTOS_DIR.mkdir(parents=True, exist_ok=True)

st.title("Dataset de Produtos")

st.subheader("Cadastrar produto")
nome = st.text_input("Nome do produto", value="Meu Produto")
atributos_raw = st.text_area(
    "Atributos do produto (JSON)",
    value='{"portas": 24, "poe": true}',
    height=200,
)

if st.button("Salvar produto"):
    try:
        atributos = json.loads(atributos_raw)
    except json.JSONDecodeError as e:
        st.error(f"JSON inválido: {e}")
    else:
        produto = {"nome": nome, "atributos": atributos}
        dest = PRODUTOS_DIR / f"{nome}.json"
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(produto, f, ensure_ascii=False, indent=2)
        st.success(f"Produto '{nome}' salvo em {dest}")

st.subheader("Produtos cadastrados")
produtos_disponiveis = [p for p in PRODUTOS_DIR.glob("*.json")]
if not produtos_disponiveis:
    st.info("Nenhum produto cadastrado ainda.")
else:
    for p in produtos_disponiveis:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        st.json({"arquivo": p.name, **data})
