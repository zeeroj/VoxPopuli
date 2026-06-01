import sqlite3
import os
from config import DB_PATH


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keywords TEXT NOT NULL,
            date_from TEXT,
            date_to TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            status TEXT DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            post_id TEXT NOT NULL,
            url TEXT,
            caption TEXT,
            image_url TEXT,
            posted_at TEXT,
            scraped_at TEXT DEFAULT (datetime('now')),
            is_poll INTEGER DEFAULT 0,
            poll_data TEXT,
            poll_reactions TEXT,
            FOREIGN KEY (search_id) REFERENCES searches(id),
            UNIQUE(platform, post_id)
        );

        CREATE TABLE IF NOT EXISTS reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            reaction_type TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            FOREIGN KEY (post_id) REFERENCES posts(id)
        );

        CREATE TABLE IF NOT EXISTS post_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            candidate_key TEXT NOT NULL,
            confidence REAL DEFAULT 0.0,
            detection_method TEXT DEFAULT 'unknown',
            FOREIGN KEY (post_id) REFERENCES posts(id),
            FOREIGN KEY (candidate_key) REFERENCES candidates(key)
        );

        CREATE TABLE IF NOT EXISTS candidates (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            party TEXT,
            color TEXT
        );

        CREATE TABLE IF NOT EXISTS face_encodings (
            candidate_key TEXT NOT NULL,
            encoding_index INTEGER NOT NULL,
            encoding_blob BLOB NOT NULL,
            PRIMARY KEY (candidate_key, encoding_index),
            FOREIGN KEY (candidate_key) REFERENCES candidates(key)
        );

        CREATE INDEX IF NOT EXISTS idx_posts_search ON posts(search_id);
        CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform);
        CREATE INDEX IF NOT EXISTS idx_posts_posted_at ON posts(posted_at);
        CREATE INDEX IF NOT EXISTS idx_post_candidates_candidate ON post_candidates(candidate_key);
        CREATE INDEX IF NOT EXISTS idx_reactions_post ON reactions(post_id);
    """)
    conn.commit()
    try:
        conn.execute("ALTER TABLE posts ADD COLUMN poll_data TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE posts ADD COLUMN poll_reactions TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()
