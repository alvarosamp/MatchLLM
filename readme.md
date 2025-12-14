## MatchLLM
Pipeline para ingestão de editais PDF, extração de texto (OCR), chunking, geração de embeddings, indexação vetorial e matching de produtos usando RAG + LLM (Ollama).

### Principais componentes
- `core/ocr`: extração de texto (PDF nativo + OCR via Doctr).
- `core/preprocess`: normalização, chunking, embeddings (SentenceTransformers).
- `core/vectorstore`: índice FAISS serializado em disco.
- `core/rag`: busca semântica e comparação via LLM.
- `api/`: FastAPI para expor ingestão/consulta.
- `dashboard/`: Streamlit para visualização simples.

### Requisitos
- Python 3.11+
- Ollama rodando localmente (padrão `http://localhost:11434`).
- Dependências em `requirements.txt` (inclui torch, transformers, sentence-transformers, pdfplumber, python-doctr, streamlit, fastapi, faiss-cpu).

### Setup
1) Criar venv e instalar deps
```bash
python -m venv .venv
.\n+venv\Scripts\activate
pip install -r requirements.txt
```
2) Baixar um modelo menor para evitar OOM na GPU (ex.: llama3.2:1b)
```bash
ollama pull llama3.2:1b
```

### Variáveis de ambiente relevantes
- `LLM_URL` (default: `http://localhost:11434`)
- `LLM_MODEL` (default: `llama3.1`; sugerido: `llama3.2:1b` ou um quantizado se GPU for limitada)

### Executar API FastAPI
```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Executar Dashboard (Streamlit)
```bash
streamlit run dashboard/home.py
```

### Scripts de teste/manual
- Ingestão + RAG direto: `python teste/teste_rag.py`
- Pipeline + match de produto: `python teste/teste_match.py`

### Estrutura de dados
- PDFs de entrada: `data/editais/`
- Índices vetoriais salvos: `data/processed/vectorstore/` (`edital_{id}_index.pkl` + `edital_{id}_chunks.pkl`)

### Fluxo básico (pipeline)
1) Extrai e normaliza texto do PDF (`PDFExtractor`, `normalize_text`).
2) Chunking (`chunk_text`).
3) Embeddings (`Embedder.encode`).
4) Indexação FAISS (`VectorIndex.add`/`save`).
5) Busca RAG (`RAGRetrivier.search`) e comparação via LLM (`Matcher.compare`).

### Resolução de problemas
- Erro 500 no Ollama com "unable to allocate CUDA0 buffer": use um modelo menor ou quantizado (`LLM_MODEL=llama3.2:1b`).
- `ModuleNotFoundError: core`: certifique-se de rodar a partir da raiz do projeto ou adicionar `Path(__file__).parent.parent` ao `sys.path` (já feito nos scripts de teste).

### Testes
```bash
pytest
```
