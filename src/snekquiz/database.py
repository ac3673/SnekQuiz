"""SQLite database layer using aiosqlite."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Return the current database connection."""
    if _db is None:
        msg = "Database not initialised - call init_db() first"
        raise RuntimeError(msg)
    return _db


async def init_db(db_path: str) -> None:
    """Open (or create) the database and ensure the schema exists."""
    global _db

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    _db = await aiosqlite.connect(str(path))
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")

    await _db.executescript(
        """
        CREATE TABLE IF NOT EXISTS quizzes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            data_json   TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS attempts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL,
            quiz_id     INTEGER NOT NULL REFERENCES quizzes(id),
            score       INTEGER NOT NULL,
            total       INTEGER NOT NULL,
            answers_json TEXT   NOT NULL,
            completed_at TEXT   NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_attempts_user
            ON attempts(username);

        CREATE TABLE IF NOT EXISTS quiz_progress (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT    NOT NULL,
            quiz_id      INTEGER NOT NULL REFERENCES quizzes(id),
            question_id  INTEGER NOT NULL,
            answers_json TEXT    NOT NULL,
            updated_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(username, quiz_id, question_id)
        );

        CREATE INDEX IF NOT EXISTS idx_progress_user_quiz
            ON quiz_progress(username, quiz_id);

        CREATE TABLE IF NOT EXISTS users (
            username    TEXT PRIMARY KEY,
            full_name   TEXT NOT NULL
        );
        """
    )
    await _db.commit()
    logger.info("Database initialised at %s", db_path)


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
        logger.info("Database closed")


# ---------------------------------------------------------------------------
# Quiz CRUD
# ---------------------------------------------------------------------------


async def insert_quiz(name: str, data_json: str) -> int:
    """Insert a new quiz, returning its id."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO quizzes (name, data_json) VALUES (?, ?)",
        (name, data_json),
    )
    await db.commit()
    logger.info("Inserted quiz %r (id=%s)", name, cursor.lastrowid)
    return cursor.lastrowid  # type: ignore[return-value]


async def get_all_quizzes() -> list[dict]:
    """Return lightweight list of all quizzes."""
    db = await get_db()
    cursor = await db.execute("SELECT id, name, created_at FROM quizzes ORDER BY id")
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_quiz_by_id(quiz_id: int) -> dict | None:
    """Return a single quiz with its full JSON data."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def quiz_name_exists(name: str) -> bool:
    db = await get_db()
    cursor = await db.execute("SELECT 1 FROM quizzes WHERE name = ?", (name,))
    return await cursor.fetchone() is not None


# ---------------------------------------------------------------------------
# Attempt CRUD
# ---------------------------------------------------------------------------


async def save_attempt(
    username: str,
    quiz_id: int,
    score: int,
    total: int,
    answers: dict,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO attempts"
        " (username, quiz_id, score, total, answers_json)"
        " VALUES (?, ?, ?, ?, ?)",
        (username, quiz_id, score, total, json.dumps(answers)),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def get_attempt_by_id(attempt_id: int) -> dict | None:
    """Return a single attempt by its id."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT a.*, COALESCE(u.full_name, a.username) AS full_name
        FROM attempts a
        LEFT JOIN users u ON u.username = a.username
        WHERE a.id = ?
        """,
        (attempt_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_user_attempts(username: str) -> list[dict]:
    """Return all attempts for a user."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM attempts WHERE username = ? ORDER BY completed_at DESC",
        (username,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_completed_quiz_ids(username: str) -> set[int]:
    """Return set of quiz ids the user has completed at least once."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT DISTINCT quiz_id FROM attempts WHERE username = ?",
        (username,),
    )
    rows = await cursor.fetchall()
    return {row["quiz_id"] for row in rows}


async def get_quiz_stats() -> list[dict]:
    """Return aggregated stats per quiz for the admin dashboard."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT
            q.id            AS quiz_id,
            q.name          AS quiz_name,
            COUNT(a.id)     AS attempt_count,
            COUNT(DISTINCT a.username) AS unique_users,
            ROUND(AVG(a.score * 100.0 / a.total), 1) AS avg_score_pct,
            MAX(a.score * 100.0 / a.total) AS best_score_pct,
            MIN(a.score * 100.0 / a.total) AS worst_score_pct
        FROM quizzes q
        LEFT JOIN attempts a ON a.quiz_id = q.id
        GROUP BY q.id, q.name
        ORDER BY q.id
        """
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_quiz_attempts(quiz_id: int) -> list[dict]:
    """Return all attempts for a specific quiz (admin drilldown)."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT
            a.id, a.username,
            COALESCE(u.full_name, a.username) AS full_name,
            a.score, a.total,
            ROUND(a.score * 100.0 / a.total, 1) AS score_pct,
            a.answers_json,
            a.completed_at
        FROM attempts a
        LEFT JOIN users u ON u.username = a.username
        WHERE a.quiz_id = ?
        ORDER BY a.completed_at DESC
        """,
        (quiz_id,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def delete_quiz(quiz_id: int) -> bool:
    """Delete a quiz and all its attempts/progress. Returns True if the quiz existed."""
    db = await get_db()
    await db.execute("DELETE FROM quiz_progress WHERE quiz_id = ?", (quiz_id,))
    await db.execute("DELETE FROM attempts WHERE quiz_id = ?", (quiz_id,))
    cursor = await db.execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
    await db.commit()
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Quiz progress (incremental, per-question persistence)
# ---------------------------------------------------------------------------


async def save_progress_answer(
    username: str,
    quiz_id: int,
    question_id: int,
    answers: list[str],
) -> None:
    """Upsert a single question's answers into the progress table."""
    db = await get_db()
    await db.execute(
        "INSERT INTO quiz_progress (username, quiz_id, question_id, answers_json)"
        " VALUES (?, ?, ?, ?)"
        " ON CONFLICT(username, quiz_id, question_id)"
        " DO UPDATE SET answers_json = excluded.answers_json,"
        "              updated_at   = datetime('now')",
        (username, quiz_id, question_id, json.dumps(answers)),
    )
    await db.commit()


async def get_progress(username: str, quiz_id: int) -> dict[int, list[str]]:
    """Return saved progress as ``{question_id: [answer_ids, ...]}``."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT question_id, answers_json FROM quiz_progress WHERE username = ? AND quiz_id = ?",
        (username, quiz_id),
    )
    rows = await cursor.fetchall()
    return {row["question_id"]: json.loads(row["answers_json"]) for row in rows}


async def delete_progress(username: str, quiz_id: int) -> None:
    """Remove all saved progress for a user/quiz pair."""
    db = await get_db()
    await db.execute(
        "DELETE FROM quiz_progress WHERE username = ? AND quiz_id = ?",
        (username, quiz_id),
    )
    await db.commit()


async def upsert_user(username: str, full_name: str) -> None:
    """Insert or update a user's full name."""
    db = await get_db()
    await db.execute(
        "INSERT INTO users (username, full_name) VALUES (?, ?)"
        " ON CONFLICT(username) DO UPDATE SET full_name = excluded.full_name",
        (username, full_name),
    )
    await db.commit()


async def get_in_progress_quiz_ids(username: str) -> set[int]:
    """Return quiz ids where the user has saved progress but no completed attempt yet."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT DISTINCT p.quiz_id FROM quiz_progress p WHERE p.username = ?",
        (username,),
    )
    rows = await cursor.fetchall()
    return {row["quiz_id"] for row in rows}
