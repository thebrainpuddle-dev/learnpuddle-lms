from unittest.mock import patch

from django.http import HttpResponse
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.maic_models import TenantAIConfig
from apps.tenants.models import Tenant
from apps.users.models import User


HOST = "tts-school.lms.com"


def _tenant():
    return Tenant.objects.create(
        name="TTS School",
        slug="tts-school",
        subdomain="tts-school",
        email="admin@tts-school.test",
        is_active=True,
        feature_maic=True,
    )


def _user(tenant, role="TEACHER"):
    return User.objects.create_user(
        email=f"{role.lower()}@tts-school.test",
        password="Pass!1234",
        first_name="TTS",
        last_name="User",
        tenant=tenant,
        role=role,
        is_active=True,
    )


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class MaicTtsViewSecurityTests(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _user(self.tenant)
        self.config = TenantAIConfig.objects.create(
            tenant=self.tenant,
            llm_provider="openrouter",
            llm_model="openrouter/auto",
            tts_provider="edge",
            maic_enabled=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.teacher)
        self.client.defaults["HTTP_HOST"] = HOST

    def test_rejects_oversized_tts_text_before_proxy_or_provider(self):
        with patch("apps.courses.maic_views._proxy_binary") as proxy, patch(
            "apps.courses.maic_views.generate_tts_audio"
        ) as tts:
            response = self.client.post(
                "/api/v1/teacher/maic/generate/tts/",
                {"text": "x" * 2001, "voiceId": "en-IN-PrabhatNeural"},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["max_chars"], 2000)
        proxy.assert_not_called()
        tts.assert_not_called()

    def test_rejects_invalid_voice_id_before_proxy_or_provider(self):
        with patch("apps.courses.maic_views._proxy_binary") as proxy, patch(
            "apps.courses.maic_views.generate_tts_audio"
        ) as tts:
            response = self.client.post(
                "/api/v1/teacher/maic/generate/tts/",
                {"text": "Hello class", "voiceId": "../../internal"},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "Invalid voiceId.")
        proxy.assert_not_called()
        tts.assert_not_called()

    def test_valid_tts_request_proxies_only_sanitized_payload(self):
        captured = {}

        def fake_proxy(_request, _path, _config, body_override=None):
            captured.update(body_override or {})
            return HttpResponse(status=204)

        with patch("apps.courses.maic_views._proxy_binary", side_effect=fake_proxy):
            response = self.client.post(
                "/api/v1/teacher/maic/generate/tts/",
                {
                    "text": "  Hello class  ",
                    "voiceId": "en-IN-PrabhatNeural",
                    "ignored": "do-not-forward",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            captured,
            {
                "text": "Hello class",
                "voiceId": "en-IN-PrabhatNeural",
                "voice_id": "en-IN-PrabhatNeural",
            },
        )
