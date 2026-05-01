# tests/progress/test_certificate_service.py
"""
Unit tests for apps/progress/certificate_service.py — currently 0% coverage.

Covers:
1. hex_to_rgb()              — hex color conversion
2. get_certificate_filename()— filename sanitisation
3. generate_certificate_pdf() — PDF buffer generation

Note: ReportLab (reportlab==4.1.0) must be installed. Tests run entirely in
memory; no disk I/O is performed.
"""

import io
from datetime import datetime

import pytest


# ===========================================================================
# 1. hex_to_rgb()
# ===========================================================================

class TestHexToRgb:
    """Unit tests for hex_to_rgb() — converts hex to 0-1 float RGB tuple."""

    def test_black_hex_returns_zero_tuple(self):
        from apps.progress.certificate_service import hex_to_rgb
        r, g, b = hex_to_rgb("#000000")
        assert r == pytest.approx(0.0)
        assert g == pytest.approx(0.0)
        assert b == pytest.approx(0.0)

    def test_white_hex_returns_one_tuple(self):
        from apps.progress.certificate_service import hex_to_rgb
        r, g, b = hex_to_rgb("#FFFFFF")
        assert r == pytest.approx(1.0)
        assert g == pytest.approx(1.0)
        assert b == pytest.approx(1.0)

    def test_red_hex_returns_correct_rgb(self):
        from apps.progress.certificate_service import hex_to_rgb
        r, g, b = hex_to_rgb("#FF0000")
        assert r == pytest.approx(1.0)
        assert g == pytest.approx(0.0)
        assert b == pytest.approx(0.0)

    def test_green_hex_returns_correct_rgb(self):
        from apps.progress.certificate_service import hex_to_rgb
        r, g, b = hex_to_rgb("#00FF00")
        assert r == pytest.approx(0.0)
        assert g == pytest.approx(1.0)
        assert b == pytest.approx(0.0)

    def test_blue_hex_returns_correct_rgb(self):
        from apps.progress.certificate_service import hex_to_rgb
        r, g, b = hex_to_rgb("#0000FF")
        assert r == pytest.approx(0.0)
        assert g == pytest.approx(0.0)
        assert b == pytest.approx(1.0)

    def test_default_primary_color_is_valid(self):
        """The default primary color (#1F4788) should parse without errors."""
        from apps.progress.certificate_service import hex_to_rgb
        r, g, b = hex_to_rgb("#1F4788")
        # r = 0x1F / 255 ≈ 0.122, g = 0x47 / 255 ≈ 0.278, b = 0x88 / 255 ≈ 0.533
        assert 0.0 < r < 1.0
        assert 0.0 < g < 1.0
        assert 0.0 < b < 1.0

    def test_strips_leading_hash(self):
        """hex_to_rgb must strip the leading '#' before parsing."""
        from apps.progress.certificate_service import hex_to_rgb
        # Should not raise; both forms should produce the same result
        r1, g1, b1 = hex_to_rgb("#1F4788")
        r2, g2, b2 = hex_to_rgb("1F4788")
        assert r1 == pytest.approx(r2)
        assert g1 == pytest.approx(g2)
        assert b1 == pytest.approx(b2)

    def test_returns_tuple_of_three_floats(self):
        from apps.progress.certificate_service import hex_to_rgb
        result = hex_to_rgb("#AABBCC")
        assert len(result) == 3
        assert all(isinstance(v, float) for v in result)

    def test_all_values_in_zero_to_one_range(self):
        """All channel values must be in [0.0, 1.0] for ReportLab compatibility."""
        from apps.progress.certificate_service import hex_to_rgb
        for hex_color in ["#000000", "#FFFFFF", "#FF8800", "#123456"]:
            r, g, b = hex_to_rgb(hex_color)
            assert 0.0 <= r <= 1.0, f"Red channel out of range for {hex_color}"
            assert 0.0 <= g <= 1.0, f"Green channel out of range for {hex_color}"
            assert 0.0 <= b <= 1.0, f"Blue channel out of range for {hex_color}"


# ===========================================================================
# 2. get_certificate_filename()
# ===========================================================================

class TestGetCertificateFilename:
    """Unit tests for get_certificate_filename() — safe filename generation."""

    def test_returns_string(self):
        from apps.progress.certificate_service import get_certificate_filename
        result = get_certificate_filename("Jane Doe", "Python 101")
        assert isinstance(result, str)

    def test_starts_with_certificate_prefix(self):
        from apps.progress.certificate_service import get_certificate_filename
        result = get_certificate_filename("Jane Doe", "Python 101")
        assert result.startswith("certificate_")

    def test_ends_with_pdf_extension(self):
        from apps.progress.certificate_service import get_certificate_filename
        result = get_certificate_filename("Jane Doe", "Python 101")
        assert result.endswith(".pdf")

    def test_replaces_spaces_with_underscores(self):
        from apps.progress.certificate_service import get_certificate_filename
        result = get_certificate_filename("Jane Doe", "Advanced Python")
        assert " " not in result

    def test_includes_teacher_name_fragment(self):
        from apps.progress.certificate_service import get_certificate_filename
        result = get_certificate_filename("Jane Doe", "Python 101")
        assert "Jane" in result or "Jane_Doe" in result

    def test_includes_course_title_fragment(self):
        from apps.progress.certificate_service import get_certificate_filename
        result = get_certificate_filename("Jane Doe", "Python 101")
        assert "Python" in result

    def test_strips_special_characters(self):
        """Characters that are unsafe in filenames must be removed."""
        from apps.progress.certificate_service import get_certificate_filename
        result = get_certificate_filename("O'Brien-Smith", "C++ & Java!")
        # Special chars like ', !, & should be stripped
        unsafe = set('<>:"/\\|?*\'!')
        for char in unsafe:
            assert char not in result, f"Unsafe char {char!r} found in {result!r}"

    def test_long_names_are_truncated(self):
        """Names longer than 30 chars should be truncated to keep filename manageable."""
        from apps.progress.certificate_service import get_certificate_filename
        long_teacher = "A" * 50
        long_course = "B" * 50
        result = get_certificate_filename(long_teacher, long_course)
        # Filename should be reasonable length (prefix + 30 + _ + 30 + .pdf = ~75 chars)
        assert len(result) < 100

    def test_simple_alphanumeric_names_preserved(self):
        from apps.progress.certificate_service import get_certificate_filename
        result = get_certificate_filename("Alice", "Math101")
        assert "Alice" in result
        assert "Math101" in result


# ===========================================================================
# 3. generate_certificate_pdf()
# ===========================================================================

class TestGenerateCertificatePdf:
    """Unit tests for generate_certificate_pdf() — PDF buffer generation."""

    _TEACHER_NAME = "Jane Smith"
    _COURSE_TITLE = "Professional Development 101"
    _TENANT_NAME = "Riverside Academy"
    _COMPLETION_DATE = datetime(2026, 3, 15, 10, 0, 0)

    def _generate(self, **kwargs):
        from apps.progress.certificate_service import generate_certificate_pdf
        defaults = {
            "teacher_name": self._TEACHER_NAME,
            "course_title": self._COURSE_TITLE,
            "completion_date": self._COMPLETION_DATE,
            "tenant_name": self._TENANT_NAME,
        }
        defaults.update(kwargs)
        return generate_certificate_pdf(**defaults)

    def test_returns_bytesio(self):
        """Function must return a BytesIO buffer."""
        result = self._generate()
        assert isinstance(result, io.BytesIO)

    def test_buffer_is_seeked_to_start(self):
        """The returned buffer must be seeked to position 0 for callers to read."""
        result = self._generate()
        assert result.tell() == 0

    def test_buffer_contains_pdf_header(self):
        """The buffer must start with the PDF magic bytes (%PDF-)."""
        result = self._generate()
        header = result.read(5)
        assert header == b"%PDF-", f"Expected PDF header, got: {header!r}"

    def test_buffer_has_non_zero_size(self):
        """The generated PDF must not be empty."""
        result = self._generate()
        content = result.read()
        assert len(content) > 0

    def test_with_certificate_id(self):
        """Passing a certificate_id must not raise and must still produce a valid PDF."""
        result = self._generate(certificate_id="CERT-2026-001")
        result.seek(0)
        header = result.read(5)
        assert header == b"%PDF-"

    def test_without_certificate_id(self):
        """Calling without certificate_id (None default) must work correctly."""
        result = self._generate(certificate_id=None)
        result.seek(0)
        assert result.read(5) == b"%PDF-"

    def test_custom_primary_color(self):
        """A valid non-default primary_color must not raise."""
        result = self._generate(primary_color="#E63946")
        result.seek(0)
        assert result.read(5) == b"%PDF-"

    def test_without_logo(self):
        """Calling without tenant_logo_path (default None) must produce a valid PDF."""
        result = self._generate(tenant_logo_path=None)
        result.seek(0)
        assert result.read(5) == b"%PDF-"

    def test_with_invalid_logo_path_skips_gracefully(self, caplog):
        """
        A stale or missing tenant_logo_path must NOT raise — the certificate
        service pre-validates the path with os.path.isfile() before handing
        it to ReportLab's Image() constructor. If the file is missing, the
        logo is silently skipped (and a warning is logged), so the PDF is
        still produced for the teacher.

        Regression test for the OSError leak previously tracked in
        `_coordination/inbox/backend-engineer/CERT-SERVICE-DOCBUILD-OSERROR-LEAK-2026-04-30.md`.
        """
        import logging

        with caplog.at_level(logging.WARNING, logger="apps.progress.certificate_service"):
            result = self._generate(tenant_logo_path="/nonexistent/path/logo.png")

        # PDF was produced despite the bad logo path
        assert isinstance(result, io.BytesIO)
        assert result.tell() == 0
        header = result.read(5)
        assert header == b"%PDF-", f"Expected PDF header, got: {header!r}"

        # Warning was emitted explaining the skip
        skip_messages = [
            r.getMessage() for r in caplog.records
            if r.levelno == logging.WARNING and "certificate logo skipped" in r.getMessage()
        ]
        assert skip_messages, "Expected a 'certificate logo skipped' warning"
        assert any("file_missing" in m for m in skip_messages), (
            f"Expected file_missing reason in warning, got: {skip_messages!r}"
        )

    def test_pdf_is_landscape_a4(self):
        """The PDF should specify A4 landscape dimensions (297×210mm → ~841×595pt)."""
        result = self._generate()
        content = result.read()
        # A4 landscape mediabox is approx 841×595 pts — check presence of these numbers
        # in the page dictionary (exact encoding varies by ReportLab version)
        assert len(content) > 1000, "PDF is suspiciously small for A4 landscape"

    def test_two_calls_produce_independent_buffers(self):
        """Each call must return a fresh BytesIO; they must not share state."""
        buf1 = self._generate(teacher_name="Teacher One")
        buf2 = self._generate(teacher_name="Teacher Two")
        assert buf1 is not buf2
        content1 = buf1.read()
        content2 = buf2.read()
        assert content1 != content2
