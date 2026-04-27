"""
Tests for the image_service per-provider circuit breaker (CG-P0-4).

Covers:
  1. A 429 response opens the breaker; subsequent calls skip the provider.
  2. After `cooling_until` elapses, the provider is tried again (half-open).
  3. `Retry-After: 60` header on a 429 sets cool-until to now+60s.
  4. A successful 200 clears failure count and cooldown (closed state).
  5. When ALL providers are cooling, `fetch_scene_image` returns the
     deterministic placeholder without any HTTP calls.

All external HTTP calls are mocked. Time is controlled by monkeypatching
`image_service._now` so tests don't need freezegun.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.courses import image_service


@pytest.fixture(autouse=True)
def _reset_circuit_state():
    """Make every test start from a clean breaker state — module-level dict
    persists across tests otherwise.
    """
    image_service.reset_circuit_breaker_state()
    yield
    image_service.reset_circuit_breaker_state()


@pytest.fixture
def fake_clock():
    """Returns a tuple (get, advance). Monkeypatch `image_service._now` to
    `get` in each test. `advance(seconds)` fast-forwards the clock.
    """
    current = [1_000_000.0]  # mutable box

    def get() -> float:
        return current[0]

    def advance(seconds: float) -> None:
        current[0] += seconds

    return get, advance


def _mock_resp(status_code: int, headers: dict | None = None, json_payload: dict | None = None, content: bytes | None = None):
    """Build a mocked requests.Response-ish object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    if json_payload is not None:
        resp.json = MagicMock(return_value=json_payload)
    if content is not None:
        resp.content = content
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 1. 429 → skip provider on next call
# ─────────────────────────────────────────────────────────────────────────────

def test_429_opens_breaker_skips_provider_next_call(fake_clock, monkeypatch):
    """First call returns 429 → second call for same provider skips it."""
    now, _ = fake_clock
    monkeypatch.setattr(image_service, "_now", now)

    # Configure API keys so Unsplash is selected.
    monkeypatch.setattr(image_service, "_get_api_key", lambda name: "fake-key" if name == "UNSPLASH_ACCESS_KEY" else "")

    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        # Unsplash is the only configured provider, then falls to pollinations
        if "unsplash" in url:
            call_count["n"] += 1
            return _mock_resp(429, headers={})
        # pollinations fallback returns bad content so we keep going to placeholder
        return _mock_resp(500)

    with patch.object(image_service.requests, "get", side_effect=fake_get):
        # First call — hits Unsplash, gets 429, opens breaker
        url1 = image_service.fetch_scene_image("photosynthesis")
        # Second call — Unsplash is cooling, must be skipped
        url2 = image_service.fetch_scene_image("photosynthesis")

    assert call_count["n"] == 1, (
        f"Unsplash should have been called exactly once (skipped on 2nd due to cooldown). Got {call_count['n']}."
    )
    # Both should have landed on the placeholder (pollinations also 500'd)
    assert url1.startswith("https://placehold.co/")
    assert url2.startswith("https://placehold.co/")


# ─────────────────────────────────────────────────────────────────────────────
# 2. After cooldown elapses, provider is retried
# ─────────────────────────────────────────────────────────────────────────────

def test_provider_retried_after_cooldown_elapses(fake_clock, monkeypatch):
    """After cool_until elapses, provider is tried again."""
    now, advance = fake_clock
    monkeypatch.setattr(image_service, "_now", now)
    monkeypatch.setattr(image_service, "_get_api_key", lambda name: "fake-key" if name == "UNSPLASH_ACCESS_KEY" else "")

    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        if "unsplash" in url:
            call_count["n"] += 1
            return _mock_resp(429)
        return _mock_resp(500)

    with patch.object(image_service.requests, "get", side_effect=fake_get):
        image_service.fetch_scene_image("photosynthesis")
        # First ladder rung is 30s. Jump past it.
        advance(31)
        image_service.fetch_scene_image("photosynthesis")

    assert call_count["n"] == 2, (
        f"Unsplash should have been retried after cooldown elapsed. Got {call_count['n']}."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Retry-After header honoured
# ─────────────────────────────────────────────────────────────────────────────

def test_retry_after_header_sets_exact_cooldown(fake_clock, monkeypatch):
    """Retry-After: 60 → cool_until ≈ now + 60."""
    now, advance = fake_clock
    monkeypatch.setattr(image_service, "_now", now)
    monkeypatch.setattr(image_service, "_get_api_key", lambda name: "fake-key" if name == "UNSPLASH_ACCESS_KEY" else "")

    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        if "unsplash" in url:
            call_count["n"] += 1
            return _mock_resp(429, headers={"Retry-After": "60"})
        return _mock_resp(500)

    with patch.object(image_service.requests, "get", side_effect=fake_get):
        image_service.fetch_scene_image("photosynthesis")
        # 59s later — still cooling (Retry-After=60 overrides the 30s ladder rung)
        advance(59)
        image_service.fetch_scene_image("photosynthesis")
        assert call_count["n"] == 1, (
            "Retry-After=60 should keep Unsplash cooling at t=59s. "
            f"Instead was retried; got {call_count['n']} calls."
        )
        # 2s more → past the 60s Retry-After window
        advance(2)
        image_service.fetch_scene_image("photosynthesis")

    assert call_count["n"] == 2, (
        f"Unsplash should have been retried at t=61s. Got {call_count['n']}."
    )


def test_retry_after_capped_at_15_minutes(monkeypatch):
    """Retry-After: 3600 (1hr) → capped at 900s (15min)."""
    image_service._mark_provider_failure("unsplash", retry_after=3600.0)
    state = image_service._CIRCUIT_STATE["unsplash"]
    cooldown_length = state["cooling_until"] - image_service._now()
    # Allow small timing jitter
    assert 899 <= cooldown_length <= 901, (
        f"Retry-After=3600 should be capped at 900s. Got {cooldown_length}s."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. 200 success resets failure state
# ─────────────────────────────────────────────────────────────────────────────

def test_200_success_clears_cooling_state(fake_clock, monkeypatch):
    """Successful 200 → cooling state cleared, failure count reset."""
    now, advance = fake_clock
    monkeypatch.setattr(image_service, "_now", now)
    monkeypatch.setattr(image_service, "_get_api_key", lambda name: "fake-key" if name == "UNSPLASH_ACCESS_KEY" else "")

    responses = [
        # First call: 429
        _mock_resp(429),
        # After cooldown elapses, provider is tried again — this time success
        _mock_resp(200, json_payload={"results": [{"urls": {"regular": "https://images.unsplash.com/photo-abc"}}]}),
    ]

    def fake_get(url, **kwargs):
        if "unsplash" in url:
            return responses.pop(0) if responses else _mock_resp(500)
        return _mock_resp(500)

    with patch.object(image_service.requests, "get", side_effect=fake_get):
        image_service.fetch_scene_image("photosynthesis")
        # Failure count should be 1 after the 429
        assert image_service._CIRCUIT_STATE["unsplash"]["failure_count"] == 1
        assert image_service._CIRCUIT_STATE["unsplash"]["cooling_until"] > now()

        advance(31)  # past 30s rung
        url = image_service.fetch_scene_image("photosynthesis")

    # After success, state is cleared
    assert url == "https://images.unsplash.com/photo-abc"
    assert image_service._CIRCUIT_STATE["unsplash"]["failure_count"] == 0
    assert image_service._CIRCUIT_STATE["unsplash"]["cooling_until"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. All providers cooling → placeholder, no HTTP calls
# ─────────────────────────────────────────────────────────────────────────────

def test_all_providers_cooling_returns_placeholder_without_http(fake_clock, monkeypatch):
    """Every provider in cooldown → returns placeholder, makes zero HTTP calls."""
    now, _ = fake_clock
    monkeypatch.setattr(image_service, "_now", now)

    # Configure all keys so all providers are "configured"
    def _all_keys(name):
        return "fake-key"

    monkeypatch.setattr(image_service, "_get_api_key", _all_keys)

    # Open the breaker for every provider
    for p in ("imagen", "nanobanana", "unsplash", "pexels", "pollinations"):
        image_service._mark_provider_failure(p)

    http_calls = {"n": 0}

    def spy_get(*args, **kwargs):
        http_calls["n"] += 1
        return _mock_resp(500)

    def spy_post(*args, **kwargs):
        http_calls["n"] += 1
        return _mock_resp(500)

    with patch.object(image_service.requests, "get", side_effect=spy_get), \
         patch.object(image_service.requests, "post", side_effect=spy_post):
        url = image_service.fetch_scene_image("quantum entanglement")

    assert url.startswith("https://placehold.co/"), f"Expected placeholder, got {url}"
    assert "quantum" in url, "Placeholder should encode the keyword"
    assert http_calls["n"] == 0, (
        f"No HTTP calls should be made when all providers cooling. Got {http_calls['n']}."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bonus: exponential ladder
# ─────────────────────────────────────────────────────────────────────────────

def test_cooldown_ladder_exponential(monkeypatch):
    """Successive failures use exponential ladder rungs: 30, 60, 120, 240, …"""
    fixed_now = [2_000_000.0]
    monkeypatch.setattr(image_service, "_now", lambda: fixed_now[0])

    expected = [30, 60, 120, 240, 480, 900, 900]  # capped at 900
    for i, want in enumerate(expected, start=1):
        image_service._mark_provider_failure("imagen")
        state = image_service._CIRCUIT_STATE["imagen"]
        got = state["cooling_until"] - fixed_now[0]
        assert got == pytest.approx(want, abs=0.01), (
            f"Failure #{i}: expected cooldown={want}s, got {got}s"
        )


def test_parse_retry_after_rejects_garbage():
    """Retry-After parser returns None on invalid values."""
    assert image_service._parse_retry_after("abc") is None
    assert image_service._parse_retry_after("") is None
    assert image_service._parse_retry_after(None) is None
    assert image_service._parse_retry_after("-5") is None
    assert image_service._parse_retry_after("30") == 30.0
    assert image_service._parse_retry_after("  60  ") == 60.0
