# tests/infra/test_nginx_dockerfile.py
"""
Regression tests — Fix 6: Nginx runs as non-root (USER nginx directive).

Before this fix the nginx Dockerfile did not include a USER directive,
meaning the nginx worker process ran as root. Running containers as root
gives an attacker who achieves code execution full container privileges,
defeating the principle of least privilege.

After the fix, the Dockerfile contains:
    USER nginx

These tests verify:
1. A USER directive exists in the Dockerfile (not missing).
2. The user is 'nginx', not 'root'.
3. The USER directive appears AFTER the chown/setup steps (correct order).
4. The USER directive appears BEFORE the EXPOSE/CMD directives.
5. The Dockerfile does not switch back to root after setting USER nginx.
"""

import os
import re
import pytest


# ---------------------------------------------------------------------------
# Locate nginx/Dockerfile relative to this test file
# tests/infra/ → backend/ → LMS/ → nginx/Dockerfile
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
_NGINX_DOCKERFILE = os.path.join(_REPO_ROOT, "nginx", "Dockerfile")


@pytest.fixture(scope="module")
def dockerfile_lines():
    """Read nginx/Dockerfile once and return its lines."""
    assert os.path.exists(_NGINX_DOCKERFILE), (
        f"nginx/Dockerfile not found at {_NGINX_DOCKERFILE}. "
        "Adjust _REPO_ROOT if the file has moved."
    )
    with open(_NGINX_DOCKERFILE, "r") as fh:
        return fh.readlines()


@pytest.fixture(scope="module")
def dockerfile_text(dockerfile_lines):
    return "".join(dockerfile_lines)


# ===========================================================================
# 1. USER directive presence and value
# ===========================================================================

class TestNginxDockerfileUserDirective:
    """nginx/Dockerfile must include 'USER nginx' to run as non-root."""

    def test_user_directive_exists(self, dockerfile_text):
        """
        'USER' must appear somewhere in the Dockerfile.
        Absence means the container runs as root (the Docker default).
        """
        user_pattern = re.compile(r'^\s*USER\b', re.MULTILINE)
        assert user_pattern.search(dockerfile_text), (
            "nginx/Dockerfile has no USER directive. "
            "The container runs as root, violating least-privilege. "
            "Add 'USER nginx' after the chown/setup steps."
        )

    def test_user_is_nginx_not_root(self, dockerfile_text):
        """
        The USER directive must specify 'nginx', not 'root'.
        Some Dockerfiles accidentally set USER root to perform setup steps
        and fail to switch back.
        """
        # Find all USER lines
        user_lines = re.findall(r'^\s*USER\s+(\S+)', dockerfile_text, re.MULTILINE)
        assert user_lines, "No USER directive found in nginx/Dockerfile"

        # The LAST USER directive wins at runtime
        final_user = user_lines[-1].lower()
        assert final_user == "nginx", (
            f"Final USER in nginx/Dockerfile is '{user_lines[-1]}', expected 'nginx'. "
            "The container will run as the wrong user."
        )

    def test_user_directive_is_not_root(self, dockerfile_text):
        """
        Explicit guard: 'USER root' must not be the last USER directive.
        This catches the pattern of switching to root for setup and forgetting
        to switch back.
        """
        user_lines = re.findall(r'^\s*USER\s+(\S+)', dockerfile_text, re.MULTILINE)
        if not user_lines:
            pytest.fail("No USER directive found in nginx/Dockerfile")

        final_user = user_lines[-1].lower()
        assert final_user != "root", (
            "nginx/Dockerfile ends with 'USER root'. "
            "The container will run as root, violating least-privilege. "
            "Add 'USER nginx' as the final USER directive."
        )


# ===========================================================================
# 2. Directive ordering
# ===========================================================================

class TestNginxDockerfileOrdering:
    """
    The USER nginx directive must appear in the correct place in the
    Dockerfile (after setup/chown, before EXPOSE/CMD).
    """

    def _line_index(self, lines, pattern):
        """Return the index of the last line matching the pattern, or -1."""
        pat = re.compile(pattern)
        result = -1
        for i, line in enumerate(lines):
            if pat.search(line):
                result = i
        return result

    def _first_line_index(self, lines, pattern):
        """Return the index of the first line matching the pattern, or -1."""
        pat = re.compile(pattern)
        for i, line in enumerate(lines):
            if pat.search(line):
                return i
        return -1

    def test_user_nginx_appears_before_expose(self, dockerfile_lines):
        """
        USER nginx must appear before EXPOSE so the port is declared
        in the context of the non-root user.
        """
        user_idx = self._line_index(dockerfile_lines, r'^\s*USER\s+nginx')
        expose_idx = self._first_line_index(dockerfile_lines, r'^\s*EXPOSE\b')

        if expose_idx == -1:
            # If there's no EXPOSE, the ordering constraint doesn't apply
            return

        assert user_idx != -1, "No 'USER nginx' directive in nginx/Dockerfile"
        assert user_idx < expose_idx, (
            f"'USER nginx' (line {user_idx + 1}) must appear before 'EXPOSE' "
            f"(line {expose_idx + 1}) in nginx/Dockerfile."
        )

    def test_user_nginx_appears_before_cmd(self, dockerfile_lines):
        """
        USER nginx must appear before CMD so the process starts as nginx user.
        """
        user_idx = self._line_index(dockerfile_lines, r'^\s*USER\s+nginx')
        cmd_idx = self._first_line_index(dockerfile_lines, r'^\s*CMD\b')

        if cmd_idx == -1:
            return  # No CMD, skip ordering check

        assert user_idx != -1, "No 'USER nginx' directive in nginx/Dockerfile"
        assert user_idx < cmd_idx, (
            f"'USER nginx' (line {user_idx + 1}) must appear before 'CMD' "
            f"(line {cmd_idx + 1}) in nginx/Dockerfile. "
            "Process will run as root if USER comes after CMD."
        )

    def test_chown_step_exists_before_user_nginx(self, dockerfile_lines):
        """
        chown steps must exist before USER nginx (ownership set while still root).
        This is the correct pattern:
            RUN chown -R nginx:nginx ...
            USER nginx
        """
        chown_idx = self._line_index(dockerfile_lines, r'chown.*nginx')
        user_idx = self._first_line_index(dockerfile_lines, r'^\s*USER\s+nginx')

        if chown_idx == -1:
            # No chown found — this is suspicious but not the direct concern of this test
            return

        assert user_idx != -1, "No 'USER nginx' directive found"
        assert chown_idx < user_idx, (
            f"chown step (line {chown_idx + 1}) must precede 'USER nginx' "
            f"(line {user_idx + 1}). "
            "chown must run as root before we drop privileges."
        )


# ===========================================================================
# 3. No root re-escalation after USER nginx
# ===========================================================================

class TestNginxNoRootEscalation:
    """After 'USER nginx' the Dockerfile must not switch back to root."""

    def test_no_user_root_after_user_nginx(self, dockerfile_lines):
        """
        'USER root' must not appear after 'USER nginx'.
        Re-escalating to root after dropping privileges defeats the fix.
        """
        user_nginx_idx = -1
        for i, line in enumerate(dockerfile_lines):
            if re.match(r'^\s*USER\s+nginx', line):
                user_nginx_idx = i
                break

        if user_nginx_idx == -1:
            pytest.fail("'USER nginx' not found in nginx/Dockerfile")

        subsequent_lines = dockerfile_lines[user_nginx_idx + 1:]
        for i, line in enumerate(subsequent_lines, start=user_nginx_idx + 2):
            if re.match(r'^\s*USER\s+root', line, re.IGNORECASE):
                pytest.fail(
                    f"'USER root' found at line {i} after 'USER nginx' "
                    f"(line {user_nginx_idx + 1}). "
                    "This re-escalates to root and defeats the non-root fix."
                )
