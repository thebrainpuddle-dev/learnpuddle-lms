"""Typed exceptions for the MAIC v2 stack.

Hierarchy:
    MaicError
    ├── MaicConfigError       — bad/missing settings or model registry entry
    ├── MaicGraphError        — orchestration graph runtime failure
    │   └── MaicProtocolError — node emitted an event that violates the
    │                           StatelessEvent wire format
    ├── MaicProviderError     — TTS / LLM provider failure (network, auth, quota)
    └── MaicTenantError       — tenant boundary violation (e.g. cross-tenant read)

Catching `MaicError` is the single broad-net for app-internal failures
that should be surfaced to the WS client as an `error` frame; never
catch `MaicError` and silently continue.
"""
from __future__ import annotations


class MaicError(Exception):
    """Base for all MAIC v2 exceptions."""


class MaicConfigError(MaicError):
    """Settings/registry/env misconfiguration that blocks startup or a request."""


class MaicGraphError(MaicError):
    """Orchestration graph runtime failure — wraps the underlying cause."""


class MaicProtocolError(MaicGraphError):
    """A node emitted an event that does not conform to StatelessEvent shape."""


class MaicProviderError(MaicError):
    """TTS / LLM / image provider call failed (network, auth, quota, etc.)."""


class MaicTenantError(MaicError):
    """Cross-tenant access attempt — must always reject + audit-log."""
