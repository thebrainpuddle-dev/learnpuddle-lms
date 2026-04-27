# apps/tenants/tests_mode_switching.py
"""
TASK-020 — Education vs Corporate mode switching tests.

Covers:
- Model defaults (`mode='education'`, `mode_label_overrides={}`)
- `Tenant.get_mode_labels()` returns education defaults
- `Tenant.get_mode_labels()` returns corporate defaults when flipped
- Overrides are layered on top of active mode
- `GET /api/v1/tenants/me/` exposes `mode` + `mode_labels`
- `GET /api/v1/tenants/settings/` exposes `mode`, `mode_label_overrides`,
  `mode_labels`
- Admin `PATCH /api/v1/tenants/settings/` flips mode (200)
- Admin `PATCH /api/v1/tenants/settings/` writes overrides; `/me` reflects
- Clearing overrides reverts labels to mode defaults
- Non-admin `PATCH` is blocked (403)
- Invalid mode value → 400
- Cross-tenant: admin of tenant A cannot flip tenant B
"""

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain, **extra):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=f"{subdomain}@example.com", is_active=True, **extra,
    )


def _make_user(email, tenant, role="TEACHER"):
    return User.objects.create_user(
        email=email, password="Pass!123",
        first_name="Test", last_name="User",
        tenant=tenant, role=role, is_active=True,
    )


def _client_for(user, subdomain):
    c = APIClient()
    c.force_authenticate(user=user)
    c.defaults["HTTP_HOST"] = f"{subdomain}.lms.com"
    return c


# ===========================================================================
# 1. Model-level tests
# ===========================================================================

class TenantModeModelTests(TestCase):
    def test_mode_defaults_to_education(self):
        t = _make_tenant("Edu School", "edu1")
        self.assertEqual(t.mode, "education")

    def test_mode_label_overrides_defaults_to_empty_dict(self):
        t = _make_tenant("Edu School", "edu2")
        self.assertEqual(t.mode_label_overrides, {})

    def test_education_mode_returns_education_labels(self):
        t = _make_tenant("Edu", "edu3", mode="education")
        labels = t.get_mode_labels()
        self.assertEqual(labels["learner"], "Teacher")
        self.assertEqual(labels["learner_plural"], "Teachers")
        self.assertEqual(labels["course"], "Course")
        self.assertEqual(labels["badge"], "Badge")
        self.assertEqual(labels["league"], "League")
        self.assertEqual(labels["xp"], "XP")

    def test_corporate_mode_returns_corporate_labels(self):
        t = _make_tenant("Corp", "corp1", mode="corporate")
        labels = t.get_mode_labels()
        self.assertEqual(labels["learner"], "Employee")
        self.assertEqual(labels["learner_plural"], "Employees")
        self.assertEqual(labels["course"], "Training Program")
        self.assertEqual(labels["badge"], "Achievement")
        self.assertEqual(labels["league"], "Tier")
        self.assertEqual(labels["xp"], "Points")

    def test_overrides_are_applied_on_top_of_mode_defaults(self):
        t = _make_tenant(
            "Override Corp", "ovr1",
            mode="corporate",
            mode_label_overrides={"course": "Masterclass", "badge": "Trophy"},
        )
        labels = t.get_mode_labels()
        # Overrides win
        self.assertEqual(labels["course"], "Masterclass")
        self.assertEqual(labels["badge"], "Trophy")
        # Non-overridden keys still fall through to corporate defaults
        self.assertEqual(labels["learner"], "Employee")
        self.assertEqual(labels["xp"], "Points")

    def test_invalid_mode_fails_full_clean(self):
        t = _make_tenant("Bad", "bad1")
        t.mode = "hybrid"
        with self.assertRaises(ValidationError):
            t.full_clean()


# ===========================================================================
# 2. API tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class TenantModeApiTests(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("API School", "apisch")
        self.admin = _make_user("admin@apisch.test", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _make_user("teacher@apisch.test", self.tenant, role="TEACHER")

    # ---------- GET /me ----------

    def test_me_includes_mode_and_mode_labels(self):
        c = _client_for(self.teacher, "apisch")
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("mode"), "education")
        labels = r.data.get("mode_labels")
        self.assertIsInstance(labels, dict)
        self.assertEqual(labels.get("learner"), "Teacher")
        self.assertEqual(labels.get("course"), "Course")

    def test_me_reflects_corporate_labels_after_flip(self):
        self.tenant.mode = "corporate"
        self.tenant.save(update_fields=["mode"])
        c = _client_for(self.teacher, "apisch")
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("mode"), "corporate")
        self.assertEqual(r.data["mode_labels"]["learner"], "Employee")
        self.assertEqual(r.data["mode_labels"]["course"], "Training Program")

    def test_me_reflects_override_labels(self):
        self.tenant.mode_label_overrides = {"course": "Masterclass"}
        self.tenant.save(update_fields=["mode_label_overrides"])
        c = _client_for(self.teacher, "apisch")
        r = c.get("/api/v1/tenants/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["mode_labels"]["course"], "Masterclass")
        # Unrelated keys remain at education defaults
        self.assertEqual(r.data["mode_labels"]["learner"], "Teacher")

    # ---------- GET /settings ----------

    def test_settings_get_returns_mode_overrides_and_labels(self):
        c = _client_for(self.admin, "apisch")
        r = c.get("/api/v1/tenants/settings/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("mode"), "education")
        self.assertEqual(r.data.get("mode_label_overrides"), {})
        self.assertEqual(r.data["mode_labels"]["learner"], "Teacher")

    # ---------- PATCH /settings ----------

    def test_admin_patch_flips_mode_and_returns_new_labels(self):
        c = _client_for(self.admin, "apisch")
        r = c.patch("/api/v1/tenants/settings/", {"mode": "corporate"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.get("mode"), "corporate")
        self.assertEqual(r.data["mode_labels"]["learner"], "Employee")

        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.mode, "corporate")

    def test_admin_patch_writes_overrides_and_me_reflects_them(self):
        admin_c = _client_for(self.admin, "apisch")
        r = admin_c.patch(
            "/api/v1/tenants/settings/",
            {"mode_label_overrides": {"course": "Masterclass"}},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["mode_label_overrides"], {"course": "Masterclass"})

        teacher_c = _client_for(self.teacher, "apisch")
        me = teacher_c.get("/api/v1/tenants/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["mode_labels"]["course"], "Masterclass")

    def test_clearing_overrides_reverts_to_mode_default(self):
        self.tenant.mode_label_overrides = {"course": "Masterclass"}
        self.tenant.save(update_fields=["mode_label_overrides"])

        admin_c = _client_for(self.admin, "apisch")
        r = admin_c.patch(
            "/api/v1/tenants/settings/",
            {"mode_label_overrides": {}},
            format="json",
        )
        self.assertEqual(r.status_code, 200)

        teacher_c = _client_for(self.teacher, "apisch")
        me = teacher_c.get("/api/v1/tenants/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["mode_labels"]["course"], "Course")

    def test_non_admin_patch_is_forbidden(self):
        c = _client_for(self.teacher, "apisch")
        r = c.patch("/api/v1/tenants/settings/", {"mode": "corporate"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_invalid_mode_value_returns_400(self):
        c = _client_for(self.admin, "apisch")
        r = c.patch("/api/v1/tenants/settings/", {"mode": "hybrid"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("mode", r.data)


# ===========================================================================
# 3. Cross-tenant isolation
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
)
class TenantModeCrossTenantTests(TestCase):

    def setUp(self):
        self.tenant_a = _make_tenant("Tenant A", "ta")
        self.tenant_b = _make_tenant("Tenant B", "tb")
        self.admin_a = _make_user("a@ta.test", self.tenant_a, role="SCHOOL_ADMIN")

    def test_admin_in_a_cannot_flip_mode_on_b_subdomain(self):
        """
        When admin_a hits /settings on tenant B's subdomain, the
        @tenant_required decorator rejects with 403 (user.tenant_id !=
        resolved tenant.id).  Regardless, tenant B must remain in its
        original mode.
        """
        c = APIClient()
        c.force_authenticate(user=self.admin_a)
        c.defaults["HTTP_HOST"] = "tb.lms.com"  # tenant B's subdomain
        r = c.patch("/api/v1/tenants/settings/", {"mode": "corporate"}, format="json")
        self.assertEqual(r.status_code, 403)

        self.tenant_b.refresh_from_db()
        self.assertEqual(self.tenant_b.mode, "education")
