# tests/test_rich_text.py
"""
Tests for utils/rich_text.py — HTML sanitization and rich text processing.

Security properties verified:
1. XSS prevention: <script> tags stripped
2. Event handler attributes (onclick, onload, etc.) stripped
3. javascript: protocol in href stripped
4. Allowed tags (p, strong, em, etc.) preserved
5. Allowed attributes (href, src) preserved
6. Forbidden CSS properties stripped (only allowed-list CSS permitted)
7. Inline images with rtimg: protocol handled correctly
8. Empty/None input handled gracefully
9. sanitize_rich_text_html returns a string
10. collect_rich_text_image_ids extracts image UUIDs

No mocks — these tests exercise real HTML sanitization behavior.
"""

import pytest
from django.test import TestCase


# ===========================================================================
# Helpers
# ===========================================================================

_VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"
_ANOTHER_UUID = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


# ===========================================================================
# 1. XSS Prevention Tests
# ===========================================================================


class XSSPreventionTestCase(TestCase):
    """sanitize_rich_text_html must strip XSS vectors."""

    def test_script_tags_stripped(self):
        """<script> tags must be completely removed."""
        from utils.rich_text import sanitize_rich_text_html

        dirty = "<p>Hello</p><script>alert('XSS')</script>"
        result = sanitize_rich_text_html(dirty)

        self.assertNotIn("<script>", result, "<script> tag must be stripped")
        self.assertNotIn("alert('XSS')", result, "Script content must be stripped")
        self.assertIn("<p>Hello</p>", result, "Safe content must be preserved")

    def test_onclick_attribute_stripped(self):
        """onclick and other event handler attributes must be removed."""
        from utils.rich_text import sanitize_rich_text_html

        dirty = '<p onclick="stealCookies()">Click me</p>'
        result = sanitize_rich_text_html(dirty)

        self.assertNotIn("onclick", result, "onclick attribute must be stripped")
        self.assertIn("Click me", result, "Text content must be preserved")

    def test_onerror_attribute_stripped(self):
        """onerror attribute (used in img-based XSS) must be stripped."""
        from utils.rich_text import sanitize_rich_text_html

        dirty = '<img src="x" onerror="alert(1)">'
        result = sanitize_rich_text_html(dirty)

        self.assertNotIn("onerror", result, "onerror attribute must be stripped")

    def test_javascript_href_stripped(self):
        """javascript: protocol in href attributes must be stripped."""
        from utils.rich_text import sanitize_rich_text_html

        dirty = '<a href="javascript:alert(1)">Click</a>'
        result = sanitize_rich_text_html(dirty)

        self.assertNotIn("javascript:", result, "javascript: protocol must be stripped from href")

    def test_data_uri_in_href_stripped(self):
        """data: URI in href must be blocked (can carry malicious content)."""
        from utils.rich_text import sanitize_rich_text_html

        dirty = '<a href="data:text/html,<script>alert(1)</script>">Click</a>'
        result = sanitize_rich_text_html(dirty)

        self.assertNotIn("data:text/html", result, "data: URI in href must be stripped")

    def test_iframe_stripped(self):
        """<iframe> is not in ALLOWED_TAGS and must be removed."""
        from utils.rich_text import sanitize_rich_text_html

        dirty = '<iframe src="https://evil.example.com"></iframe>'
        result = sanitize_rich_text_html(dirty)

        self.assertNotIn("<iframe", result, "<iframe> must be stripped")
        self.assertNotIn("evil.example.com", result, "Iframe src must be stripped")

    def test_form_stripped(self):
        """<form> tag must be removed."""
        from utils.rich_text import sanitize_rich_text_html

        dirty = '<form action="https://steal.example.com"><input type="text"></form>'
        result = sanitize_rich_text_html(dirty)

        self.assertNotIn("<form", result, "<form> tag must be stripped")

    def test_object_tag_stripped(self):
        """<object> tag (Flash/plugin) must be stripped."""
        from utils.rich_text import sanitize_rich_text_html

        dirty = '<object data="malware.swf" type="application/x-shockwave-flash"></object>'
        result = sanitize_rich_text_html(dirty)

        self.assertNotIn("<object", result, "<object> tag must be stripped")


# ===========================================================================
# 2. Allowed Tag Preservation Tests
# ===========================================================================


class AllowedTagPreservationTestCase(TestCase):
    """Allowed HTML tags must be preserved through sanitization."""

    def _sanitize(self, html: str) -> str:
        from utils.rich_text import sanitize_rich_text_html
        return sanitize_rich_text_html(html)

    def test_paragraph_tag_preserved(self):
        """<p> tags must pass through."""
        result = self._sanitize("<p>Hello world</p>")
        self.assertIn("<p>", result)
        self.assertIn("Hello world", result)

    def test_strong_tag_preserved(self):
        """<strong> tags must pass through."""
        result = self._sanitize("<strong>Bold text</strong>")
        self.assertIn("<strong>", result)

    def test_em_tag_preserved(self):
        """<em> tags must pass through."""
        result = self._sanitize("<em>Italic text</em>")
        self.assertIn("<em>", result)

    def test_heading_tags_preserved(self):
        """h1, h2, h3, h4 must pass through."""
        result = self._sanitize("<h1>Title</h1><h2>Sub</h2><h3>Smaller</h3>")
        self.assertIn("<h1>", result)
        self.assertIn("<h2>", result)
        self.assertIn("<h3>", result)

    def test_ordered_list_preserved(self):
        """<ol>/<li> must pass through."""
        result = self._sanitize("<ol><li>Item 1</li><li>Item 2</li></ol>")
        self.assertIn("<ol>", result)
        self.assertIn("<li>", result)

    def test_unordered_list_preserved(self):
        """<ul>/<li> must pass through."""
        result = self._sanitize("<ul><li>Bullet</li></ul>")
        self.assertIn("<ul>", result)

    def test_anchor_with_https_href_preserved(self):
        """<a href='https://...'>link</a> must pass through."""
        result = self._sanitize('<a href="https://example.com">Link</a>')
        self.assertIn('href="https://example.com"', result)
        self.assertIn("Link", result)

    def test_blockquote_preserved(self):
        """<blockquote> must pass through."""
        result = self._sanitize("<blockquote>Quoted text</blockquote>")
        self.assertIn("<blockquote>", result)

    def test_code_and_pre_preserved(self):
        """<code> and <pre> must pass through."""
        result = self._sanitize("<pre><code>def hello(): pass</code></pre>")
        self.assertIn("<code>", result)
        self.assertIn("<pre>", result)


# ===========================================================================
# 3. CSS Sanitization Tests
# ===========================================================================


class CSSSanitizationTestCase(TestCase):
    """Inline CSS must be filtered to only allowed properties."""

    def _sanitize(self, html: str) -> str:
        from utils.rich_text import sanitize_rich_text_html
        return sanitize_rich_text_html(html)

    def test_allowed_css_property_preserved(self):
        """color is in ALLOWED_CSS_PROPS and must be preserved."""
        result = self._sanitize('<p style="color: red;">Red text</p>')
        self.assertIn("color", result, "color CSS property must be preserved")

    def test_font_size_preserved(self):
        """font-size is in ALLOWED_CSS_PROPS and must be preserved."""
        result = self._sanitize('<p style="font-size: 14px;">Text</p>')
        self.assertIn("font-size", result)

    def test_dangerous_css_stripped(self):
        """
        CSS properties that can load external resources or bypass security
        (e.g., background-image: url(), -moz-binding) must be stripped.
        """
        result = self._sanitize(
            '<p style="background-image: url(https://evil.example.com/tracker.png);">Text</p>'
        )
        # background-image with url() is not in ALLOWED_CSS_PROPS
        self.assertNotIn("background-image: url(", result)

    def test_expression_in_css_stripped(self):
        """CSS expression() is a legacy IE XSS vector and must be stripped."""
        result = self._sanitize('<p style="width: expression(alert(1));">Text</p>')
        self.assertNotIn("expression(", result)

    def test_text_align_preserved(self):
        """text-align is in ALLOWED_CSS_PROPS."""
        result = self._sanitize('<p style="text-align: center;">Centered</p>')
        self.assertIn("text-align", result)


# ===========================================================================
# 4. Empty/None Input Tests
# ===========================================================================


class EmptyInputTestCase(TestCase):
    """Empty or None inputs must not raise exceptions."""

    def test_sanitize_empty_string_returns_empty(self):
        """sanitize_rich_text_html('') must return ''."""
        from utils.rich_text import sanitize_rich_text_html
        self.assertEqual(sanitize_rich_text_html(""), "")

    def test_collect_image_ids_empty_string_returns_empty_set(self):
        """collect_rich_text_image_ids('') must return an empty set."""
        from utils.rich_text import collect_rich_text_image_ids
        self.assertEqual(collect_rich_text_image_ids(""), set())

    def test_sanitize_returns_string(self):
        """sanitize_rich_text_html must always return a string."""
        from utils.rich_text import sanitize_rich_text_html
        result = sanitize_rich_text_html("<p>Normal content</p>")
        self.assertIsInstance(result, str)

    def test_sanitize_plain_text_passes_through(self):
        """Plain text without HTML tags must pass through unchanged (or wrapped)."""
        from utils.rich_text import sanitize_rich_text_html
        result = sanitize_rich_text_html("Just plain text without any tags")
        self.assertIn("Just plain text", result)


# ===========================================================================
# 5. Inline Image ID Extraction Tests
# ===========================================================================


class ImageIDExtractionTestCase(TestCase):
    """collect_rich_text_image_ids must correctly extract image UUIDs."""

    def test_extracts_uuid_from_data_image_id(self):
        """UUID in data-image-id attribute must be extracted."""
        from utils.rich_text import collect_rich_text_image_ids

        html = f'<img src="rtimg:{_VALID_UUID}" data-image-id="{_VALID_UUID}">'
        ids = collect_rich_text_image_ids(html)

        self.assertIn(
            _VALID_UUID,
            ids,
            "UUID in data-image-id must be extracted by collect_rich_text_image_ids",
        )

    def test_extracts_uuid_from_rtimg_src(self):
        """UUID in rtimg:<uuid> src must be extracted."""
        from utils.rich_text import collect_rich_text_image_ids

        html = f'<img src="rtimg:{_VALID_UUID}" alt="image">'
        ids = collect_rich_text_image_ids(html)

        self.assertIn(_VALID_UUID, ids)

    def test_multiple_images_all_extracted(self):
        """Multiple image UUIDs must all be extracted."""
        from utils.rich_text import collect_rich_text_image_ids

        html = (
            f'<img src="rtimg:{_VALID_UUID}" data-image-id="{_VALID_UUID}">'
            f'<img src="rtimg:{_ANOTHER_UUID}" data-image-id="{_ANOTHER_UUID}">'
        )
        ids = collect_rich_text_image_ids(html)

        self.assertIn(_VALID_UUID, ids)
        self.assertIn(_ANOTHER_UUID, ids)

    def test_invalid_src_without_uuid_excluded(self):
        """Non-rtimg src values must not produce false UUID extractions."""
        from utils.rich_text import collect_rich_text_image_ids

        html = '<img src="https://cdn.example.com/image.jpg" alt="photo">'
        ids = collect_rich_text_image_ids(html)

        self.assertEqual(ids, set(), "External src URLs must not produce UUID extractions")

    def test_html_without_images_returns_empty_set(self):
        """HTML with no images must return an empty set."""
        from utils.rich_text import collect_rich_text_image_ids

        html = "<p>Just a paragraph <strong>with bold</strong></p>"
        ids = collect_rich_text_image_ids(html)

        self.assertEqual(ids, set())


# ===========================================================================
# 6. Image Canonicalization in Sanitize Tests
# ===========================================================================


class ImageCanonicalizationTestCase(TestCase):
    """
    sanitize_rich_text_html must canonicalize img src to rtimg:<uuid>.
    Images without a valid UUID must be removed entirely.
    """

    def test_img_without_uuid_is_removed(self):
        """<img> without a valid UUID in data-image-id or src must be removed."""
        from utils.rich_text import sanitize_rich_text_html

        html = '<img src="https://external.example.com/logo.png" alt="logo">'
        result = sanitize_rich_text_html(html)

        # Image without valid UUID data-image-id/rtimg src must be removed
        # (bleach strips the external URL, and without a UUID it's decomposed)
        # The tag itself is gone
        self.assertNotIn('src="https://external.example.com/logo.png"', result)

    def test_img_with_valid_rtimg_src_preserved(self):
        """<img> with valid rtimg:<uuid> src is preserved in canonical form."""
        from utils.rich_text import sanitize_rich_text_html

        html = f'<img src="rtimg:{_VALID_UUID}" data-image-id="{_VALID_UUID}" alt="chart">'
        result = sanitize_rich_text_html(html)

        self.assertIn(_VALID_UUID, result, "Valid image UUID must be preserved after sanitization")
