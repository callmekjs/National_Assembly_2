CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    chunk_id VARCHAR(255) UNIQUE NOT NULL,
    source_id VARCHAR(255),
    text TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunks_source_id ON chunks(source_id);

CREATE TABLE IF NOT EXISTS embeddings_e5 (
    id SERIAL PRIMARY KEY,
    chunk_id VARCHAR(255) REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_e5_chunk_id ON embeddings_e5(chunk_id);
