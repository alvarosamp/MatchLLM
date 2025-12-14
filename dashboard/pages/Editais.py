import os
import streamlit as st
import requests

# Dentro do Docker, o hostname do serviço da API é "api"
API_URL = os.getenv("API_BASE_URL", "http://api:8000")

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
