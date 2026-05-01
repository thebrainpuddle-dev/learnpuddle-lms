"""
SSRF Guard — validates that an outbound URL is safe to call.

Protects against Server-Side Request Forgery by:
1. (Webhook variant only) Enforcing a hostname allowlist for chat webhooks.
2. Resolving the URL's hostname and rejecting RFC1918, loopback,
   link-local, and CGNAT addresses.
3. Pinning the resolved IP into a custom ``requests`` Transport Adapter
   so that a DNS rebind between validation and the actual HTTP call
   cannot swap the address.

Two flavors:

* :func:`safe_post` — outbound chat webhooks. Hostname must match the
  Slack / Teams allowlist *and* resolve to a public IP.
* :func:`safe_get` / :func:`validate_external_url` — admin-supplied
  fetches (e.g. chatbot knowledge URL ingestion). No host allowlist,
  but still rejects private IPs, disables redirects, and pins the IP.

Usage::

    from apps.integrations_chat.ssrf_guard import (
        validate_webhook_host,
        safe_post,
        safe_get,
        SSRFError,
    )

    validate_webhook_host(url)   # raises SSRFError on violation
    resp = safe_post(url, json=body, timeout=(5, 10))

    # Admin-supplied URL ingestion:
    resp = safe_get(url, headers={"User-Agent": "..."}, timeout=(5, 30))
"""

import ipaddress
import logging
import socket
import urllib.parse

import requests
from requests.adapters import HTTPAdapter
from urllib3 import PoolManager
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

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


def _build_pinned_pool_classes(pinned_ip: str):
    """
    Build a (HTTPConnectionPool, HTTPSConnectionPool) pair whose connections
    always dial *pinned_ip* instead of resolving DNS.

    Each call returns a fresh pair of subclasses, so two adapters with
    different pinned IPs never share connection classes. SNI / Host header /
    cert verification still use ``self.host`` (the original hostname), so
    TLS continues to validate against the certificate the user expects.

    Thread-safety:
    - Replaces the previous ``socket.getaddrinfo`` monkey-patch in
      ``_PinnedIPAdapter.send`` (which leaked across concurrent requests).
    - Each connection is constructed with the pinned IP captured in the
      class closure; no global mutable state, so concurrent calls on
      different threads cannot cross-contaminate.
    """

    class _PinnedHTTPConnection(HTTPConnection):
        def _new_conn(self):  # type: ignore[override]
            from urllib3.util import connection as _u3_conn
            return _u3_conn.create_connection(
                (pinned_ip, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )

    class _PinnedHTTPSConnection(HTTPSConnection):
        def _new_conn(self):  # type: ignore[override]
            from urllib3.util import connection as _u3_conn
            return _u3_conn.create_connection(
                (pinned_ip, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )

    class _PinnedHTTPConnectionPool(HTTPConnectionPool):
        ConnectionCls = _PinnedHTTPConnection

    class _PinnedHTTPSConnectionPool(HTTPSConnectionPool):
        ConnectionCls = _PinnedHTTPSConnection

    return _PinnedHTTPConnectionPool, _PinnedHTTPSConnectionPool


class PinnedIPAdapter(HTTPAdapter):
    """
    Transport adapter that prevents DNS rebinding by sending each request to
    a pre-validated IP address while preserving the original hostname in the
    ``Host`` header and TLS SNI.

    Implementation approach (urllib3 2.x):
    - Build per-instance ``HTTPConnection`` / ``HTTPSConnection`` subclasses
      whose ``_new_conn`` connects directly to the pinned IP.
    - Wire them into a dedicated ``PoolManager`` whose ``pool_classes_by_scheme``
      uses pools that instantiate those connection classes.
    - The connection's ``self.host`` remains the original hostname, so
      ``HTTPSConnection.connect()`` passes ``server_hostname=self.host`` to
      the TLS wrap and certificate verification succeeds against the real
      hostname.

    Thread-safety:
    - No module-level monkey-patching. The pinned IP is captured in the
      class closure, so concurrent requests on different threads cannot
      observe each other's pinned addresses.
    """

    def __init__(self, hostname: str, pinned_ip: str, **kwargs):
        self._hostname = hostname
        self._pinned_ip = pinned_ip
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        http_pool_cls, https_pool_cls = _build_pinned_pool_classes(self._pinned_ip)

        # ``pool_classes_by_scheme`` is an *instance* attribute on PoolManager
        # in urllib3 2.x (assigned in ``PoolManager.__init__`` from a
        # module-level dict).  Subclassing with a class-level override does
        # not work — the parent ``__init__`` would just clobber it.  Build a
        # vanilla PoolManager first, then replace its scheme-to-pool map
        # with our pinned subclasses.  This is the supported override path
        # (the attribute is documented and used at lookup time inside
        # ``connection_from_pool_key``).
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            **pool_kwargs,
        )
        self.poolmanager.pool_classes_by_scheme = {
            "http": http_pool_cls,
            "https": https_pool_cls,
        }


# Backwards-compat alias.  Historically this class was named with a leading
# underscore but is now consumed by callers outside this module
# (``apps/webhooks/services.py``).  Keep the old name resolvable so any
# stragglers / tests / type-stubs that import the underscored symbol do not
# break.  New callers should use ``PinnedIPAdapter`` or, preferably,
# :func:`build_pinned_session`.
_PinnedIPAdapter = PinnedIPAdapter


# ---------------------------------------------------------------------------
# Public session factory
# ---------------------------------------------------------------------------


def build_pinned_session(url: str) -> tuple[requests.Session, str, str]:
    """
    Validate *url* against the SSRF policy and return a ``requests.Session``
    whose HTTP/HTTPS adapter is pinned to the resolved IP.

    This is the public entry point for callers that need to mount the
    pinning adapter on a session they then drive themselves (for example,
    webhook delivery wants ``session.post(..., allow_redirects=False,
    verify=True)`` with custom error handling).  Prefer this factory over
    instantiating :class:`PinnedIPAdapter` directly so the validate → resolve
    → pin sequencing is performed in one place.

    Note that this factory does **not** apply the chat-webhook host
    allowlist (Slack / Teams).  Callers that need allowlist enforcement
    should use :func:`safe_post`, which adds
    :func:`validate_webhook_host` on top.

    Returns ``(session, hostname, pinned_ip)`` so callers can log or
    assert against the pinned IP if needed.

    :raises SSRFError: If the URL fails scheme / private-IP validation.
    """
    hostname, pinned_ip = validate_external_url(url)
    session = requests.Session()
    adapter = PinnedIPAdapter(hostname=hostname, pinned_ip=pinned_ip)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session, hostname, pinned_ip


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
    # Two-layer validation: chat-webhook allowlist first, then the generic
    # scheme + private-IP rejection performed inside ``build_pinned_session``.
    # The allowlist catches "wrong vendor" before we even resolve DNS, while
    # ``build_pinned_session`` defends against DNS rebind / literal-IP inputs.
    validate_webhook_host(url)
    session, _hostname, _pinned_ip = build_pinned_session(url)

    return session.post(
        url,
        json=json,
        data=data,
        headers=headers or {},
        timeout=timeout,
        allow_redirects=False,
        verify=True,  # enforce TLS cert validation
    )


# ---------------------------------------------------------------------------
# General-purpose external-URL safe GET (no host allowlist)
# ---------------------------------------------------------------------------


def validate_external_url(url: str) -> tuple[str, str]:
    """
    Validate that *url* is safe to fetch from an admin-supplied input.

    Unlike :func:`validate_webhook_host`, this does NOT enforce a host
    allowlist — admin-supplied content URLs can point to any external
    host.  It still enforces:

    1. Scheme is ``http`` or ``https`` (rejects ``file://``, ``gopher://``,
       ``ftp://``, etc.).
    2. Hostname is parseable.
    3. The hostname resolves and the resolved IP is **not**
       private / loopback / link-local / CGNAT (per
       :data:`_BLOCKED_NETWORKS`).  This blocks AWS IMDS pivots
       (``169.254.169.254``), localhost-only services like Redis
       (``127.0.0.1:6379``), and lateral movement into the VPC.

    Returns a tuple of ``(hostname, pinned_ip)`` for use with
    :class:`_PinnedIPAdapter`.

    Raises :class:`SSRFError` on any violation.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as exc:
        raise SSRFError(f"INVALID_URL: unparseable URL — {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise SSRFError(
            f"INVALID_URL: scheme must be http or https (got {scheme!r})"
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SSRFError("INVALID_URL: missing hostname")

    # If the user supplied a literal IP, validate it directly so we
    # don't trust DNS to "fix" a private-IP literal like
    # http://127.0.0.1:6379/.
    try:
        literal_addr = ipaddress.ip_address(hostname)
    except ValueError:
        literal_addr = None

    if literal_addr is not None:
        if _is_private_ip(str(literal_addr)):
            raise SSRFError(
                f"SSRF_BLOCKED: '{hostname}' is a private/loopback address"
            )
        return hostname, str(literal_addr)

    pinned_ip = _resolve_and_check(hostname)
    return hostname, pinned_ip


def safe_get(
    url: str,
    *,
    headers=None,
    timeout=(5, 30),
    max_bytes: int = 50 * 1024 * 1024,
) -> requests.Response:
    """
    Perform a GET to *url* with full SSRF protection — no host allowlist.

    Designed for admin-supplied external content fetches (e.g. chatbot
    knowledge ingestion).  Steps:

    1. Validate scheme and reject private-IP destinations
       (:func:`validate_external_url`).
    2. Pin the resolved IP into a custom adapter to defeat DNS rebind.
    3. GET with ``allow_redirects=False`` — redirects can lead to a
       different (private) host.  Callers that need redirect support
       must validate each hop themselves.
    4. Enforce a streaming size cap (default 50 MB) so an attacker can't
       exhaust memory by pointing us at an infinite stream.

    :param url: URL to GET.
    :param headers: Extra request headers.
    :param timeout: ``(connect_timeout, read_timeout)`` seconds.
    :param max_bytes: Reject responses larger than this many bytes.
    :raises SSRFError: On scheme/private-IP/redirect/size-cap violation.
    :raises requests.RequestException: On HTTP/network errors.
    """
    session, _hostname, _pinned_ip = build_pinned_session(url)

    response = session.get(
        url,
        headers=headers or {},
        timeout=timeout,
        allow_redirects=False,
        verify=True,
        stream=True,
    )

    # Reject 3xx — a redirect target can be a private host.
    if 300 <= response.status_code < 400:
        location = response.headers.get("Location", "<missing>")
        response.close()
        raise SSRFError(
            f"SSRF_REDIRECT_BLOCKED: '{url}' redirected to {location!r}; "
            "redirects are disabled for admin-supplied URL fetches"
        )

    # Stream the body but enforce the byte cap.
    chunks = []
    total = 0
    try:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise SSRFError(
                    f"SSRF_SIZE_CAP_EXCEEDED: '{url}' returned more than "
                    f"{max_bytes} bytes"
                )
            chunks.append(chunk)
    finally:
        response.close()

    # Re-attach the buffered body so callers can use ``.text`` / ``.content``.
    response._content = b"".join(chunks)
    response._content_consumed = True
    return response
