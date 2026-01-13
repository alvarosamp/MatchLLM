CREATE TABLE IF NOT EXISTS editais (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(255),
    caminho_pdf TEXT,
    criado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS produtos (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(255),
    atributos_json JSONB,
    criado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS matches (
    id BIGSERIAL PRIMARY KEY,
    edital_id BIGINT REFERENCES editais(id),
    produto_id BIGINT REFERENCES produtos(id),
    consulta TEXT,
    resultado_llm JSONB,
    criado_em TIMESTAMP DEFAULT NOW()
);

-- Cache para evitar reprocessar PDFs repetidos
CREATE TABLE IF NOT EXISTS document_cache (
    id BIGSERIAL PRIMARY KEY,
    doc_type VARCHAR(32) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    hint_key TEXT,
    original_name TEXT,
    extracted_json JSONB NOT NULL,
    meta_json JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_cache_type_hash_hint
    ON document_cache (doc_type, sha256, COALESCE(hint_key, ''));

CREATE TABLE IF NOT EXISTS match_cache (
    id BIGSERIAL PRIMARY KEY,
    edital_sha256 VARCHAR(64) NOT NULL,
    produto_sha256 VARCHAR(64) NOT NULL,
    settings_sig TEXT NOT NULL,
    result_json JSONB NOT NULL,
    meta_json JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_match_cache_pair_settings
    ON match_cache (edital_sha256, produto_sha256, settings_sig);
