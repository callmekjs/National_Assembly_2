-- Plan B: v2 스키마. v1 테이블(chunks, embeddings_e5)은 건드리지 않는다.

CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────────────────────
-- chunks_v2: ETL v2 청크 (raw_text / clean_text / embed_text 분리)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks_v2 (
    id          SERIAL PRIMARY KEY,
    chunk_id    VARCHAR(255) UNIQUE NOT NULL,
    source_id   VARCHAR(255),
    page_no     INTEGER,
    turn_index  INTEGER,
    section_type VARCHAR(20),
    speaker     VARCHAR(255),
    speaker_role VARCHAR(100),
    raw_text    TEXT NOT NULL,
    clean_text  TEXT NOT NULL,
    embed_text  TEXT NOT NULL,
    metadata    JSONB,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 기본 조회 인덱스
CREATE INDEX IF NOT EXISTS idx_chunks_v2_source_id
    ON chunks_v2(source_id);

-- metadata 내부 필드 인덱스 (위원회 필터링)
CREATE INDEX IF NOT EXISTS idx_chunks_v2_committee
    ON chunks_v2 ((metadata->>'committee'));

-- metadata 내부 필드 인덱스 (날짜 필터링)
CREATE INDEX IF NOT EXISTS idx_chunks_v2_meeting_date
    ON chunks_v2 ((metadata->>'meeting_date'));

-- 발언자 필터링
CREATE INDEX IF NOT EXISTS idx_chunks_v2_speaker
    ON chunks_v2(speaker);

-- section_type 필터링 (body만 임베딩/검색)
CREATE INDEX IF NOT EXISTS idx_chunks_v2_section_type
    ON chunks_v2(section_type);

-- PostgreSQL FTS (한국어 기본 설정 simple 사용)
CREATE INDEX IF NOT EXISTS idx_chunks_v2_fts
    ON chunks_v2 USING gin(to_tsvector('simple', clean_text));

-- ─────────────────────────────────────────────────────────────
-- embeddings_e5_v2: embed_text 기반 임베딩 (section_type=body만)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS embeddings_e5_v2 (
    id          SERIAL PRIMARY KEY,
    chunk_id    VARCHAR(255) REFERENCES chunks_v2(chunk_id) ON DELETE CASCADE,
    embedding   vector(1024) NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_e5_v2_chunk_id
    ON embeddings_e5_v2(chunk_id);

-- pgvector HNSW 인덱스 (cosine distance, 검색 속도 향상)
-- 주의: 데이터 적재 완료 후 실행할 것 (적재 중 HNSW는 느림)
-- CREATE INDEX idx_embeddings_e5_v2_hnsw
--     ON embeddings_e5_v2 USING hnsw (embedding vector_cosine_ops);
