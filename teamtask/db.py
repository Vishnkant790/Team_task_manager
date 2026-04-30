import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from .config import DATABASE_URL, SQLITE_PATH


USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_members (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('ADMIN', 'MEMBER')),
        created_at TEXT NOT NULL,
        UNIQUE (project_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL CHECK (status IN ('TODO', 'IN_PROGRESS', 'DONE')) DEFAULT 'TODO',
        priority TEXT NOT NULL CHECK (priority IN ('LOW', 'MEDIUM', 'HIGH')) DEFAULT 'MEDIUM',
        due_date TEXT NOT NULL,
        assignee_id TEXT REFERENCES users(id) ON DELETE SET NULL,
        created_by_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
]


def _prepare_sql(sql: str) -> str:
    if USE_POSTGRES:
        return sql.replace("?", "%s")
    return sql


def _connect():
    if USE_POSTGRES:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    Path(SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(conn, sql: str, params: Iterable[Any] = ()):
    cur = conn.execute(_prepare_sql(sql), tuple(params))
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


def fetch_all(conn, sql: str, params: Iterable[Any] = ()):
    cur = conn.execute(_prepare_sql(sql), tuple(params))
    return [dict(row) for row in cur.fetchall()]


def execute(conn, sql: str, params: Iterable[Any] = ()):
    return conn.execute(_prepare_sql(sql), tuple(params))


def init_db() -> None:
    with connection() as conn:
        for statement in SCHEMA:
            execute(conn, statement)
