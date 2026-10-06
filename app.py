import os
import re
import secrets
import sqlite3
from urllib.parse import urlparse

from flask import Flask, g, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

FLOWERS = {"rose", "tulip", "sunflower", "cherry", "lavender", "daisy"}
VISIBILITIES = {"private", "public"}
MAX_MESSAGE = 2000
MAX_NAME = 60
SPOTIFY_PATH_RE = re.compile(
    r"^/embed/(track|album|playlist|episode|show|artist)/[A-Za-z0-9]{10,40}/?$"
)
PUBLIC_ID_RE = re.compile(r"^[a-f0-9]{6,32}$")

app = Flask(__name__)


# ---------- database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            db.executescript(f.read())


# ---------- helpers ----------
class ValidationError(Exception):
    pass


def error(message, status):
    return jsonify({"success": False, "error": message}), status


def clean_spotify_url(raw):
    """Return canonical Spotify embed URL, '' if empty, raise if invalid."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        u = urlparse(raw)
    except ValueError:
        raise ValidationError("Spotify URL is not a valid URL")
    if u.scheme != "https" or u.hostname != "open.spotify.com" or u.port not in (None, 443):
        raise ValidationError("Spotify URL must be an https://open.spotify.com/embed/... link")
    if not SPOTIFY_PATH_RE.match(u.path):
        raise ValidationError("Spotify URL must be an embed URL, e.g. https://open.spotify.com/embed/track/...")
    return "https://open.spotify.com" + u.path.rstrip("/")


def validate_letter(data):
    if not isinstance(data, dict):
        raise ValidationError("Invalid JSON body")
    message = data.get("message")
    message = message.strip() if isinstance(message, str) else ""
    if not message:
        raise ValidationError("Message is required")
    if len(message) > MAX_MESSAGE:
        raise ValidationError("Message is too long (max %d characters)" % MAX_MESSAGE)

    flower = data.get("flower_type")
    if flower not in FLOWERS:
        raise ValidationError("Invalid flower type")
    visibility = data.get("visibility")
    if visibility not in VISIBILITIES:
        raise ValidationError("Visibility must be 'private' or 'public'")

    is_anon = data.get("is_anonymous", True)
    if not isinstance(is_anon, bool):
        raise ValidationError("is_anonymous must be a boolean")
    sender = data.get("sender_name")
    sender = sender.strip() if isinstance(sender, str) else ""
    if is_anon:
        sender = ""
    elif not sender:
        raise ValidationError("Your name is required when not anonymous")
    if len(sender) > MAX_NAME:
        raise ValidationError("Name is too long (max %d characters)" % MAX_NAME)

    recipient = data.get("recipient_name")
    recipient = recipient.strip() if isinstance(recipient, str) else ""
    if len(recipient) > MAX_NAME:
        raise ValidationError("Recipient name is too long (max %d characters)" % MAX_NAME)

    return {
        "sender_name": sender,
        "is_anonymous": 1 if is_anon else 0,
        "recipient_name": recipient,
        "message": message,
        "spotify_url": clean_spotify_url(data.get("spotify_url")),
        "flower_type": flower,
        "visibility": visibility,
    }


def letter_json(row):
    anon = bool(row["is_anonymous"])
    return {
        "public_id": row["public_id"],
        "sender_name": "" if anon else (row["sender_name"] or ""),
        "is_anonymous": anon,
        "recipient_name": row["recipient_name"] or "",
        "message": row["message"],
        "spotify_url": row["spotify_url"] or "",
        "flower_type": row["flower_type"],
        "visibility": row["visibility"],
        "created_at": row["created_at"],
    }


# ---------- pages ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/letter/<public_id>")
def letter_page(public_id):
    # Same page/design; the JS loads the letter by id from the URL.
    return render_template("index.html")


# ---------- API ----------
@app.route("/api/health")
def health():
    return jsonify({"success": True, "status": "ok"})


@app.route("/api/letters", methods=["POST"])
def create_letter():
    data = request.get_json(silent=True)
    try:
        v = validate_letter(data)
    except ValidationError as e:
        return error(str(e), 400)
    db = get_db()
    try:
        for _ in range(5):
            public_id = secrets.token_hex(5)
            try:
                db.execute(
                    "INSERT INTO letters (public_id, sender_name, is_anonymous, recipient_name,"
                    " message, spotify_url, flower_type, visibility)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (public_id, v["sender_name"], v["is_anonymous"], v["recipient_name"],
                     v["message"], v["spotify_url"], v["flower_type"], v["visibility"]),
                )
                db.commit()
                break
            except sqlite3.IntegrityError:
                db.rollback()
        else:
            return error("Could not generate a unique id", 500)
        row = db.execute("SELECT * FROM letters WHERE public_id = ?", (public_id,)).fetchone()
    except sqlite3.Error:
        return error("Server error", 500)
    share_path = "/letter/" + public_id
    return jsonify({
        "success": True,
        "public_id": public_id,
        "share_url": request.host_url.rstrip("/") + share_path,
        "share_path": share_path,
        "letter": letter_json(row),
    }), 201


@app.route("/api/letters/public")
def public_letters():
    try:
        rows = get_db().execute(
            "SELECT * FROM letters WHERE visibility = 'public' ORDER BY id DESC LIMIT 24"
        ).fetchall()
    except sqlite3.Error:
        return error("Server error", 500)
    letters = []
    for r in rows:
        anon = bool(r["is_anonymous"])
        letters.append({
            "public_id": r["public_id"],
            "sender_name": "Anonymous" if anon or not r["sender_name"] else r["sender_name"],
            "recipient_name": r["recipient_name"] or "",
            "message": r["message"],
            "flower_type": r["flower_type"],
            "created_at": r["created_at"],
        })
    return jsonify({"success": True, "letters": letters})


@app.route("/api/letters/<public_id>")
def get_letter(public_id):
    if not PUBLIC_ID_RE.match(public_id):
        return error("Letter not found", 404)
    try:
        row = get_db().execute("SELECT * FROM letters WHERE public_id = ?", (public_id,)).fetchone()
    except sqlite3.Error:
        return error("Server error", 500)
    if row is None:
        return error("Letter not found", 404)
    return jsonify({"success": True, "letter": letter_json(row)})


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return error("Not found", 404)
    return "Not found", 404


@app.errorhandler(500)
def server_error(_e):
    if request.path.startswith("/api/"):
        return error("Server error", 500)
    return "Server error", 500


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
