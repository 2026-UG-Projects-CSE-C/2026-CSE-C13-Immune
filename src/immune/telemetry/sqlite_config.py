"""Central SQLite connection policy used by writers and verification readers."""

from __future__ import annotations

import sqlite3


def sqlite_path(database_url: str) -> str:
    prefix = "sqlite:///"
    path = database_url[len(prefix) :] if database_url.startswith(prefix) else ""
    return path or ":memory:"


def configure_sqlite(dbapi_connection: sqlite3.Connection, _: object) -> None:
    dbapi_connection.execute("PRAGMA foreign_keys=ON")
    dbapi_connection.execute("PRAGMA busy_timeout=1000")


def open_read_only(database_url: str) -> sqlite3.Connection:
    path = sqlite_path(database_url)
    connection = sqlite3.connect(
        f"file:{path}?mode=ro", uri=True, check_same_thread=False
    )
    connection.execute("PRAGMA query_only=ON")
    connection.row_factory = sqlite3.Row
    return connection
