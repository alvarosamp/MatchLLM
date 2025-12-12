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
