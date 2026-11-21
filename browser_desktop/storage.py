"""SQLite storage for the Browser Desktop Simulator (standard library only).

Every operation opens its own short-lived connection, so the object is safe
to share between server threads. Writes run inside ``BEGIN IMMEDIATE``.
File names are only ever database keys and never filesystem paths.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_NAME = "desktop.sqlite3"
MAX_FILES = 500
MAX_TEXT_BYTES = 65536
NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")

FIXTURE_NAME = "launch-notes.txt"
FIXTURE_TEXT = "orbit alpha ready\ndock lights green\norbit beta synced\n"

MIGRATIONS = (
    (
        1,
        """CREATE TABLE files(
  name TEXT PRIMARY KEY CHECK(length(name) BETWEEN 1 AND 64),
  text TEXT NOT NULL CHECK(length(CAST(text AS BLOB)) <= 65536),
  revision INTEGER NOT NULL CHECK(revision >= 1),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
) WITHOUT ROWID""",
    ),
)
LATEST_VERSION = MIGRATIONS[-1][0]


class StorageError(Exception):
    """Base class for storage errors."""


class ValidationError(StorageError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NotFound(StorageError):
    pass


class AlreadyExists(StorageError):
    pass


class FileLimitReached(StorageError):
    pass


class Conflict(StorageError):
    def __init__(self, current: dict):
        super().__init__("revision conflict")
        self.current = current


class SchemaTooNew(StorageError):
    pass


class DataDirError(StorageError):
    pass


def validate_name(name) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name) or ".." in name:
        raise ValidationError(
            "invalid_name",
            "File names use letters, digits, '.', '_' or '-', start with a "
            "letter or digit, are at most 64 characters and contain no '..'.",
        )
    return name


def validate_text(text) -> str:
    if not isinstance(text, str):
        raise ValidationError("invalid_request", "text must be a string.")
    if "\x00" in text:
        raise ValidationError("invalid_request", "text must not contain NUL characters.")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValidationError("invalid_request", "text is not valid Unicode.") from None
    if size > MAX_TEXT_BYTES:
        raise ValidationError(
            "text_too_large", f"text is larger than {MAX_TEXT_BYTES} bytes."
        )
    return text


def validate_revision(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError(
            "invalid_request", "base_revision must be an integer of at least 1."
        )
    return value


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def prepare_data_dir(data_dir) -> Path:
    """Validate and create the data directory; raise DataDirError otherwise."""
    if not isinstance(data_dir, (str, os.PathLike)) or str(data_dir) == "":
        raise DataDirError("data directory must be a non-empty path")
    if "\x00" in str(data_dir):
        raise DataDirError("data directory path is invalid")
    try:
        path = Path(data_dir).absolute()
        if path.exists() and not path.is_dir():
            raise DataDirError(f"data directory path is not a directory: {data_dir}")
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise DataDirError(f"data directory path is not a directory: {data_dir}")
    except DataDirError:
        raise
    except (OSError, ValueError) as exc:
        raise DataDirError(f"cannot use data directory {data_dir}: {exc.__class__.__name__}") from None
    return path


class Storage:
    def __init__(self, data_dir):
        self.data_dir = prepare_data_dir(data_dir)
        self.db_path = self.data_dir / DB_NAME
        try:
            self._migrate()
        except sqlite3.Error as exc:
            raise DataDirError(f"cannot open database: {exc}") from None

    # -- plumbing ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
        except BaseException:
            conn.close()
            raise
        return conn

    @contextmanager
    def _read(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _tx(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            else:
                conn.execute("COMMIT")
        finally:
            conn.close()

    def _migrate(self) -> None:
        with self._tx() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY)"
            )
            applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
            if applied and max(applied) > LATEST_VERSION:
                raise SchemaTooNew(
                    f"database schema version {max(applied)} is newer than "
                    f"supported version {LATEST_VERSION}"
                )
            for version, sql in MIGRATIONS:
                if version not in applied:
                    conn.execute(sql)
                    conn.execute(
                        "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
                    )

    def close(self) -> None:
        """Fold the WAL into the main database file (best effort).

        No connections are held open between operations.
        """
        try:
            with self._read() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except (sqlite3.Error, OSError):
            pass

    # -- queries ----------------------------------------------------------

    @staticmethod
    def _file_dict(row) -> dict:
        name, text, revision, updated_at = row
        return {
            "name": name,
            "text": text,
            "revision": revision,
            "size": len(text.encode("utf-8")),
            "updated_at": updated_at,
        }

    def schema_version(self) -> int:
        with self._read() as conn:
            row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return row[0] or 0

    def list_files(self) -> list[dict]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT name, length(CAST(text AS BLOB)), revision, updated_at "
                "FROM files ORDER BY name"
            ).fetchall()
        return [
            {"name": n, "size": s, "revision": r, "updated_at": u} for n, s, r, u in rows
        ]

    def get_file(self, name: str) -> dict:
        validate_name(name)
        with self._read() as conn:
            row = conn.execute(
                "SELECT name, text, revision, updated_at FROM files WHERE name=?",
                (name,),
            ).fetchone()
        if row is None:
            raise NotFound(name)
        return self._file_dict(row)

    def create_file(self, name: str, text: str) -> dict:
        validate_name(name)
        validate_text(text)
        now = _now()
        with self._tx() as conn:
            if conn.execute("SELECT 1 FROM files WHERE name=?", (name,)).fetchone():
                raise AlreadyExists(name)
            if conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] >= MAX_FILES:
                raise FileLimitReached(f"at most {MAX_FILES} files are allowed")
            conn.execute(
                "INSERT INTO files(name, text, revision, created_at, updated_at) "
                "VALUES (?, ?, 1, ?, ?)",
                (name, text, now, now),
            )
        return self._file_dict((name, text, 1, now))

    def update_file(self, name: str, text: str, base_revision: int) -> dict:
        validate_name(name)
        validate_text(text)
        validate_revision(base_revision)
        now = _now()
        with self._tx() as conn:
            cur = conn.execute(
                "UPDATE files SET text=?, revision=revision+1, updated_at=? "
                "WHERE name=? AND revision=?",
                (text, now, name, base_revision),
            )
            row = conn.execute(
                "SELECT name, text, revision, updated_at FROM files WHERE name=?",
                (name,),
            ).fetchone()
            if cur.rowcount == 0:
                if row is None:
                    raise NotFound(name)
                raise Conflict(self._file_dict(row))
        return self._file_dict(row)

    def ensure_fixture(self) -> bool:
        """Create launch-notes.txt if missing. Never overwrites. Returns True if created."""
        now = _now()
        with self._tx() as conn:
            if conn.execute(
                "SELECT 1 FROM files WHERE name=?", (FIXTURE_NAME,)
            ).fetchone():
                return False
            if conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] >= MAX_FILES:
                raise FileLimitReached(f"at most {MAX_FILES} files are allowed")
            conn.execute(
                "INSERT INTO files(name, text, revision, created_at, updated_at) "
                "VALUES (?, ?, 1, ?, ?)",
                (FIXTURE_NAME, FIXTURE_TEXT, now, now),
            )
        return True
