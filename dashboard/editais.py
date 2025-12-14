import os
import streamlit as st
import requests

# Dentro do Docker, o hostname do serviço da API é "api"
# Permite override via variável de ambiente
API_URL = os.getenv("API_BASE_URL", "http://api:8000")


st.title("Upload de Editais")

uploaded_file = st.file_uploader("Envie um edital em PDF", type=["pdf"])

if uploaded_file is not None and st.button("Processar edital"):
    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
    resp = requests.post(f"{API_URL}/editais/upload", files=files)
    if resp.status_code == 200:
        data = resp.json()
        st.success(f"Edital processado. ID: {data['edital_id']} | Chunks: {data['total_chunks']}")
    else:
        st.error(resp.text)
st.title("Match de Produto com Edital")