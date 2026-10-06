# Send Me a Letter

Flask + SQLite backend for the existing "send me a letter" frontend.

## Run (Windows)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Database

`database.db` is created automatically from `schema.sql` on startup (safe to re-run, uses `IF NOT EXISTS`).
To create it manually:

```bash
python -c "import sqlite3; sqlite3.connect('database.db').executescript(open('schema.sql').read())"
```

## API

- `POST /api/letters` – create a letter
- `GET /api/letters/<public_id>` – fetch one letter (private ones too, by exact id)
- `GET /api/letters/public` – public letters for the Garden
- `GET /api/health`

Letters are opened at `/letter/<public_id>`.

## Spotify

Paste a Spotify **embed** URL, e.g. `https://open.spotify.com/embed/track/<id>`
(Spotify: Share → Embed → copy the `src`). Only `open.spotify.com/embed/...` is accepted.
