import streamlit as st 

st.title("Dashboard - Licitação com IA")
st.write("Navegue pelas sessões no menu lateral.")

st.subheader("Como usar (bem mastigado)")
st.markdown("1) Abra **Match**")
st.markdown("2) Envie **um ou vários PDFs** de **Editais** e **Produtos (datasheets)**")
st.markdown("3) Clique em **Executar Match**")
st.markdown("4) Veja o resumo (status/score) e clique em **Baixar resultados (ZIP)**")

st.subheader("Outras páginas (opcionais)")
st.markdown("- **Datasheet**: extrai e salva um JSON do produto em `data/produtos` (útil para manter catálogo).")
st.markdown("- **Editais**: envia editais para a API (modo Docker/API).")
st.markdown("- **Dataset/Datasheet**: ajudam a cadastrar/organizar produtos (opcional no fluxo principal).")