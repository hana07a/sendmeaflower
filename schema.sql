CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT UNIQUE NOT NULL,
    sender_name TEXT,
    is_anonymous INTEGER NOT NULL DEFAULT 1,
    recipient_name TEXT,
    message TEXT NOT NULL,
    spotify_url TEXT,
    flower_type TEXT NOT NULL,
    visibility TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_letters_visibility ON letters (visibility, id);
