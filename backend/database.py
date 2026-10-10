import sqlite3
import os

# CRAFTPROOF_DB lets the tests (and a deployment) point at a different file.
DB_PATH = os.environ.get(
    "CRAFTPROOF_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "craftproof.db"),
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(128) NOT NULL,
        email VARCHAR(128) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(32) NOT NULL,
        shop_name VARCHAR(128),
        public_key TEXT NOT NULL,
        encrypted_privkey TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS pieces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        certificate_code VARCHAR(16) UNIQUE NOT NULL,
        title VARCHAR(128) NOT NULL,
        description TEXT,
        materials VARCHAR(255),
        photo_url TEXT,
        made_by INTEGER REFERENCES users(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        current_owner_id INTEGER REFERENCES users(id)
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS custody_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        piece_id INTEGER REFERENCES pieces(id),
        seq_index INTEGER NOT NULL,
        from_user_id INTEGER REFERENCES users(id),
        to_user_id INTEGER REFERENCES users(id),
        to_name VARCHAR(128),
        note TEXT,
        timestamp TEXT NOT NULL,
        prev_hash VARCHAR(64) NOT NULL,
        record_hash VARCHAR(64) NOT NULL,
        signature TEXT NOT NULL,
        UNIQUE(piece_id, seq_index)
    )
    ''')

    # Physical-fingerprint commitments (W4): a piece may carry the SHA-256
    # digest of its enrolled physical template. NULL = legacy piece with no
    # fingerprint; verification falls back to the digital-history-only path.
    def _add_column_if_missing(table: str, column: str, decl: str):
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    _add_column_if_missing('pieces', 'fingerprint_commitment', 'VARCHAR(64)')

    c.execute('''
    CREATE TABLE IF NOT EXISTS verification_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        piece_id INTEGER NOT NULL REFERENCES pieces(id),
        certificate_code VARCHAR(16) NOT NULL,
        verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        similarity REAL,
        matched INTEGER,
        impression TEXT
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS merkle_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_index INTEGER UNIQUE NOT NULL,
        root_hash VARCHAR(64) NOT NULL,
        record_ids TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.commit()
    conn.close()

# Always call init to ensure tables exist
init_db()
