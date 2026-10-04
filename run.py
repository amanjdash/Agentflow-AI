"""AgentFlow universal launcher - runnable from any directory."""

import sys
from pathlib import Path

# Ensure project root is in sys.path regardless of where the command is invoked
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Install resilient DNS fallback before any network calls
try:
    from app.services.dns_fallback import install_dns_fallback
    install_dns_fallback()
except Exception:
    pass

from app.__main__ import run_cli

if __name__ == "__main__":
    run_cli()
