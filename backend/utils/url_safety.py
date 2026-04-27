"""URL-safety validators to block SSRF via tenant-controlled URLs.

Context: `TenantAIConfig.llm_base_url` is a user-editable URLField (SCHOOL_ADMIN
can set it to point at a custom LLM proxy / Azure endpoint / self-hosted model).
Without validation, a malicious admin can set it to `http://169.254.169.254/`
(AWS IMDS) or `http://localhost:6379/` (Redis on the Django host) and the
server-side LLM proxy will POST to that URL — echoing cloud metadata or
internal service responses back into the UI.

This module centralises the validator so every outbound-URL construction
in the backend uses the same rules. See ultrareview 2026-04-23 SEC-P0-3.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF-safety validation."""


# Hostnames we never allow regardless of resolution.
_BANNED_HOSTNAMES = {
    "localhost",
    "ip6-localhost",
    "ip6-loopback",
    "broadcasthost",
    "metadata",            # GCP metadata alias
    "metadata.google.internal",
}

# IP ranges we refuse to connect to (RFC1918 + loopback + link-local + cloud
# metadata + CG-NAT + multicast + private v6). A resolved hostname landing in
# any of these ranges is a red flag for SSRF.
_BANNED_V4_NETWORKS = [
    ipaddress.IPv4Network("0.0.0.0/8"),         # "this" network
    ipaddress.IPv4Network("10.0.0.0/8"),         # RFC1918
    ipaddress.IPv4Network("100.64.0.0/10"),      # CG-NAT
    ipaddress.IPv4Network("127.0.0.0/8"),        # loopback
    ipaddress.IPv4Network("169.254.0.0/16"),     # link-local + AWS/GCP IMDS
    ipaddress.IPv4Network("172.16.0.0/12"),      # RFC1918
    ipaddress.IPv4Network("192.0.0.0/24"),       # IETF protocol
    ipaddress.IPv4Network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.IPv4Network("192.168.0.0/16"),     # RFC1918
    ipaddress.IPv4Network("198.18.0.0/15"),      # benchmarking
    ipaddress.IPv4Network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.IPv4Network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.IPv4Network("224.0.0.0/4"),        # multicast
    ipaddress.IPv4Network("240.0.0.0/4"),        # reserved
    ipaddress.IPv4Network("255.255.255.255/32"), # broadcast
]
_BANNED_V6_NETWORKS = [
    ipaddress.IPv6Network("::1/128"),            # loopback
    ipaddress.IPv6Network("::/128"),             # unspecified
    ipaddress.IPv6Network("fc00::/7"),           # unique-local
    ipaddress.IPv6Network("fe80::/10"),          # link-local
    ipaddress.IPv6Network("ff00::/8"),           # multicast
    ipaddress.IPv6Network("fec0::/10"),          # deprecated site-local
]


def _ip_is_banned(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # can't parse = don't trust
    if isinstance(addr, ipaddress.IPv4Address):
        return any(addr in net for net in _BANNED_V4_NETWORKS)
    return any(addr in net for net in _BANNED_V6_NETWORKS)


def validate_outbound_url(
    raw_url: str,
    *,
    allowed_schemes: tuple[str, ...] = ("https",),
    resolve_dns: bool = True,
) -> str:
    """Validate a URL is safe for server-side outbound fetch.

    Rules:
      - Must parse.
      - Scheme must be in ``allowed_schemes`` (default: ``https`` only).
      - Hostname must be present, not in the banned alias list.
      - Resolved IP(s) must not fall into any banned range (see
        ``_BANNED_V4_NETWORKS`` / ``_BANNED_V6_NETWORKS``).

    Returns the original URL on success; raises ``UnsafeURLError`` otherwise.

    DNS resolution can be disabled via ``resolve_dns=False`` for fast-path
    checks (e.g. form validation) — but runtime fetch paths should always
    resolve, since a DNS record can flip between validation and the fetch.
    The caller should also pin the resolved IP into the request if paranoid.
    """
    if not raw_url or not isinstance(raw_url, str):
        raise UnsafeURLError("URL is empty")

    try:
        parsed = urlparse(raw_url)
    except Exception as e:
        raise UnsafeURLError(f"URL did not parse: {e}") from e

    if parsed.scheme.lower() not in allowed_schemes:
        raise UnsafeURLError(
            f"URL scheme {parsed.scheme!r} not in allow-list {allowed_schemes}"
        )

    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeURLError("URL has no hostname")

    if host in _BANNED_HOSTNAMES:
        raise UnsafeURLError(f"Hostname {host!r} is banned")

    # If the hostname is itself a literal IP, check it directly.
    # urlparse strips outer brackets on IPv6 literals, but ipaddress.ip_address
    # rejects any leftover brackets — normalize.
    maybe_ip = host.strip("[]")
    is_literal_ip = False
    try:
        ipaddress.ip_address(maybe_ip)
        is_literal_ip = True
    except ValueError:
        # not a literal IP — fall through to DNS resolution below
        pass

    if is_literal_ip:
        if _ip_is_banned(maybe_ip):
            raise UnsafeURLError(f"Literal IP {maybe_ip!r} is in a banned range")
        return raw_url

    if not resolve_dns:
        return raw_url

    try:
        # getaddrinfo returns every A/AAAA record. ALL of them must pass —
        # a DNS rebinder that returns both a public IP and 127.0.0.1 would
        # otherwise pass validation and then be redirected at fetch time.
        records = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"DNS resolution failed for {host!r}: {e}") from e

    seen: set[str] = set()
    for family, _typ, _proto, _canon, sockaddr in records:
        ip = sockaddr[0]
        if ip in seen:
            continue
        seen.add(ip)
        if _ip_is_banned(ip):
            raise UnsafeURLError(
                f"Host {host!r} resolved to banned IP {ip!r}"
            )

    return raw_url


def safe_outbound_url_or_fallback(
    raw_url: str | None,
    fallback_url: str,
    *,
    allowed_schemes: tuple[str, ...] = ("https",),
) -> str:
    """Convenience wrapper — use `raw_url` if safe, else log + fall back.

    Intended for tenant-supplied URLs where a silent fallback to the
    platform default is preferable to erroring the whole generation run.
    Logs the rejected URL so SREs can spot abuse patterns.
    """
    if not raw_url:
        return fallback_url
    try:
        return validate_outbound_url(raw_url, allowed_schemes=allowed_schemes)
    except UnsafeURLError as e:
        logger.warning(
            "[url_safety] rejecting tenant-supplied URL %r (fallback=%r): %s",
            raw_url, fallback_url, e,
        )
        return fallback_url
