"""
Coverage tests for ``apps.billing`` views and webhook handlers.

Scope
=====
The existing billing test files cover:
  - ``test_billing_redirect_url.py`` — the URL allow-list helper (36 tests)
  - ``test_stripe_webhook.py``       — the webhook endpoint exception
                                        granularity + dispatch (7 tests)

Those tests do NOT cover:
  - ``plan_list``, ``subscription_detail``, ``create_checkout``,
    ``create_portal``, ``payment_history``, ``preview_plan_change`` views
  - Auth / role / tenant isolation boundaries for the above views
  - The bodies of the individual webhook handlers
    (``handle_checkout_session_completed``, ``handle_subscription_created``,
    ``handle_subscription_updated``, ``handle_subscription_deleted``,
    ``handle_invoice_paid``, ``handle_invoice_payment_failed``) —
    the existing webhook-endpoint tests only verify dispatch, not the
    handlers themselves.
  - Idempotency via ``StripeWebhookEvent``

All tests mock Stripe API calls at the ``apps.billing.stripe_service``
boundary so no network traffic is generated.

URL prefix
----------
``apps.billing.urls`` is mounted at ``/api/billing/`` (alias of
``/api/v1/billing/``) — see ``backend/config/urls.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone as dt_tz
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.billing import webhook_handlers
from apps.billing.models import (
    PaymentHistory,
    StripeWebhookEvent,
    SubscriptionPlan,
    TenantSubscription,
)

pytestmark = pytest.mark.django_db

BILLING = "/api/billing"


# ===========================================================================
# Plan / subscription fixtures (scoped to this module)
# ===========================================================================


@pytest.fixture
def plan_pro(db):
    return SubscriptionPlan.objects.create(
        name="Professional",
        plan_code="PRO",
        description="Pro plan",
        price_monthly_cents=9900,
        price_yearly_cents=99000,
        currency="usd",
        stripe_product_id="prod_pro",
        stripe_price_monthly_id="price_pro_month",
        stripe_price_yearly_id="price_pro_year",
        is_active=True,
        sort_order=2,
    )


@pytest.fixture
def plan_free(db):
    return SubscriptionPlan.objects.create(
        name="Free",
        plan_code="FREE",
        price_monthly_cents=0,
        price_yearly_cents=0,
        is_active=True,
        sort_order=0,
    )


@pytest.fixture
def plan_enterprise(db):
    return SubscriptionPlan.objects.create(
        name="Enterprise",
        plan_code="ENTERPRISE",
        stripe_price_monthly_id="",  # Custom pricing → no price IDs
        stripe_price_yearly_id="",
        is_active=True,
        is_custom_pricing=True,
        sort_order=3,
    )


@pytest.fixture
def plan_inactive(db):
    return SubscriptionPlan.objects.create(
        name="Legacy",
        plan_code="LEGACY",
        is_active=False,
        sort_order=9,
    )


@pytest.fixture
def subscription_active(db, tenant, plan_pro):
    tenant.stripe_customer_id = "cus_tenant_a"
    tenant.save(update_fields=["stripe_customer_id"])
    return TenantSubscription.objects.create(
        tenant=tenant,
        plan=plan_pro,
        stripe_customer_id="cus_tenant_a",
        stripe_subscription_id="sub_active_a",
        status="active",
        billing_interval="month",
        current_period_start=timezone.now(),
        current_period_end=timezone.now(),
    )


@pytest.fixture
def subscription_for_b(db, tenant_b, plan_pro):
    tenant_b.stripe_customer_id = "cus_tenant_b"
    tenant_b.save(update_fields=["stripe_customer_id"])
    return TenantSubscription.objects.create(
        tenant=tenant_b,
        plan=plan_pro,
        stripe_customer_id="cus_tenant_b",
        stripe_subscription_id="sub_active_b",
        status="active",
        billing_interval="year",
    )


# ===========================================================================
# 1. plan_list (public)
# ===========================================================================


class TestPlanList:
    URL = f"{BILLING}/plans/"

    def test_unauthenticated_can_list_plans(
        self, api_client, plan_pro, plan_free
    ):
        """The endpoint is AllowAny — no auth required."""
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        codes = {p["plan_code"] for p in resp.data["results"]}
        assert codes == {"PRO", "FREE"}

    def test_inactive_plans_are_excluded(
        self, api_client, plan_pro, plan_inactive
    ):
        resp = api_client.get(self.URL)
        assert resp.status_code == 200
        codes = {p["plan_code"] for p in resp.data["results"]}
        assert "LEGACY" not in codes
        assert "PRO" in codes

    def test_plans_are_ordered_by_sort_order(
        self, api_client, plan_pro, plan_free, plan_enterprise
    ):
        """sort_order: FREE=0, PRO=2, ENTERPRISE=3."""
        resp = api_client.get(self.URL)
        codes = [p["plan_code"] for p in resp.data["results"]]
        assert codes == ["FREE", "PRO", "ENTERPRISE"]


# ===========================================================================
# 2. subscription_detail (admin-only, tenant-scoped)
# ===========================================================================


class TestSubscriptionDetail:
    URL = f"{BILLING}/subscription/"

    def test_requires_auth(self, api_client, tenant):
        api_client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
        resp = api_client.get(self.URL)
        assert resp.status_code == 401

    def test_teacher_forbidden(self, teacher_client):
        resp = teacher_client.get(self.URL)
        assert resp.status_code == 403

    def test_admin_with_subscription_returns_200(
        self, admin_client, subscription_active
    ):
        resp = admin_client.get(self.URL)
        assert resp.status_code == 200
        assert resp.data["status"] == "active"
        assert resp.data["plan"]["plan_code"] == "PRO"
        assert resp.data["billing_interval"] == "month"

    def test_admin_without_subscription_returns_404(self, admin_client):
        resp = admin_client.get(self.URL)
        assert resp.status_code == 404
        assert "detail" in resp.data

    def test_cross_tenant_isolation(
        self,
        api_client_for,
        admin_user,
        tenant,
        subscription_active,      # belongs to tenant A
        subscription_for_b,       # belongs to tenant B
    ):
        """Admin of tenant A sees ONLY A's subscription — never B's."""
        client = api_client_for(admin_user, tenant)
        resp = client.get(self.URL)
        assert resp.status_code == 200
        assert resp.data["stripe_customer_id"] == "cus_tenant_a"
        assert resp.data["stripe_customer_id"] != "cus_tenant_b"


# ===========================================================================
# 3. create_checkout (admin-only)
# ===========================================================================


ALLOWED_SUCCESS = "https://test.lms.com/success"
ALLOWED_CANCEL = "https://test.lms.com/cancel"


class TestCreateCheckout:
    URL = f"{BILLING}/checkout/"

    def _payload(self, plan, success=ALLOWED_SUCCESS, cancel=ALLOWED_CANCEL,
                 interval="month"):
        return {
            "plan_id": str(plan.id),
            "interval": interval,
            "success_url": success,
            "cancel_url": cancel,
        }

    def test_teacher_forbidden(self, teacher_client, plan_pro):
        resp = teacher_client.post(
            self.URL, self._payload(plan_pro), format="json"
        )
        assert resp.status_code == 403

    def test_unauthenticated_unauthorized(self, api_client, tenant, plan_pro):
        api_client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
        resp = api_client.post(
            self.URL, self._payload(plan_pro), format="json"
        )
        assert resp.status_code == 401

    def test_enterprise_plan_rejected(
        self, admin_client, plan_enterprise
    ):
        resp = admin_client.post(
            self.URL, self._payload(plan_enterprise), format="json"
        )
        assert resp.status_code == 400
        assert "sales" in str(resp.data).lower()

    def test_inactive_plan_returns_404(self, admin_client, plan_inactive):
        resp = admin_client.post(
            self.URL, self._payload(plan_inactive), format="json"
        )
        assert resp.status_code == 404

    def test_unknown_plan_returns_404(self, admin_client):
        resp = admin_client.post(
            self.URL,
            {
                "plan_id": str(uuid4()),
                "interval": "month",
                "success_url": ALLOWED_SUCCESS,
                "cancel_url": ALLOWED_CANCEL,
            },
            format="json",
        )
        assert resp.status_code == 404

    def test_foreign_success_url_rejected(self, admin_client, plan_pro):
        resp = admin_client.post(
            self.URL,
            self._payload(plan_pro, success="https://attacker.example/oops"),
            format="json",
        )
        assert resp.status_code == 400
        assert "success_url" in str(resp.data)

    def test_foreign_cancel_url_rejected(self, admin_client, plan_pro):
        resp = admin_client.post(
            self.URL,
            self._payload(plan_pro, cancel="https://evil.example/cancel"),
            format="json",
        )
        assert resp.status_code == 400
        assert "cancel_url" in str(resp.data)

    def test_happy_path_returns_checkout_url(self, admin_client, plan_pro):
        with mock.patch(
            "apps.billing.stripe_service.create_checkout_session",
            return_value="https://checkout.stripe.com/c/abc",
        ) as mock_create:
            resp = admin_client.post(
                self.URL, self._payload(plan_pro), format="json"
            )
        assert resp.status_code == 201
        assert resp.data["checkout_url"] == "https://checkout.stripe.com/c/abc"
        assert mock_create.call_count == 1
        kwargs = mock_create.call_args.kwargs
        assert kwargs["interval"] == "month"
        assert kwargs["success_url"] == ALLOWED_SUCCESS
        assert kwargs["plan"].plan_code == "PRO"

    def test_stripe_failure_returns_400(self, admin_client, plan_pro):
        with mock.patch(
            "apps.billing.stripe_service.create_checkout_session",
            side_effect=RuntimeError("Stripe down"),
        ):
            resp = admin_client.post(
                self.URL, self._payload(plan_pro), format="json"
            )
        assert resp.status_code == 400
        assert "Stripe down" in str(resp.data)


# ===========================================================================
# 4. create_portal (admin-only)
# ===========================================================================


class TestCreatePortal:
    URL = f"{BILLING}/portal/"

    def test_teacher_forbidden(self, teacher_client):
        resp = teacher_client.post(
            self.URL, {"return_url": ALLOWED_SUCCESS}, format="json"
        )
        assert resp.status_code == 403

    def test_foreign_return_url_rejected(self, admin_client):
        resp = admin_client.post(
            self.URL,
            {"return_url": "https://attacker.example/portal"},
            format="json",
        )
        assert resp.status_code == 400
        assert "return_url" in str(resp.data)

    def test_happy_path(self, admin_client):
        with mock.patch(
            "apps.billing.stripe_service.create_portal_session",
            return_value="https://billing.stripe.com/portal/xyz",
        ) as mock_create:
            resp = admin_client.post(
                self.URL,
                {"return_url": ALLOWED_SUCCESS},
                format="json",
            )
        assert resp.status_code == 200
        assert resp.data["portal_url"] == (
            "https://billing.stripe.com/portal/xyz"
        )
        assert mock_create.call_count == 1

    def test_default_return_url_allowed_when_omitted_in_debug(
        self, admin_client, settings
    ):
        """When return_url omitted, server uses request.build_absolute_uri,
        which emits http://... in tests.  The URL guard accepts http only
        when DEBUG=True, so this path is exercised under DEBUG=True."""
        settings.DEBUG = True
        with mock.patch(
            "apps.billing.stripe_service.create_portal_session",
            return_value="https://billing.stripe.com/portal/default",
        ):
            resp = admin_client.post(self.URL, {}, format="json")
        assert resp.status_code == 200

    def test_stripe_failure_returns_400(self, admin_client):
        with mock.patch(
            "apps.billing.stripe_service.create_portal_session",
            side_effect=RuntimeError("Stripe portal unavailable"),
        ):
            resp = admin_client.post(
                self.URL,
                {"return_url": ALLOWED_SUCCESS},
                format="json",
            )
        assert resp.status_code == 400
        assert "Stripe portal unavailable" in str(resp.data)


# ===========================================================================
# 5. payment_history
# ===========================================================================


class TestPaymentHistory:
    URL = f"{BILLING}/payments/"

    def test_teacher_forbidden(self, teacher_client):
        resp = teacher_client.get(self.URL)
        assert resp.status_code == 403

    def test_returns_tenant_payments_only(
        self,
        admin_client,
        tenant,
        tenant_b,
        subscription_active,
        subscription_for_b,
    ):
        """Cross-tenant isolation for payment history."""
        PaymentHistory.objects.create(
            tenant=tenant,
            subscription=subscription_active,
            stripe_invoice_id="in_tenant_a_1",
            amount_cents=1000,
            currency="usd",
            status="paid",
        )
        PaymentHistory.objects.create(
            tenant=tenant_b,
            subscription=subscription_for_b,
            stripe_invoice_id="in_tenant_b_1",
            amount_cents=2000,
            currency="usd",
            status="paid",
        )

        resp = admin_client.get(self.URL)
        assert resp.status_code == 200
        # Paginated response has 'results'
        results = resp.data.get("results", resp.data)
        if isinstance(results, dict):
            results = results.get("results", [])
        ids = {r["id"] for r in results}
        # Tenant A sees only its own invoice
        amounts = {r["amount_cents"] for r in results}
        assert 1000 in amounts
        assert 2000 not in amounts


# ===========================================================================
# 6. preview_plan_change
# ===========================================================================


class TestPreviewPlanChange:
    URL = f"{BILLING}/preview-change/"

    def test_teacher_forbidden(self, teacher_client, plan_pro):
        resp = teacher_client.post(
            self.URL,
            {"plan_id": str(plan_pro.id), "interval": "month"},
            format="json",
        )
        assert resp.status_code == 403

    def test_happy_path(self, admin_client, plan_pro, subscription_active):
        with mock.patch(
            "apps.billing.stripe_service.preview_plan_change",
            return_value={
                "prorated_amount_cents": 2500,
                "next_billing_date": 1900000000,
                "new_plan_name": "Professional",
            },
        ) as mock_preview:
            resp = admin_client.post(
                self.URL,
                {"plan_id": str(plan_pro.id), "interval": "month"},
                format="json",
            )
        assert resp.status_code == 200
        assert resp.data["prorated_amount_cents"] == 2500
        assert resp.data["new_plan"]["plan_code"] == "PRO"
        assert mock_preview.call_count == 1

    def test_stripe_error_returns_400(
        self, admin_client, plan_pro, subscription_active
    ):
        with mock.patch(
            "apps.billing.stripe_service.preview_plan_change",
            side_effect=ValueError("No active subscription"),
        ):
            resp = admin_client.post(
                self.URL,
                {"plan_id": str(plan_pro.id), "interval": "month"},
                format="json",
            )
        assert resp.status_code == 400


# ===========================================================================
# Helpers for webhook-handler tests
# ===========================================================================


def _now_ts() -> int:
    return int(datetime.now(tz=dt_tz.utc).timestamp())


def _make_event(event_type, event_id, obj):
    """Build a minimal Stripe-event-like object (attr access)."""
    event = SimpleNamespace()
    event.id = event_id
    event.type = event_type
    event.data = SimpleNamespace(object=obj)
    return event


def _make_checkout_session(tenant_id, plan_code, customer="cus_hook",
                           subscription="sub_hook", billing_interval=None):
    """Build a minimal Stripe checkout-session-like object.

    ``billing_interval`` mirrors the metadata key written by
    ``create_checkout_session()`` (TASK-022).  Pass ``None`` (default) to
    simulate sessions created *before* that deploy — the handler must fall
    back gracefully to ``'month'`` in that case.
    """
    metadata = {"tenant_id": str(tenant_id), "plan_code": plan_code}
    if billing_interval is not None:
        metadata["billing_interval"] = billing_interval
    return SimpleNamespace(
        id="cs_test_1",
        customer=customer,
        subscription=subscription,
        metadata=metadata,
    )


def _make_stripe_subscription(
    sub_id="sub_xyz",
    customer="cus_tenant_a",
    status="active",
    tenant_id=None,
    plan_code=None,
    price_id="price_pro_month",
    interval="month",
    cancel_at_period_end=False,
    canceled_at=None,
    trial_start=None,
    trial_end=None,
):
    """Build a dict-like object supporting BOTH ``obj['items']['data']`` AND
    attribute access, matching what the handler does."""
    now = _now_ts()

    class StripeObj(dict):
        def __getattr__(self, key):
            try:
                return self[key]
            except KeyError as exc:
                raise AttributeError(key) from exc

    price = StripeObj(id=price_id, recurring=StripeObj(interval=interval))
    item = StripeObj(id="si_1", price=price)
    items = StripeObj(data=[item])
    metadata = {}
    if tenant_id is not None:
        metadata["tenant_id"] = str(tenant_id)
    if plan_code is not None:
        metadata["plan_code"] = plan_code

    obj = StripeObj(
        id=sub_id,
        customer=customer,
        status=status,
        items=items,
        metadata=metadata,
        current_period_start=now,
        current_period_end=now + 86400 * 30,
        cancel_at_period_end=cancel_at_period_end,
        canceled_at=canceled_at,
        trial_start=trial_start,
        trial_end=trial_end,
    )
    return obj


def _make_invoice(
    invoice_id="in_test_1",
    customer="cus_tenant_a",
    amount_paid=9900,
    amount_due=9900,
    currency="usd",
    hosted_invoice_url="https://stripe.com/inv/1",
    invoice_pdf="https://stripe.com/inv/1.pdf",
    payment_intent="pi_1",
    charge="ch_1",
    number="INV-001",
    description="",
):
    return SimpleNamespace(
        id=invoice_id,
        customer=customer,
        amount_paid=amount_paid,
        amount_due=amount_due,
        currency=currency,
        hosted_invoice_url=hosted_invoice_url,
        invoice_pdf=invoice_pdf,
        payment_intent=payment_intent,
        charge=charge,
        number=number,
        description=description,
        period_start=_now_ts(),
        period_end=_now_ts() + 86400 * 30,
    )


# ===========================================================================
# 7. handle_checkout_session_completed
# ===========================================================================


class TestHandleCheckoutSessionCompleted:
    def test_creates_subscription_and_marks_trial_false(
        self, db, tenant, plan_pro
    ):
        tenant.is_trial = True
        tenant.save(update_fields=["is_trial"])

        session = _make_checkout_session(
            tenant_id=tenant.id,
            plan_code="PRO",
            customer="cus_new_123",
            subscription="sub_new_123",
        )
        event = _make_event(
            "checkout.session.completed", "evt_cs_1", session
        )

        webhook_handlers.handle_checkout_session_completed(event)

        tenant.refresh_from_db()
        assert tenant.stripe_customer_id == "cus_new_123"
        assert tenant.is_trial is False
        assert tenant.plan == "PRO"  # apply_plan_preset called

        ts = TenantSubscription.objects.get(tenant=tenant)
        assert ts.stripe_subscription_id == "sub_new_123"
        assert ts.plan_id == plan_pro.id
        assert ts.status == "active"

        # Idempotency record
        assert StripeWebhookEvent.objects.filter(
            stripe_event_id="evt_cs_1"
        ).exists()

    def test_idempotent_skips_second_call(self, db, tenant, plan_pro):
        session = _make_checkout_session(tenant.id, "PRO")
        event = _make_event("checkout.session.completed", "evt_dupe", session)

        webhook_handlers.handle_checkout_session_completed(event)
        # Second call — must not raise & must not create 2 rows
        webhook_handlers.handle_checkout_session_completed(event)

        assert (
            StripeWebhookEvent.objects.filter(
                stripe_event_id="evt_dupe"
            ).count()
            == 1
        )
        assert TenantSubscription.objects.filter(tenant=tenant).count() == 1

    def test_missing_metadata_logs_and_records_error(self, db):
        """metadata without tenant_id / plan_code → recorded as error."""
        session = SimpleNamespace(
            id="cs_bad", customer="cus_x", subscription="sub_x", metadata={}
        )
        event = _make_event(
            "checkout.session.completed", "evt_missing_meta", session
        )

        webhook_handlers.handle_checkout_session_completed(event)

        rec = StripeWebhookEvent.objects.get(
            stripe_event_id="evt_missing_meta"
        )
        assert "error" in rec.payload_summary

    def test_unknown_tenant_is_recorded(self, db, plan_pro):
        session = _make_checkout_session(
            tenant_id=uuid4(), plan_code="PRO"  # no such tenant
        )
        event = _make_event(
            "checkout.session.completed", "evt_no_tenant", session
        )

        webhook_handlers.handle_checkout_session_completed(event)

        rec = StripeWebhookEvent.objects.get(stripe_event_id="evt_no_tenant")
        assert "error" in rec.payload_summary

    def test_unknown_plan_is_recorded(self, db, tenant):
        """No SubscriptionPlan row with plan_code=GHOST."""
        session = _make_checkout_session(tenant.id, "GHOST")
        event = _make_event(
            "checkout.session.completed", "evt_no_plan", session
        )

        webhook_handlers.handle_checkout_session_completed(event)

        rec = StripeWebhookEvent.objects.get(stripe_event_id="evt_no_plan")
        assert "error" in rec.payload_summary
        assert not TenantSubscription.objects.filter(tenant=tenant).exists()

    # -----------------------------------------------------------------------
    # TASK-022 regression: billing_interval derived from session metadata
    # -----------------------------------------------------------------------

    def test_yearly_checkout_sets_billing_interval_year(
        self, db, tenant, plan_pro
    ):
        """checkout.session.completed with billing_interval='year' in metadata
        must create TenantSubscription with billing_interval='year'.

        Regression guard for TASK-022 Finding 1: previously the handler
        hard-coded billing_interval='month' regardless of the actual plan
        purchased — yearly subscriptions appeared as monthly in the admin UI
        until the next subscription.updated event arrived.
        """
        session = _make_checkout_session(
            tenant_id=tenant.id,
            plan_code="PRO",
            customer="cus_yearly_1",
            subscription="sub_yearly_1",
            billing_interval="year",
        )
        event = _make_event(
            "checkout.session.completed", "evt_yearly_checkout", session
        )

        webhook_handlers.handle_checkout_session_completed(event)

        ts = TenantSubscription.objects.get(tenant=tenant)
        assert ts.billing_interval == "year", (
            "Yearly checkout session should produce billing_interval='year' "
            "immediately, not wait for subscription.updated."
        )

    def test_checkout_without_billing_interval_metadata_defaults_to_month(
        self, db, tenant, plan_pro
    ):
        """Sessions created before TASK-022 have no billing_interval key in
        metadata.  The handler must fall back gracefully to 'month' — the
        value is corrected later by subscription.created/updated."""
        session = _make_checkout_session(
            tenant_id=tenant.id,
            plan_code="PRO",
            customer="cus_legacy_1",
            subscription="sub_legacy_1",
            billing_interval=None,  # omitted — pre-TASK-022 session
        )
        event = _make_event(
            "checkout.session.completed", "evt_legacy_checkout", session
        )

        webhook_handlers.handle_checkout_session_completed(event)

        ts = TenantSubscription.objects.get(tenant=tenant)
        assert ts.billing_interval == "month"

    def test_invalid_billing_interval_in_metadata_falls_back_to_month(
        self, db, tenant, plan_pro
    ):
        """billing_interval values other than 'month' / 'year' are guarded
        against: the handler must clamp them to 'month'."""
        session = _make_checkout_session(
            tenant_id=tenant.id,
            plan_code="PRO",
            customer="cus_bad_interval",
            subscription="sub_bad_interval",
            billing_interval="quarterly",  # unexpected / future value
        )
        event = _make_event(
            "checkout.session.completed", "evt_bad_interval", session
        )

        webhook_handlers.handle_checkout_session_completed(event)

        ts = TenantSubscription.objects.get(tenant=tenant)
        assert ts.billing_interval == "month"


# ===========================================================================
# 8. handle_subscription_created / .updated (shared _sync_subscription)
# ===========================================================================


class TestHandleSubscriptionLifecycle:
    def test_created_syncs_subscription(self, db, tenant, plan_pro):
        tenant.stripe_customer_id = "cus_tenant_a"
        tenant.save(update_fields=["stripe_customer_id"])

        stripe_sub = _make_stripe_subscription(
            sub_id="sub_created_1",
            customer="cus_tenant_a",
            status="active",
            tenant_id=tenant.id,
            plan_code="PRO",
        )
        event = _make_event(
            "customer.subscription.created", "evt_created_1", stripe_sub
        )

        webhook_handlers.handle_subscription_created(event)

        ts = TenantSubscription.objects.get(tenant=tenant)
        assert ts.stripe_subscription_id == "sub_created_1"
        assert ts.status == "active"
        assert ts.billing_interval == "month"
        assert ts.plan_id == plan_pro.id

    def test_updated_changes_status_to_past_due(
        self, db, tenant, plan_pro, subscription_active
    ):
        """customer.subscription.updated → status transitions to past_due."""
        stripe_sub = _make_stripe_subscription(
            sub_id=subscription_active.stripe_subscription_id,
            customer="cus_tenant_a",
            status="past_due",
            tenant_id=tenant.id,
            plan_code="PRO",
        )
        event = _make_event(
            "customer.subscription.updated", "evt_updated_1", stripe_sub
        )

        webhook_handlers.handle_subscription_updated(event)

        subscription_active.refresh_from_db()
        assert subscription_active.status == "past_due"

    def test_updated_trialing_state_populates_trial_fields(
        self, db, tenant, plan_pro
    ):
        tenant.stripe_customer_id = "cus_tenant_a"
        tenant.save(update_fields=["stripe_customer_id"])

        trial_start = _now_ts()
        trial_end = trial_start + 86400 * 14
        stripe_sub = _make_stripe_subscription(
            sub_id="sub_trialing",
            customer="cus_tenant_a",
            status="trialing",
            tenant_id=tenant.id,
            plan_code="PRO",
            trial_start=trial_start,
            trial_end=trial_end,
        )
        event = _make_event(
            "customer.subscription.updated", "evt_trial", stripe_sub
        )

        webhook_handlers.handle_subscription_updated(event)

        ts = TenantSubscription.objects.get(tenant=tenant)
        assert ts.status == "trialing"
        assert ts.trial_start is not None
        assert ts.trial_end is not None

    def test_updated_yearly_interval_from_price(self, db, tenant, plan_pro):
        tenant.stripe_customer_id = "cus_tenant_a"
        tenant.save(update_fields=["stripe_customer_id"])

        stripe_sub = _make_stripe_subscription(
            sub_id="sub_yearly",
            customer="cus_tenant_a",
            status="active",
            tenant_id=tenant.id,
            plan_code="PRO",
            price_id="price_pro_year",
            interval="year",
        )
        event = _make_event(
            "customer.subscription.updated", "evt_yearly", stripe_sub
        )

        webhook_handlers.handle_subscription_updated(event)

        ts = TenantSubscription.objects.get(tenant=tenant)
        assert ts.billing_interval == "year"

    def test_created_resolves_plan_via_price_id_when_no_metadata(
        self, db, tenant, plan_pro
    ):
        """If metadata lacks plan_code, handler falls back to matching the
        Stripe price ID against SubscriptionPlan.stripe_price_*."""
        tenant.stripe_customer_id = "cus_tenant_a"
        tenant.save(update_fields=["stripe_customer_id"])

        stripe_sub = _make_stripe_subscription(
            sub_id="sub_by_price",
            customer="cus_tenant_a",
            status="active",
            tenant_id=tenant.id,
            plan_code=None,  # no plan_code in metadata
            price_id="price_pro_year",
            interval="year",
        )
        event = _make_event(
            "customer.subscription.created", "evt_by_price", stripe_sub
        )

        webhook_handlers.handle_subscription_created(event)

        ts = TenantSubscription.objects.get(tenant=tenant)
        assert ts.plan_id == plan_pro.id

    def test_created_without_tenant_metadata_resolves_via_customer_id(
        self, db, tenant, plan_pro
    ):
        """Fallback lookup path: when metadata has no tenant_id the handler
        finds the tenant via stripe_customer_id."""
        tenant.stripe_customer_id = "cus_tenant_a"
        tenant.save(update_fields=["stripe_customer_id"])

        stripe_sub = _make_stripe_subscription(
            sub_id="sub_no_meta",
            customer="cus_tenant_a",
            status="active",
            tenant_id=None,
            plan_code="PRO",
        )
        event = _make_event(
            "customer.subscription.created", "evt_no_meta", stripe_sub
        )

        webhook_handlers.handle_subscription_created(event)

        ts = TenantSubscription.objects.get(tenant=tenant)
        assert ts.stripe_subscription_id == "sub_no_meta"

    def test_created_unknown_tenant_records_error(self, db, plan_pro):
        """No matching tenant_id and no matching stripe_customer_id."""
        stripe_sub = _make_stripe_subscription(
            sub_id="sub_orphan",
            customer="cus_unknown_xyz",
            status="active",
            tenant_id=None,
            plan_code="PRO",
        )
        event = _make_event(
            "customer.subscription.created", "evt_orphan", stripe_sub
        )

        webhook_handlers.handle_subscription_created(event)

        rec = StripeWebhookEvent.objects.get(stripe_event_id="evt_orphan")
        assert "error" in rec.payload_summary

    def test_idempotency_subscription_updated(
        self, db, tenant, plan_pro, subscription_active
    ):
        stripe_sub = _make_stripe_subscription(
            sub_id=subscription_active.stripe_subscription_id,
            customer="cus_tenant_a",
            status="past_due",
            tenant_id=tenant.id,
            plan_code="PRO",
        )
        event = _make_event(
            "customer.subscription.updated", "evt_dupe_upd", stripe_sub
        )

        webhook_handlers.handle_subscription_updated(event)
        webhook_handlers.handle_subscription_updated(event)

        assert (
            StripeWebhookEvent.objects.filter(
                stripe_event_id="evt_dupe_upd"
            ).count()
            == 1
        )


# ===========================================================================
# 9. handle_subscription_deleted
# ===========================================================================


class TestHandleSubscriptionDeleted:
    def test_marks_canceled_and_downgrades_to_free(
        self, db, tenant, plan_pro, plan_free, subscription_active
    ):
        tenant.plan = "PRO"
        tenant.save(update_fields=["plan"])

        stripe_sub = SimpleNamespace(
            id=subscription_active.stripe_subscription_id
        )
        event = _make_event(
            "customer.subscription.deleted", "evt_del_1", stripe_sub
        )

        webhook_handlers.handle_subscription_deleted(event)

        subscription_active.refresh_from_db()
        assert subscription_active.status == "canceled"
        assert subscription_active.canceled_at is not None

        tenant.refresh_from_db()
        assert tenant.plan == "FREE"

    def test_unknown_subscription_id_records_error(self, db):
        stripe_sub = SimpleNamespace(id="sub_does_not_exist")
        event = _make_event(
            "customer.subscription.deleted", "evt_del_missing", stripe_sub
        )

        webhook_handlers.handle_subscription_deleted(event)

        rec = StripeWebhookEvent.objects.get(
            stripe_event_id="evt_del_missing"
        )
        assert "error" in rec.payload_summary


# ===========================================================================
# 10. handle_invoice_paid
# ===========================================================================


class TestHandleInvoicePaid:
    def test_records_payment_history(
        self, db, tenant, plan_pro, subscription_active
    ):
        invoice = _make_invoice(
            invoice_id="in_paid_1",
            customer="cus_tenant_a",
            amount_paid=9900,
        )
        event = _make_event("invoice.paid", "evt_paid_1", invoice)

        webhook_handlers.handle_invoice_paid(event)

        ph = PaymentHistory.objects.get(stripe_invoice_id="in_paid_1")
        assert ph.tenant_id == tenant.id
        assert ph.amount_cents == 9900
        assert ph.status == "paid"
        assert ph.subscription_id == subscription_active.id

    def test_no_tenant_for_customer_records_error(self, db):
        invoice = _make_invoice(
            invoice_id="in_orphan", customer="cus_no_tenant"
        )
        event = _make_event("invoice.paid", "evt_orphan_inv", invoice)

        webhook_handlers.handle_invoice_paid(event)

        rec = StripeWebhookEvent.objects.get(stripe_event_id="evt_orphan_inv")
        assert "error" in rec.payload_summary
        assert not PaymentHistory.objects.filter(
            stripe_invoice_id="in_orphan"
        ).exists()

    def test_idempotent_update_same_invoice(
        self, db, tenant, plan_pro, subscription_active
    ):
        """Second call for same invoice updates in place — no duplicate."""
        invoice = _make_invoice(
            invoice_id="in_dupe", customer="cus_tenant_a", amount_paid=1000
        )
        event = _make_event("invoice.paid", "evt_dupe_paid", invoice)

        webhook_handlers.handle_invoice_paid(event)
        webhook_handlers.handle_invoice_paid(event)  # idempotent

        assert (
            PaymentHistory.objects.filter(
                stripe_invoice_id="in_dupe"
            ).count()
            == 1
        )


# ===========================================================================
# 11. handle_invoice_payment_failed
# ===========================================================================


class TestHandleInvoicePaymentFailed:
    def test_records_failed_payment_with_failure_reason(
        self, db, tenant, plan_pro, subscription_active
    ):
        invoice = _make_invoice(
            invoice_id="in_fail_1",
            customer="cus_tenant_a",
            amount_due=9900,
            charge="ch_failed_1",
        )
        event = _make_event(
            "invoice.payment_failed", "evt_fail_1", invoice
        )

        mock_charge = SimpleNamespace(
            failure_message="Your card was declined.",
            outcome=SimpleNamespace(seller_message=""),
        )

        with mock.patch(
            "apps.billing.stripe_service._get_stripe"
        ) as mock_stripe:
            mock_stripe.return_value.Charge.retrieve.return_value = (
                mock_charge
            )
            webhook_handlers.handle_invoice_payment_failed(event)

        ph = PaymentHistory.objects.get(stripe_invoice_id="in_fail_1")
        assert ph.status == "failed"
        assert ph.amount_cents == 9900
        assert "declined" in ph.failure_reason

    def test_failure_without_charge_leaves_reason_blank(
        self, db, tenant, plan_pro, subscription_active
    ):
        invoice = _make_invoice(
            invoice_id="in_fail_nocharge",
            customer="cus_tenant_a",
            charge="",
        )
        event = _make_event(
            "invoice.payment_failed", "evt_fail_nocharge", invoice
        )

        webhook_handlers.handle_invoice_payment_failed(event)

        ph = PaymentHistory.objects.get(
            stripe_invoice_id="in_fail_nocharge"
        )
        assert ph.status == "failed"
        assert ph.failure_reason == ""

    def test_unknown_customer_records_error(self, db):
        invoice = _make_invoice(
            invoice_id="in_fail_orphan", customer="cus_no_tenant"
        )
        event = _make_event(
            "invoice.payment_failed", "evt_fail_orphan", invoice
        )

        webhook_handlers.handle_invoice_payment_failed(event)

        rec = StripeWebhookEvent.objects.get(
            stripe_event_id="evt_fail_orphan"
        )
        assert "error" in rec.payload_summary
        assert not PaymentHistory.objects.filter(
            stripe_invoice_id="in_fail_orphan"
        ).exists()


# ===========================================================================
# 12. Idempotency record-keeping helper
# ===========================================================================


class TestIdempotencyTracking:
    def test_already_processed_true_after_record(self, db):
        from apps.billing.webhook_handlers import (
            _already_processed,
            _record_event,
        )

        assert _already_processed("evt_track_1") is False
        _record_event("evt_track_1", "customer.subscription.created")
        assert _already_processed("evt_track_1") is True

    def test_record_event_stores_payload_summary(self, db):
        from apps.billing.webhook_handlers import _record_event

        _record_event(
            "evt_track_2",
            "invoice.paid",
            summary={"tenant_id": "abc", "amount": 9900},
        )
        rec = StripeWebhookEvent.objects.get(stripe_event_id="evt_track_2")
        assert rec.event_type == "invoice.paid"
        assert rec.payload_summary == {"tenant_id": "abc", "amount": 9900}
