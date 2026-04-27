# tests/infra/test_docker_compose_prod.py
"""
Regression tests — Fix 4 & 5: docker-compose.prod.yml security configuration.

Fix 4: Redis password is REQUIRED (no weak default).
  docker-compose.prod.yml must use ${REDIS_PASSWORD:?...} syntax for both the
  --requirepass argument and the healthcheck ping command. This ensures that
  docker compose up fails immediately if REDIS_PASSWORD is not set in .env,
  rather than silently starting Redis with no authentication.

Fix 5: pg_isready uses the application user, not 'postgres'.
  The pg_isready healthcheck must use -U ${DB_USER:-learnpuddle} (not -U postgres).
  Using 'postgres' is wrong because it checks connectivity for a superuser role
  that may not exist in production, silently reporting healthy when the app user
  cannot connect.

These are file-level static analysis tests — they run without Django/DB.
They guard against configuration regressions in the compose file.
"""

import os
import re
import pytest


# ---------------------------------------------------------------------------
# Locate docker-compose.prod.yml relative to this test file
# tests/infra/ → backend/ → LMS/ → docker-compose.prod.yml
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
_COMPOSE_FILE = os.path.join(_REPO_ROOT, "docker-compose.prod.yml")


@pytest.fixture(scope="module")
def compose_text():
    """Read docker-compose.prod.yml once for all tests in this module."""
    assert os.path.exists(_COMPOSE_FILE), (
        f"docker-compose.prod.yml not found at {_COMPOSE_FILE}. "
        "Adjust _REPO_ROOT if the file has moved."
    )
    with open(_COMPOSE_FILE, "r") as fh:
        return fh.read()


# ===========================================================================
# Fix 4 — Redis password: required, no weak default
# ===========================================================================

class TestRedisPasswordRequired:
    """docker-compose.prod.yml must enforce REDIS_PASSWORD with no weak default."""

    def test_redis_requirepass_uses_required_syntax(self, compose_text):
        """
        --requirepass must use ${REDIS_PASSWORD:?...} syntax.
        The :? operator makes docker compose abort if the variable is unset or empty.
        """
        assert "${REDIS_PASSWORD:?" in compose_text, (
            "Redis --requirepass must use ${REDIS_PASSWORD:?...} required-variable syntax. "
            "Found neither '${REDIS_PASSWORD:?' in docker-compose.prod.yml. "
            "This means Redis may start without authentication if .env is misconfigured."
        )

    def test_redis_healthcheck_uses_required_syntax(self, compose_text):
        """
        The Redis healthcheck (redis-cli ping) must also use ${REDIS_PASSWORD:?...}.
        A healthcheck that doesn't pass -a ${REDIS_PASSWORD} would falsely report
        healthy for an unauthenticated connection while the real service requires auth.
        """
        # Count occurrences — we need at least 2: requirepass + healthcheck
        count = compose_text.count("${REDIS_PASSWORD:?")
        assert count >= 2, (
            f"Expected at least 2 uses of '${{REDIS_PASSWORD:?...' in docker-compose.prod.yml "
            f"(--requirepass and healthcheck), found {count}. "
            "The healthcheck must also use the required-variable syntax."
        )

    def test_no_weak_redis_password_default(self, compose_text):
        """
        Reject patterns like ${REDIS_PASSWORD:-learnpuddle} or ${REDIS_PASSWORD:-password}.
        The :- operator silently falls back to the default if REDIS_PASSWORD is unset,
        defeating the fail-fast protection.

        Weak defaults that are explicitly rejected:
          ${REDIS_PASSWORD:-learnpuddle}
          ${REDIS_PASSWORD:-password}
          ${REDIS_PASSWORD:-redis}
          ${REDIS_PASSWORD:-changeme}
          ${REDIS_PASSWORD:-}     (empty string default — same as no auth)
        """
        weak_pattern = re.compile(r'\$\{REDIS_PASSWORD:-')
        match = weak_pattern.search(compose_text)
        assert match is None, (
            "Weak REDIS_PASSWORD default detected in docker-compose.prod.yml. "
            "Use '${REDIS_PASSWORD:?Set REDIS_PASSWORD in .env}' instead of "
            "'${REDIS_PASSWORD:-<default>}'. A weak default silently starts Redis "
            "with a guessable password if .env is missing."
        )

    def test_redis_requirepass_line_present(self, compose_text):
        """The redis-server command must include --requirepass."""
        assert "--requirepass" in compose_text, (
            "--requirepass not found in docker-compose.prod.yml. "
            "Redis is starting without password authentication."
        )

    def test_redis_healthcheck_uses_dash_a_flag(self, compose_text):
        """redis-cli in healthcheck must use -a to pass the password."""
        assert "redis-cli" in compose_text, "redis-cli not found in compose file"
        # Find the healthcheck block and verify -a appears near redis-cli
        assert 'redis-cli", "-a"' in compose_text or '"redis-cli", "-a"' in compose_text or (
            'redis-cli -a' in compose_text
        ), (
            "Redis healthcheck must pass -a <password> to redis-cli. "
            "Without -a, the healthcheck connects unauthenticated and may report "
            "healthy even if real clients are being rejected."
        )


# ===========================================================================
# Fix 5 — pg_isready uses the application user, not postgres
# ===========================================================================

class TestPgIsReadyUser:
    """pg_isready healthcheck must use the application DB user, not 'postgres'."""

    def test_pg_isready_uses_db_user_variable(self, compose_text):
        """
        pg_isready must reference DB_USER, not hardcode 'postgres'.
        Using 'postgres' checks connectivity for the superuser, not the app user.
        The app user may lack login privileges and the healthcheck would lie.
        """
        assert "pg_isready" in compose_text, (
            "pg_isready not found in docker-compose.prod.yml — "
            "the DB healthcheck may be missing or misconfigured."
        )
        assert "${DB_USER" in compose_text, (
            "pg_isready in docker-compose.prod.yml must reference ${DB_USER...}, "
            "not hardcode '-U postgres'. Using the superuser masks connection "
            "failures for the application user."
        )

    def test_pg_isready_does_not_hardcode_postgres_user(self, compose_text):
        """
        The -U flag in pg_isready must not be '-U postgres' (the superuser).
        Allowed forms: -U ${DB_USER:-learnpuddle} or -U ${DB_USER:?...}
        """
        # Match '-U postgres' only as a complete argument (not as part of a variable name)
        # e.g. '-U postgres' or '"-U", "postgres"'
        hardcoded_pattern = re.compile(r'-U\s+postgres\b')
        match = hardcoded_pattern.search(compose_text)
        assert match is None, (
            "pg_isready uses '-U postgres' (superuser) instead of '-U ${DB_USER:-learnpuddle}'. "
            "This causes false-healthy healthchecks when the app user cannot connect."
        )

    def test_pg_isready_uses_learnpuddle_default_user(self, compose_text):
        """
        The pg_isready line (or test: array element) must:
          1. Contain a ${DB_USER reference (not hardcode -U postgres).
          2. NOT contain '-U postgres ' or '-U postgres"' (hardcoded superuser).
          3. Contain a ${DB_NAME reference so the healthcheck targets the right DB.

        This test parses line-by-line and ties each assertion directly to the
        pg_isready line, preventing a loose file-wide match from hiding a broken
        healthcheck that references DB_USER somewhere unrelated.
        """
        lines = compose_text.splitlines()

        # Find the line(s) that contain pg_isready
        pg_isready_lines = [line for line in lines if "pg_isready" in line]
        assert pg_isready_lines, (
            "No line containing 'pg_isready' found in docker-compose.prod.yml. "
            "The DB healthcheck may be missing or misconfigured."
        )

        # Use the first pg_isready line for assertion (typically the test: entry)
        pg_line = pg_isready_lines[0]

        # 1. Must reference DB_USER on the same line as pg_isready
        assert "${DB_USER" in pg_line, (
            f"pg_isready line does not reference ${{DB_USER...}}.\n"
            f"Line: {pg_line!r}\n"
            "pg_isready must use '-U ${{DB_USER:-learnpuddle}}' (not '-U postgres') "
            "so the healthcheck tests connectivity for the application user."
        )

        # 2. Must NOT hardcode '-U postgres' on the pg_isready line
        assert not re.search(r'-U\s+postgres\b', pg_line), (
            f"pg_isready line hardcodes '-U postgres' (superuser) instead of "
            f"'-U ${{DB_USER:-learnpuddle}}'.\nLine: {pg_line!r}\n"
            "This causes false-healthy checks when the application user cannot connect."
        )

        # 3. Must reference DB_NAME on the same line (confirms full healthcheck target)
        assert "${DB_NAME" in pg_line, (
            f"pg_isready line does not reference ${{DB_NAME...}}.\n"
            f"Line: {pg_line!r}\n"
            "The healthcheck must specify the target database via '-d ${{DB_NAME:-learnpuddle_db}}'."
        )

    def test_db_service_has_healthcheck(self, compose_text):
        """
        The db service must declare a healthcheck (absence would hide connection
        problems from services that depend on db with condition: service_healthy).
        """
        assert "pg_isready" in compose_text, (
            "No pg_isready healthcheck found in docker-compose.prod.yml. "
            "Dependent services (web, worker) with 'condition: service_healthy' "
            "will never start if the db service has no healthcheck."
        )
