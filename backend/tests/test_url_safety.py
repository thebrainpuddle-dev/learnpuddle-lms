"""Tests for utils.url_safety SSRF validator.

Covers SEC-P0-3 from the 2026-04-23 ultrareview: tenant-editable
`llm_base_url` must not allow attacks on AWS IMDS, localhost services,
or RFC1918 hosts.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from utils.url_safety import (
    UnsafeURLError,
    safe_outbound_url_or_fallback,
    validate_outbound_url,
)


# ── Happy path ──────────────────────────────────────────────────────────────

def test_public_https_url_accepted():
    # Literal public IP — bypass DNS, directly validated.
    url = validate_outbound_url("https://1.1.1.1/chat", resolve_dns=False)
    assert url == "https://1.1.1.1/chat"


def test_known_provider_hostname_accepted(monkeypatch):
    # Fake DNS so we don't depend on network. Cloudflare DNS resolver IP.
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("1.1.1.1", 0))],
    )
    url = validate_outbound_url("https://api.openai.com/v1/chat/completions")
    assert url.startswith("https://api.openai.com")


# ── Scheme rejection ────────────────────────────────────────────────────────

def test_http_scheme_rejected_by_default():
    with pytest.raises(UnsafeURLError, match="scheme"):
        validate_outbound_url("http://api.openai.com/", resolve_dns=False)


def test_file_scheme_rejected():
    with pytest.raises(UnsafeURLError):
        validate_outbound_url("file:///etc/passwd", resolve_dns=False)


def test_gopher_scheme_rejected():
    with pytest.raises(UnsafeURLError):
        validate_outbound_url("gopher://evil.example/", resolve_dns=False)


# ── Literal-IP SSRF attacks ─────────────────────────────────────────────────

@pytest.mark.parametrize("banned_ip", [
    "127.0.0.1",           # loopback
    "169.254.169.254",     # AWS / GCP IMDS
    "10.0.0.5",            # RFC1918
    "172.16.0.1",          # RFC1918
    "192.168.1.1",         # RFC1918
    "100.64.0.1",          # CG-NAT
    "0.0.0.0",             # "this"
    "224.0.0.1",           # multicast
    "255.255.255.255",     # broadcast
])
def test_literal_banned_ipv4_rejected(banned_ip):
    with pytest.raises(UnsafeURLError, match="banned"):
        validate_outbound_url(f"https://{banned_ip}/chat", resolve_dns=False)


@pytest.mark.parametrize("banned_ip", [
    "[::1]",               # ipv6 loopback
    "[fe80::1]",           # link-local
    "[fc00::1]",           # unique-local
])
def test_literal_banned_ipv6_rejected(banned_ip):
    with pytest.raises(UnsafeURLError, match="banned"):
        validate_outbound_url(f"https://{banned_ip}/chat", resolve_dns=False)


# ── Hostname aliases ───────────────────────────────────────────────────────

@pytest.mark.parametrize("banned_host", [
    "localhost",
    "metadata.google.internal",
])
def test_banned_hostname_aliases(banned_host):
    with pytest.raises(UnsafeURLError, match="banned"):
        validate_outbound_url(f"https://{banned_host}/", resolve_dns=False)


# ── DNS rebinding / hostname resolves to private IP ────────────────────────

def test_hostname_resolving_to_loopback_rejected(monkeypatch):
    # Attacker-controlled DNS record: points to 127.0.0.1
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))],
    )
    with pytest.raises(UnsafeURLError, match="banned IP"):
        validate_outbound_url("https://attacker.example/chat")


def test_hostname_resolving_to_imds_rejected(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("169.254.169.254", 0))],
    )
    with pytest.raises(UnsafeURLError, match="banned IP"):
        validate_outbound_url("https://imds-proxy.example/chat")


def test_hostname_with_mixed_safe_and_unsafe_ips_rejected(monkeypatch):
    # DNS rebinding protection: ALL records must be safe. If any record
    # is in a banned range, we reject.
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *a, **k: [
            (2, 1, 6, "", ("1.1.1.1", 0)),          # safe
            (2, 1, 6, "", ("127.0.0.1", 0)),        # rebinding payload
        ],
    )
    with pytest.raises(UnsafeURLError, match="banned IP"):
        validate_outbound_url("https://dns-rebinder.example/chat")


def test_dns_failure_rejected(monkeypatch):
    import socket
    def _fail(*a, **k):
        raise socket.gaierror("no such host")
    monkeypatch.setattr("socket.getaddrinfo", _fail)
    with pytest.raises(UnsafeURLError, match="DNS"):
        validate_outbound_url("https://no-such-host.example/")


# ── Parse failures / empty input ───────────────────────────────────────────

def test_empty_url_rejected():
    with pytest.raises(UnsafeURLError, match="empty"):
        validate_outbound_url("")


def test_no_hostname_rejected():
    with pytest.raises(UnsafeURLError, match="hostname"):
        validate_outbound_url("https:///only-path", resolve_dns=False)


# ── Fallback wrapper ───────────────────────────────────────────────────────

def test_fallback_used_when_url_empty():
    assert (
        safe_outbound_url_or_fallback("", "https://api.openai.com/v1")
        == "https://api.openai.com/v1"
    )


def test_fallback_used_when_url_unsafe():
    # http scheme → rejected → fallback
    assert (
        safe_outbound_url_or_fallback(
            "http://169.254.169.254/",
            "https://api.openai.com/v1",
        )
        == "https://api.openai.com/v1"
    )


def test_fallback_not_used_when_url_safe():
    # Literal 1.1.1.1 is NOT banned
    result = safe_outbound_url_or_fallback(
        "https://1.1.1.1/chat",
        "https://api.openai.com/v1",
    )
    assert result == "https://1.1.1.1/chat"
