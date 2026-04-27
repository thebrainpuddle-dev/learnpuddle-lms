"""
SSRF Guard — validates that a webhook URL is safe to call.

Protects against Server-Side Request Forgery by:
1. Enforcing a hostname allowlist (only known Slack / Teams hostnames).
2. Resolving the URL's hostname and rejecting RFC1918, loopback,
   link-local, and CGNAT addresses.
3. Pinning the resolved IP into a custom ``requests`` Transport Adapter
   so that a DNS rebind between validation and the actual HTTP call
   cannot swap the address.

Usage::

    from apps.integrations_chat.ssrf_guard import (
        validate_webhook_host,
        safe_post,
        SSRFError,
    )

    validate_webhook_host(url)   # raises SSRFError on violation
    resp = safe_post(url, json=body, timeout=(5, 10))
"""

import ipaddress
import logging
import socket
import urllib.parse

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public error type
# ---------------------------------------------------------------------------


class SSRFError(ValueError):
    """Raised when an outbound URL fails SSRF validation."""


# ---------------------------------------------------------------------------
# Allowlisted hostnames
# ---------------------------------------------------------------------------

_ALLOWED_HOSTS_EXACT = frozenset(["hooks.slack.com"])
_ALLOWED_HOSTS_SUFFIX = (".webhook.office.com",)  # wildcard suffix match


def _is_allowed_host(hostname: str) -> bool:
    """Return True if *hostname* is in the webhook allowlist."""
    hostname = hostname.lower().strip()
    if hostname in _ALLOWED_HOSTS_EXACT:
        return True
    for suffix in _ALLOWED_HOSTS_SUFFIX:
        if hostname.endswith(suffix):
            return True
    return False


def validate_webhook_host(url: str) -> None:
    """
    Raise :class:`SSRFError` with code ``INVALID_WEBHOOK_HOST`` if *url*'s
    hostname does not match the Slack / Teams allowlist.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as exc:
        raise SSRFError(f"INVALID_WEBHOOK_HOST: unparseable URL — {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("https", "http"):
        raise SSRFError("INVALID_WEBHOOK_HOST: scheme must be http or https")

    hostname = parsed.hostname or ""
    if not _is_allowed_host(hostname):
        raise SSRFError(
            f"INVALID_WEBHOOK_HOST: '{hostname}' is not an allowed webhook host. "
            "Allowed: hooks.slack.com, *.webhook.office.com"
        )


# ---------------------------------------------------------------------------
# Private IP rejection
# ---------------------------------------------------------------------------

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),        # RFC1918
    ipaddress.ip_network("172.16.0.0/12"),      # RFC1918
    ipaddress.ip_network("192.168.0.0/16"),     # RFC1918
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local (APIPA, AWS IMDS)
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
    ipaddress.ip_network("100.64.0.0/10"),      # CGNAT (RFC6598)
    ipaddress.ip_network("0.0.0.0/8"),          # "This" network
    ipaddress.ip_network("fc00::/7"),           # IPv6 ULA
]


def _is_private_ip(addr_str: str) -> bool:
    """Return True if *addr_str* resolves to a non-routable / internal address."""
    try:
        addr = ipaddress.ip_address(addr_str)
    except ValueError:
        return False
    for network in _BLOCKED_NETWORKS:
        if addr in network:
            return True
    return False


def _resolve_and_check(hostname: str) -> str:
    """
    Resolve *hostname* to an IP address string and verify it is not private.
    Returns the resolved IP string for use in connection pinning.
    Raises :class:`SSRFError` on resolution failure or private IP.
    """
    try:
        # getaddrinfo returns a list of 5-tuples; use the first result.
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFError(f"SSRF_DNS_FAILURE: cannot resolve '{hostname}' — {exc}") from exc

    if not results:
        raise SSRFError(f"SSRF_DNS_FAILURE: no DNS records for '{hostname}'")

    # Check all resolved addresses; reject if any are private.
    for _family, _type, _proto, _canonname, sockaddr in results:
        ip = sockaddr[0]
        if _is_private_ip(ip):
            raise SSRFError(
                f"SSRF_BLOCKED: '{hostname}' resolves to private/loopback address {ip!r}"
            )

    # Return the first resolved IP for pinning.
    return results[0][4][0]


# ---------------------------------------------------------------------------
# IP-pinning adapter
# ---------------------------------------------------------------------------


class _PinnedIPAdapter(HTTPAdapter):
    """
    Transport adapter that prevents DNS rebinding by using a per-connection
    socket that connects directly to the pre-validated IP address while
    preserving the original hostname in the ``Host`` header and TLS SNI.

    Implementation approach:
    - Subclass HTTPAdapter and override ``send``.
    - Monkey-patch ``socket.getaddrinfo`` within the call lifetime to always
      return the pinned IP for the target hostname, ensuring urllib3 does not
      re-resolve DNS.  This is the cleanest approach that is compatible with
      all urllib3 / requests versions and preserves TLS SNI correctly.
    """

    def __init__(self, hostname: str, pinned_ip: str, **kwargs):
        self._hostname = hostname
        self._pinned_ip = pinned_ip
        super().__init__(**kwargs)

    def send(self, request, **kwargs):
        import socket as _socket

        original_getaddrinfo = _socket.getaddrinfo
        pinned_ip = self._pinned_ip
        target_hostname = self._hostname

        def patched_getaddrinfo(host, port, *args, **kw):
            if host == target_hostname:
                # Return synthetic result pointing to the pinned IP.
                family = _socket.AF_INET6 if ":" in pinned_ip else _socket.AF_INET
                return [(family, _socket.SOCK_STREAM, 0, "", (pinned_ip, port or 0))]
            return original_getaddrinfo(host, port, *args, **kw)

        _socket.getaddrinfo = patched_getaddrinfo
        try:
            return super().send(request, **kwargs)
        finally:
            _socket.getaddrinfo = original_getaddrinfo


# ---------------------------------------------------------------------------
# Public safe-post helper
# ---------------------------------------------------------------------------


def safe_post(url: str, *, json=None, data=None, headers=None, timeout=(5, 10)) -> requests.Response:
    """
    Perform a POST to *url* with full SSRF protection.

    Steps:
    1. Enforce hostname allowlist via :func:`validate_webhook_host`.
    2. Resolve DNS and reject private IPs.
    3. Pin the resolved IP into a custom adapter to prevent DNS rebind.
    4. POST with ``allow_redirects=False``.

    :param url: Webhook URL to POST to.
    :param json: JSON body (passed to requests).
    :param data: Raw body (passed to requests).
    :param headers: Extra headers dict.
    :param timeout: (connect_timeout, read_timeout) seconds.
    :raises SSRFError: On allowlist or IP validation failure.
    :raises requests.RequestException: On HTTP/network errors.
    """
    validate_webhook_host(url)

    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or ""
    pinned_ip = _resolve_and_check(hostname)

    session = requests.Session()
    adapter = _PinnedIPAdapter(hostname=hostname, pinned_ip=pinned_ip)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session.post(
        url,
        json=json,
        data=data,
        headers=headers or {},
        timeout=timeout,
        allow_redirects=False,
        verify=True,  # enforce TLS cert validation
    )
