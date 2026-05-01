# tests/test_safe_get_ssrf.py
"""
SSRF Protection Tests for `safe_get` — used by chatbot URL ingestion.

Unlike the webhook variant (`safe_post` / `validate_webhook_host`) which
enforces a fixed Slack/Teams allowlist, `safe_get` accepts any external
host but must still:

1. Reject non-http(s) schemes (file://, gopher://, ftp://).
2. Reject literal private/loopback/link-local IPs (e.g. 127.0.0.1,
   169.254.169.254 cloud metadata).
3. Reject hostnames that resolve to private IPs (DNS-pivot).
4. Refuse to follow 3xx redirects (a redirect target may be private).
5. Cap the response size so an attacker cannot exhaust memory.

These tests pin the public-facing contract that `apps/courses/chatbot_tasks.
_extract_text_from_url` relies on — regression coverage for the proactive
audit fix BE-SEC-CHATBOT-URL-SSRF (2026-04-27).
"""

from unittest import mock

from django.test import SimpleTestCase

from apps.integrations_chat.ssrf_guard import (
    SSRFError,
    safe_get,
    validate_external_url,
)


class ValidateExternalUrlTestCase(SimpleTestCase):
    """Pure-Python validation of admin-supplied URLs."""

    # -- Scheme rejection ---------------------------------------------------

    def test_file_scheme_rejected(self):
        with self.assertRaises(SSRFError) as ctx:
            validate_external_url("file:///etc/passwd")
        self.assertIn("scheme", str(ctx.exception).lower())

    def test_gopher_scheme_rejected(self):
        with self.assertRaises(SSRFError):
            validate_external_url("gopher://internal.lan:6379/_FLUSHALL")

    def test_ftp_scheme_rejected(self):
        with self.assertRaises(SSRFError):
            validate_external_url("ftp://example.com/data")

    def test_javascript_scheme_rejected(self):
        with self.assertRaises(SSRFError):
            validate_external_url("javascript:alert(1)")

    def test_empty_scheme_rejected(self):
        with self.assertRaises(SSRFError):
            validate_external_url("//example.com/no-scheme")

    # -- Literal private-IP rejection (skip DNS) ----------------------------

    def test_literal_localhost_v4_rejected(self):
        with self.assertRaises(SSRFError) as ctx:
            validate_external_url("http://127.0.0.1:6379/")
        self.assertIn("private", str(ctx.exception).lower())

    def test_literal_localhost_v6_rejected(self):
        with self.assertRaises(SSRFError):
            validate_external_url("http://[::1]/")

    def test_literal_aws_imds_rejected(self):
        """AWS IMDS — the canonical SSRF target on EC2/ECS."""
        with self.assertRaises(SSRFError):
            validate_external_url(
                "http://169.254.169.254/latest/meta-data/"
                "iam/security-credentials/"
            )

    def test_literal_rfc1918_10_rejected(self):
        with self.assertRaises(SSRFError):
            validate_external_url("http://10.0.0.5/")

    def test_literal_rfc1918_172_rejected(self):
        with self.assertRaises(SSRFError):
            validate_external_url("http://172.16.0.1/")

    def test_literal_rfc1918_192_rejected(self):
        with self.assertRaises(SSRFError):
            validate_external_url("http://192.168.1.1/")

    def test_literal_cgnat_rejected(self):
        with self.assertRaises(SSRFError):
            validate_external_url("http://100.64.0.1/")

    # -- Hostname resolving to private IP -----------------------------------

    def test_hostname_resolving_to_private_rejected(self):
        """Even a public-looking hostname is rejected if DNS returns a
        private IP (DNS-pivot defense)."""
        with mock.patch(
            "apps.integrations_chat.ssrf_guard.socket.getaddrinfo"
        ) as mock_dns:
            import socket as _socket
            mock_dns.return_value = [
                (
                    _socket.AF_INET, _socket.SOCK_STREAM, 0, "",
                    ("127.0.0.1", 0),
                ),
            ]
            with self.assertRaises(SSRFError) as ctx:
                validate_external_url("http://attacker-controlled.example.com/")
            self.assertIn("127.0.0.1", str(ctx.exception))

    def test_hostname_resolving_to_imds_rejected(self):
        """A public hostname pointed at IMDS is the most realistic
        SSRF-pivot vector. Reject it."""
        with mock.patch(
            "apps.integrations_chat.ssrf_guard.socket.getaddrinfo"
        ) as mock_dns:
            import socket as _socket
            mock_dns.return_value = [
                (
                    _socket.AF_INET, _socket.SOCK_STREAM, 0, "",
                    ("169.254.169.254", 0),
                ),
            ]
            with self.assertRaises(SSRFError):
                validate_external_url("http://imds-bait.example.com/")

    def test_public_hostname_accepted(self):
        """Sanity check: a hostname that resolves to a public IP passes."""
        with mock.patch(
            "apps.integrations_chat.ssrf_guard.socket.getaddrinfo"
        ) as mock_dns:
            import socket as _socket
            mock_dns.return_value = [
                (
                    _socket.AF_INET, _socket.SOCK_STREAM, 0, "",
                    ("8.8.8.8", 0),
                ),
            ]
            host, ip = validate_external_url("https://public.example.com/page")
            self.assertEqual(host, "public.example.com")
            self.assertEqual(ip, "8.8.8.8")

    # -- Edge cases ---------------------------------------------------------

    def test_missing_hostname_rejected(self):
        with self.assertRaises(SSRFError):
            validate_external_url("https:///path-only")


class SafeGetIntegrationTestCase(SimpleTestCase):
    """
    `safe_get` orchestration: redirect refusal + size-cap enforcement.

    These tests stub `requests.Session.get` so we don't make real
    network calls; the goal is to verify the post-validation safety
    behavior (3xx → SSRFError, large body → SSRFError).
    """

    def _public_dns(self, mock_dns):
        import socket as _socket
        mock_dns.return_value = [
            (
                _socket.AF_INET, _socket.SOCK_STREAM, 0, "",
                ("8.8.8.8", 0),
            ),
        ]

    def test_redirect_response_raises_ssrf_error(self):
        """A 302 with a Location header is refused — the redirect
        target may be a private host."""
        with mock.patch(
            "apps.integrations_chat.ssrf_guard.socket.getaddrinfo"
        ) as mock_dns:
            self._public_dns(mock_dns)

            fake_resp = mock.MagicMock()
            fake_resp.status_code = 302
            fake_resp.headers = {"Location": "http://169.254.169.254/"}
            fake_resp.close = mock.MagicMock()

            with mock.patch(
                "requests.Session.get", return_value=fake_resp,
            ):
                with self.assertRaises(SSRFError) as ctx:
                    safe_get("https://public.example.com/page")
                self.assertIn("REDIRECT", str(ctx.exception))

    def test_oversized_body_raises_ssrf_error(self):
        """Streaming reader stops + raises once max_bytes is exceeded."""
        with mock.patch(
            "apps.integrations_chat.ssrf_guard.socket.getaddrinfo"
        ) as mock_dns:
            self._public_dns(mock_dns)

            big_chunks = [b"A" * 1024 for _ in range(20)]  # 20 KB

            fake_resp = mock.MagicMock()
            fake_resp.status_code = 200
            fake_resp.headers = {}
            fake_resp.iter_content = mock.MagicMock(
                return_value=iter(big_chunks),
            )
            fake_resp.close = mock.MagicMock()

            with mock.patch(
                "requests.Session.get", return_value=fake_resp,
            ):
                with self.assertRaises(SSRFError) as ctx:
                    safe_get(
                        "https://public.example.com/big",
                        max_bytes=8 * 1024,  # 8 KB cap
                    )
                self.assertIn("SIZE_CAP", str(ctx.exception))

    def test_normal_body_returned(self):
        """Happy path — small public response gets buffered into
        `_content` so callers can use `.text`."""
        with mock.patch(
            "apps.integrations_chat.ssrf_guard.socket.getaddrinfo"
        ) as mock_dns:
            self._public_dns(mock_dns)

            chunks = [b"<html>", b"hi", b"</html>"]

            fake_resp = mock.MagicMock()
            fake_resp.status_code = 200
            fake_resp.headers = {}
            fake_resp.iter_content = mock.MagicMock(
                return_value=iter(chunks),
            )
            fake_resp.close = mock.MagicMock()

            with mock.patch(
                "requests.Session.get", return_value=fake_resp,
            ):
                resp = safe_get("https://public.example.com/")
                self.assertEqual(resp._content, b"<html>hi</html>")
                self.assertTrue(resp._content_consumed)

    def test_safe_get_rejects_imds_before_dns(self):
        """End-to-end: the chatbot ingestion pivot — admin pastes the
        AWS IMDS URL — must short-circuit at validate_external_url
        without even constructing a Session."""
        with mock.patch("requests.Session.get") as mock_get:
            with self.assertRaises(SSRFError):
                safe_get("http://169.254.169.254/latest/meta-data/")
            mock_get.assert_not_called()


class PinnedIPAdapterTestCase(SimpleTestCase):
    """
    Smoke coverage for `_PinnedIPAdapter` internals — verifies the
    thread-safe refactor (review note BE-SEC-SSRF-OBS2) wires the
    pinned-IP connection class through urllib3's
    ``pool_classes_by_scheme`` extension point and isolates state
    per-adapter so concurrent requests cannot cross-contaminate.

    Pre-refactor risk: a module-level ``socket.getaddrinfo`` monkey-patch
    leaked across threads. After the refactor the pinned IP is captured
    in a class closure on per-adapter ``HTTPSConnection`` subclasses, so
    two adapters with different pinned IPs MUST own distinct connection
    classes.
    """

    def test_pool_uses_pinned_https_connection_class(self):
        """``poolmanager.pool_classes_by_scheme['https'].ConnectionCls``
        is the pinned subclass produced by ``_build_pinned_pool_classes``,
        not urllib3's stock ``HTTPSConnection``."""
        from apps.integrations_chat.ssrf_guard import _PinnedIPAdapter

        adapter = _PinnedIPAdapter(hostname="example.com", pinned_ip="8.8.8.8")
        try:
            https_pool_cls = adapter.poolmanager.pool_classes_by_scheme["https"]
            http_pool_cls = adapter.poolmanager.pool_classes_by_scheme["http"]
            self.assertEqual(
                https_pool_cls.ConnectionCls.__name__,
                "_PinnedHTTPSConnection",
            )
            self.assertEqual(
                http_pool_cls.ConnectionCls.__name__,
                "_PinnedHTTPConnection",
            )
        finally:
            adapter.close()

    def test_two_adapters_get_distinct_connection_classes(self):
        """Two adapters with different pinned IPs must own structurally
        distinct connection classes — no shared global state.

        This is the structural property that closes the OBS2 race: the
        pinned IP lives in a per-adapter class closure, so a thread A
        request to IP_A cannot end up dialing IP_B because thread B
        mutated a shared module attribute mid-flight."""
        from apps.integrations_chat.ssrf_guard import _PinnedIPAdapter

        adapter_a = _PinnedIPAdapter(hostname="a.example.com", pinned_ip="8.8.8.8")
        adapter_b = _PinnedIPAdapter(hostname="b.example.com", pinned_ip="1.1.1.1")
        try:
            cls_a = adapter_a.poolmanager.pool_classes_by_scheme["https"].ConnectionCls
            cls_b = adapter_b.poolmanager.pool_classes_by_scheme["https"].ConnectionCls

            # Different class objects (each came from its own factory call).
            self.assertIsNot(cls_a, cls_b)
            # And they live in their own pool classes too.
            self.assertIsNot(
                adapter_a.poolmanager.pool_classes_by_scheme["https"],
                adapter_b.poolmanager.pool_classes_by_scheme["https"],
            )
        finally:
            adapter_a.close()
            adapter_b.close()

    def test_pinned_ip_captured_in_class_closure(self):
        """Functional probe: invoking the connection's ``_new_conn``
        hits ``urllib3.util.connection.create_connection`` with the
        adapter's pinned IP — not the hostname.  We patch the urllib3
        helper rather than the stdlib socket so the test does not
        accidentally exercise a real DNS lookup."""
        from apps.integrations_chat.ssrf_guard import _PinnedIPAdapter

        adapter = _PinnedIPAdapter(hostname="example.com", pinned_ip="8.8.8.8")
        try:
            https_cls = adapter.poolmanager.pool_classes_by_scheme["https"].ConnectionCls
            # Construct a connection instance the way urllib3 does;
            # we don't actually need a working pool, only the
            # ``_new_conn`` call path.
            conn = https_cls(host="example.com", port=443)

            with mock.patch(
                "urllib3.util.connection.create_connection",
                return_value=mock.sentinel.fake_socket,
            ) as mock_create:
                result = conn._new_conn()

            self.assertIs(result, mock.sentinel.fake_socket)
            # First positional arg is (pinned_ip, port) — proves the
            # closure carried the pinned IP, NOT the hostname.
            args, _ = mock_create.call_args
            self.assertEqual(args[0], ("8.8.8.8", 443))
        finally:
            adapter.close()
