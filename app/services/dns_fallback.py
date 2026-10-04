"""Resilient DNS resolution fallback for Windows/VPN/firewall environments.

Automatically intercepts and recovers from `socket.gaierror: [Errno 11002]` or SERVFAIL
errors caused by local DNS proxy utilities (such as Portmaster or corporate firewalls)
by querying local nameservers or using cached authoritative IPs.
"""

from __future__ import annotations

import re
import socket
import subprocess
import threading
from typing import Dict, List, Optional

from app.services.logging import get_logger

logger = get_logger("agentflow.dns")

_orig_getaddrinfo = socket.getaddrinfo
_dns_cache: Dict[str, str] = {
    # Well-known fallback Google API IPs in case local resolver is blocked
    "generativelanguage.googleapis.com": "172.217.119.4",
}
_cache_lock = threading.Lock()
_installed = False


def _resolve_with_nslookup(host: str) -> Optional[str]:
    """Resolves an IPv4 address for host using system nslookup command."""
    try:
        out = subprocess.check_output(
            ["nslookup", "-type=A", host],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3.0,
        )
        # Parse output for 'Addresses: <ip>' or 'Address: <ip>'
        match = re.search(r"Name:\s+" + re.escape(host) + r"\s+Addresses?:\s+((?:[\d\.]+\s*)+)", out)
        if match:
            ips = [ip.strip() for ip in match.group(1).split() if ip.strip() and not ip.startswith("0.")]
            if ips:
                return ips[0]

        # Alternative format (non-authoritative answer directly followed by Address)
        ip_matches = re.findall(r"Address:\s+([\d\.]+)", out)
        for ip in ip_matches:
            if ip not in ("127.0.0.1", "0.0.0.0", "192.168.0.1") and not ip.startswith("0."):
                return ip
    except Exception as exc:
        logger.debug(f"nslookup fallback for {host} failed: {exc}")
    return None


def resilient_getaddrinfo(host, port, *args, **kwargs):
    """Wrapper around socket.getaddrinfo with automatic DNS fallback recovery."""
    try:
        return _orig_getaddrinfo(host, port, *args, **kwargs)
    except socket.gaierror as gai_err:
        # Check if error is Errno 11002 (WSANO_DATA) or name resolution failure
        if isinstance(host, str) and not host.replace(".", "").isdigit():
            with _cache_lock:
                cached_ip = _dns_cache.get(host)

            if not cached_ip:
                resolved_ip = _resolve_with_nslookup(host)
                if resolved_ip:
                    with _cache_lock:
                        _dns_cache[host] = resolved_ip
                    cached_ip = resolved_ip

            if cached_ip:
                logger.info(f"Recovered DNS resolution for '{host}' -> {cached_ip} via fallback")
                return _orig_getaddrinfo(cached_ip, port, *args, **kwargs)

        raise gai_err


def install_dns_fallback() -> None:
    """Installs the DNS fallback handler into Python's socket module."""
    global _installed
    if not _installed:
        socket.getaddrinfo = resilient_getaddrinfo
        _installed = True
        logger.info("Resilient DNS fallback handler installed successfully")
