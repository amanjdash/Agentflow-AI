"""AgentFlow - Autonomous Multi-Tool AI Agent Package."""

__version__ = "1.0.0"

# Install resilient DNS fallback to protect against Portmaster/proxy resolution failures
try:
    from app.services.dns_fallback import install_dns_fallback
    install_dns_fallback()
except Exception:
    pass
