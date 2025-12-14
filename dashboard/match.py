import os
import streamlit as st
import requests
import json

# Dentro do Docker, o hostname do serviço da API é "api"
# Permite override via variável de ambiente
API_URL = os.getenv("API_BASE_URL", "http://api:8000")


st.title("Match Produto x Edital")

edital_id = st.number_input("ID do Edital", min_value=1, step=1)
produto_nome = st.text_input("Nome do produto")
atributos_raw = st.text_area(
    "Atributos do produto (JSON)",
    value='{"portas": 24, "poe": true}',
)
consulta = st.text_input(
    "Consulta textual para busca no edital",
    value="switch 24 portas poe",
)

if st.button("Rodar Match"):
    try:
        atributos = json.loads(atributos_raw)
    except json.JSONDecodeError:
        st.error("JSON de atributos inválido.")
    else:
        payload = {
            "nome": produto_nome,
            "atributos": atributos,
        }
        resp = requests.post(
            f"{API_URL}/editais/match/{edital_id}",
            params={"consulta": consulta},
            json=payload,
        )
        if resp.status_code == 200:
            st.json(resp.json())
        else:
            st.error(resp.text)
