"""Script to initialize and seed the AgentFlow SQLite database."""

import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.seed import seed_database
from app.database.connection import get_default_db_path


def main() -> None:
    print("AgentFlow: Initializing SQLite database...")
    db_path = get_default_db_path()
    seeded_path = seed_database(db_path)
    print(f"AgentFlow: Database successfully created and seeded at: {seeded_path}")


if __name__ == "__main__":
    main()
