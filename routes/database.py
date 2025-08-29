import sqlite3
from pathlib import Path
from flask import current_app, g
from ingestion.extract import sha256_text

TOK_VER = 1  # increment if tokenization changes
SEG_VER = 1  # increment if segmentation changes

def get_db():
    if "db" not in g:
        db_path = current_app.config.get("DB_PATH", "data/app.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    db = get_db()
    db.execute(
        """
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                title TEXT,
                file_hash TEXT NOT NULL,
                modified_at INTEGER NOT NULL
            );
        """
    )
    db.execute(
        """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                page_start INTEGER,
                page_end INTEGER,
                section TEXT,
                chunk_hash TEXT NOT NULL,
                content_hash TEXT NOT NULL,        -- includes versioning flags
                text TEXT NOT NULL,
                FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
            );
        """
    )
    db.execute(
        """
            CREATE TABLE IF NOT EXISTS embeddings (
                chunk_id TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector BLOB NOT NULL,
                FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id)
            );
        """
    )
    db.execute(
        """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_doc_hash ON chunks(doc_id, chunk_hash);
        """
    )
    db.execute(
        """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_embeddings_chunk_model ON embeddings(chunk_id, model);
        """
    )
    db.commit()

def upsert_document(db, doc_id: str, source_path: str, norm_text: str, mtime: float) -> bool:
    file_hash = sha256_text(norm_text)
    cur = db.execute("SELECT file_hash FROM documents WHERE doc_id=?", (doc_id,))
    row = cur.fetchone()
    if row and row["file_hash"] == file_hash:
        return False  # no change
    db.execute("REPLACE INTO documents(doc_id, source_path, file_hash, modified_at) VALUES (?,?,?,?)",
               (doc_id, source_path, file_hash, int(mtime)))
    db.commit()
    return True  # changed, proceed to re-chunk

def persist_chunk(db, doc_id, text, page_s, page_e, section):
    chunk_hash = sha256_text(text)
    content_hash = sha256_text(f"{text}|tok={TOK_VER}|seg={SEG_VER}")
    chunk_id = f"{doc_id}:{chunk_hash[:12]}"
    db.execute("""REPLACE INTO chunks(chunk_id, doc_id, page_start, page_end, section, chunk_hash, content_hash, text)
               VALUES (?,?,?,?,?,?,?,?)""",
               (chunk_id, doc_id, page_s, page_e, section, chunk_hash, content_hash, text))
    db.commit()
    return chunk_id, content_hash

# def embed_if_needed(db, chunk_id, content_hash, model):
#     have = db.one("SELECT 1 FROM embeddings WHERE chunk_id=? AND model=?", (chunk_id, model))
#     if have: 
#         return  # cached
#     vec = embed([db.one("SELECT text FROM chunks WHERE chunk_id=?", (chunk_id,))["text"]])[0]
#     db.exec("REPLACE INTO embeddings(chunk_id, model, dim, vector) VALUES (?,?,?,?)",
#             (chunk_id, model, len(vec), vec.tobytes()))
