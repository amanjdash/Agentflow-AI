"""Database connection manager enforcing SQLite read-only URI mode and execution safety."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from app.safety.limits import DB_CONCURRENCY_SEMAPHORE
from app.services.logging import get_logger

logger = get_logger("agentflow.database")


def get_default_db_path() -> Path:
    """Resolves the default database path from environment or project structure."""
    env_path = os.getenv("DATABASE_PATH", "data/agentflow.db")
    return Path(env_path).resolve()


def get_readonly_connection(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Opens a strictly read-only SQLite database connection using URI parameters.

    Features:
    - Uses URI parameter `mode=ro` preventing any disk writes at the SQLite engine level.
    - Enables foreign key inspection without write privileges.
    - Sets query timeout to 5.0 seconds.
    """
    path = Path(db_path).resolve() if db_path else get_default_db_path()

    if not path.exists():
        raise FileNotFoundError(
            f"Database file not found at configured path: {path.name}. Please run the seed script."
        )

    # Construct safe URI for SQLite read-only mode
    # Standard format: file:/absolute/path?mode=ro
    posix_path = path.as_posix()
    if not posix_path.startswith("/"):
        posix_path = "/" + posix_path

    uri = f"file:{posix_path}?mode=ro"

    try:
        conn = sqlite3.connect(
            uri,
            uri=True,
            timeout=5.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as exc:
        logger.error(f"Failed to open SQLite read-only connection: {exc}")
        raise RuntimeError("Database connection could not be established in read-only mode.")
