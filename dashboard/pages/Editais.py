import os
import sys
from pathlib import Path
import streamlit as st
import requests


def _ensure_repo_root_on_path() -> None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "core").is_dir():
            sys.path.insert(0, str(parent))
            return


_ensure_repo_root_on_path()

# Dentro do Docker, o hostname do serviço da API é "api".
# Fora do Docker (rodando local no Windows), normalmente é localhost.
API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.title("Upload de Editais (múltiplos)")

uploaded_files = st.file_uploader(
    "Envie um ou mais editais em PDF",
    type=["pdf"],
    accept_multiple_files=True,
)

if uploaded_files and st.button("Processar todos"):
    ids = []
    for uf in uploaded_files:
        files = {"file": (uf.name, uf.getvalue(), "application/pdf")}
        resp = requests.post(f"{API_URL}/editais/upload", files=files)
        if resp.status_code == 200:
            data = resp.json()
            ids.append(data.get("edital_id"))
        else:
            st.error(f"Erro em {uf.name}: {resp.text}")
    if ids:
        st.success(f"Editais processados. IDs: {', '.join(map(str, ids))}")
