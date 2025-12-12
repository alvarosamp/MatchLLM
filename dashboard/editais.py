import streamlit as st
import requests

API_URL = "http://localhost:8000"


st.title("Upload de Editais")

uploaded_file = st.file_uploader("Envie um edital em PDF", type=["pdf"])

if uploaded_file is not None and st.button("Processar edital"):
    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
    resp = requests.post(f"{API_URL}/edital/upload", files=files)
    if resp.status_code == 200:
        data = resp.json()
        st.success(f"Edital processado. ID: {data['edital_id']} | Chunks: {data['total_chunks']}")
    else:
        st.error(resp.text)
st.title("Match de Produto com Edital")