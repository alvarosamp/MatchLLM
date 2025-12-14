import streamlit as st 

st.title("Dashboard - Licitação com IA")
st.write("Navegue pelas sessões no menu lateral:")
st.markdown("- Datasheet: envie o PDF do datasheet do produto; o sistema extrai e salva JSON em data/produtos.")
st.markdown("- Editais: envie um ou mais PDFs para processamento e indexação (gera IDs).")
st.markdown("- Match: selecione um produto salvo e informe IDs dos editais para comparar.")