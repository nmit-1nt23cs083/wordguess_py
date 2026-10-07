"""SQLite database layer: schema, seed data and small helper queries."""
import random
import sqlite3
from datetime import date

from werkzeug.security import generate_password_hash

# Twenty 5-letter English words (upper case) saved to the database to start with.
SEED_WORDS = [
    "APPLE", "BRAVE", "CHAIR", "DANCE", "EAGLE",
    "FLAME", "GRAPE", "HOUSE", "IMAGE", "JOKER",
    "LEMON", "MANGO", "NIGHT", "OCEAN", "PIANO",
    "QUEEN", "RIVER", "TIGER", "TOWER", "WATER",
]

# Default admin account (created on first run). Change it after first login in real use.
DEFAULT_ADMIN_USERNAME = "Admin"
DEFAULT_ADMIN_PASSWORD = "Admin$123"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'player')),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS words (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL UNIQUE
);

-- One row per game: the word given to the user and how it ended.
CREATE TABLE IF NOT EXISTS games (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES users(id),
    word_id   INTEGER NOT NULL REFERENCES words(id),
    game_date TEXT NOT NULL,                    -- YYYY-MM-DD
    status    TEXT NOT NULL DEFAULT 'active'
              CHECK (status IN ('active', 'won', 'lost')),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_games_user_date ON games(user_id, game_date);

-- Every word guessed by the user for a game.
CREATE TABLE IF NOT EXISTS guesses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id    INTEGER NOT NULL REFERENCES games(id),
    guess_no   INTEGER NOT NULL,
    guess      TEXT NOT NULL,
    guess_date TEXT NOT NULL,                   -- YYYY-MM-DD
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (game_id, guess_no)
);
"""


def today():
    """Today's date as YYYY-MM-DD (a function so tests can replace it)."""
    return date.today().isoformat()


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    """Create tables and seed the words and the default admin user (idempotent)."""
    conn.executescript(SCHEMA)
    conn.executemany("INSERT OR IGNORE INTO words (word) VALUES (?)",
                     [(w,) for w in SEED_WORDS])
    exists = conn.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            (DEFAULT_ADMIN_USERNAME, generate_password_hash(DEFAULT_ADMIN_PASSWORD)),
        )
    conn.commit()


# ---------- users ----------

def get_user_by_name(conn, username):
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_player(conn, username, password):
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'player')",
        (username, generate_password_hash(password)),
    )
    conn.commit()


# ---------- games ----------

def games_played_today(conn, user_id, day):
    return conn.execute(
        "SELECT COUNT(*) FROM games WHERE user_id = ? AND game_date = ?",
        (user_id, day),
    ).fetchone()[0]


def get_active_game(conn, user_id):
    return conn.execute(
        "SELECT * FROM games WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()


def pick_random_word(conn, user_id):
    """Pick a random word, preferring ones this user has not been given before."""
    rows = conn.execute(
        "SELECT id, word FROM words WHERE id NOT IN "
        "(SELECT word_id FROM games WHERE user_id = ?)",
        (user_id,),
    ).fetchall()
    if not rows:
        rows = conn.execute("SELECT id, word FROM words").fetchall()
    return random.choice(rows)


def start_game(conn, user_id, day):
    word = pick_random_word(conn, user_id)
    cur = conn.execute(
        "INSERT INTO games (user_id, word_id, game_date) VALUES (?, ?, ?)",
        (user_id, word["id"], day),
    )
    conn.commit()
    return cur.lastrowid


def get_game(conn, game_id):
    """Game row joined with its secret word."""
    return conn.execute(
        "SELECT g.*, w.word FROM games g JOIN words w ON w.id = g.word_id WHERE g.id = ?",
        (game_id,),
    ).fetchone()


def get_guesses(conn, game_id):
    return conn.execute(
        "SELECT guess_no, guess FROM guesses WHERE game_id = ? ORDER BY guess_no",
        (game_id,),
    ).fetchall()


def add_guess(conn, game_id, guess_no, guess, day):
    conn.execute(
        "INSERT INTO guesses (game_id, guess_no, guess, guess_date) VALUES (?, ?, ?, ?)",
        (game_id, guess_no, guess, day),
    )
    conn.commit()


def set_game_status(conn, game_id, status):
    conn.execute("UPDATE games SET status = ? WHERE id = ?", (status, game_id))
    conn.commit()


# ---------- admin report ----------

def daily_report(conn, day):
    """Summary + per-game detail for one day."""
    summary = conn.execute(
        """
        SELECT COUNT(DISTINCT user_id)                      AS users,
               COUNT(*)                                     AS games,
               COALESCE(SUM(status = 'won'), 0)             AS correct,
               COALESCE(SUM(status = 'lost'), 0)            AS lost,
               COALESCE(SUM(status = 'active'), 0)          AS in_progress
        FROM games WHERE game_date = ?
        """,
        (day,),
    ).fetchone()
    total_guesses = conn.execute(
        "SELECT COUNT(*) FROM guesses WHERE guess_date = ?", (day,)
    ).fetchone()[0]
    details = conn.execute(
        """
        SELECT g.id AS game_id, u.username, w.word, g.status,
               (SELECT COUNT(*) FROM guesses x WHERE x.game_id = g.id) AS guess_count,
               (SELECT GROUP_CONCAT(guess, ', ') FROM
                    (SELECT guess FROM guesses x WHERE x.game_id = g.id ORDER BY guess_no)
               ) AS guesses
        FROM games g
        JOIN users u ON u.id = g.user_id
        JOIN words w ON w.id = g.word_id
        WHERE g.game_date = ?
        ORDER BY u.username COLLATE NOCASE, g.id
        """,
        (day,),
    ).fetchall()
    return summary, total_guesses, details
