import os
import streamlit as st
import requests
import json
from pathlib import Path

API_URL = os.getenv("API_BASE_URL", "http://api:8000")
PRODUTOS_DIR = Path("data/produtos")

st.title("Match Produto x Edital")

# Selecionar produto salvo
produtos = [p.name for p in PRODUTOS_DIR.glob("*.json")] if PRODUTOS_DIR.exists() else []
produto_escolhido = st.selectbox("Produto", options=produtos) if produtos else None

produto_data = None
if produto_escolhido:
    with open(PRODUTOS_DIR / produto_escolhido, "r", encoding="utf-8") as f:
        produto_data = json.load(f)

# IDs de editais
edital_ids_raw = st.text_input("IDs de editais (separados por vírgula)", value="")
consulta = st.text_input("Consulta textual", value="switch 24 portas poe")

if st.button("Rodar Match"):
    if not produto_data:
        st.error("Selecione um produto cadastrado em Dataset.")
    else:
        try:
            ids = [int(x.strip()) for x in edital_ids_raw.split(",") if x.strip()]
        except ValueError:
            st.error("IDs inválidos.")
        else:
            resultados = {}
            for eid in ids:
                resp = requests.post(
                    f"{API_URL}/editais/match/{eid}",
                    params={"consulta": consulta},
                    json=produto_data,
                )
                if resp.status_code == 200:
                    # A API retorna um JSON vindo do LLM (string JSON). Tentamos parse.
                    try:
                        llm_json = json.loads(resp.json().get("resultado_llm", "[]"))
                    except Exception:
                        llm_json = resp.json()
                    resultados[eid] = llm_json
                else:
                    resultados[eid] = {"erro": resp.text}
            st.subheader("Resultados")
            st.json(resultados)
