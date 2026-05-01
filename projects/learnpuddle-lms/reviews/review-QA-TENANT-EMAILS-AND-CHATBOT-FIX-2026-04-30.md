---
tags: [review, qa/tenant-emails, qa/email-utils, qa/chatbot-decorator-fix, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: QA-TENANT-EMAILS-COVERAGE + QA-EMAIL-UTILS-COVERAGE + QA-CHATBOT-DECORATOR-FIX

## Verdict: APPROVE

## Summary

Three test-only changes, all correct against source. 19 new tests for
`apps/tenants/emails.py` (was 0% coverage), 30 new tests for
`apps/notifications/email_utils.py` (was 0% coverage), and the redundant
`@pytest.mark.django_db` decorator removed from `CreateKnowledgeForContentTestCase`
per prior reviewer note. No production code touched, no migrations, no behavioral risk.

## Verification Performed

### 1. `tests/tenants/test_tenant_emails.py` (NEW, 19 tests) ✅

Verified every assertion against `apps/tenants/emails.py`:

| Test | Assertion | Source line | OK? |
|------|-----------|-------------|-----|
| `test_skips_when_send_onboarding_email_is_false` | no `send_templated_email` call | L21–23 (`if not getattr(settings, "SEND_ONBOARDING_EMAIL", True)`) | ✅ |
| `test_subject_contains_platform_name` | `"LearnPuddle"` in subject | L31 (`f"Welcome to {platform_name}…"`) | ✅ |
| `test_context_first_name_fallback_when_empty` | `context["first_name"] == "there"` | L34 (`admin.first_name or "there"`) | ✅ |
| `test_uses_admin_welcome_template` | template == `"admin_welcome.html"` | L47 | ✅ |
| `test_email_failure_silenced_when_fail_silently_true` | no exception raised | L61–62 (`if not fail_silently: raise`) | ✅ |
| `test_email_failure_raises_when_fail_silently_false` | `OSError` propagates | same — inverse path | ✅ |
| `test_subject_plural_days_when_more_than_one` | `"7 days"` in subject | L74 (`f"…{days_left} day{'s' if days_left != 1 else ''}"`) | ✅ |
| `test_subject_singular_day_when_one_day_left` | `"1 day"` in, `"1 days"` not in | L74 plural guard | ✅ |
| `test_skips_when_no_active_admin` | no `send_templated_email` | L67–69 (`tenant.users.filter(role="SCHOOL_ADMIN", is_active=True).first()`; early return) | ✅ |
| `test_skips_when_admin_is_inactive` | filter excludes `is_active=False` | L67 (`is_active=True` filter) | ✅ |

The `assertNotIn("1 days", subject)` after `assertIn("1 day", subject)` is the
right shape — it catches the "1 days" regression that a naive `assertIn("1 day")`
alone would miss (since "1 day" is a substring of "1 days").

### 2. `tests/notifications/test_email_utils.py` (NEW, 30 tests) ✅

Verified every assertion against `apps/notifications/email_utils.py`:

| Suite | Tests | What it locks down |
|-------|-------|--------------------|
| `GetBaseSenderAddressTestCase` | 3 | `parseaddr` extraction (L21), platform-domain fallback (L24) |
| `BuildSchoolSenderEmailTestCase` | 5 | `notification_from_name > tenant.name > PLATFORM_NAME` precedence (L29–34) |
| `BuildTenantReplyToTestCase` | 4 | `notification_reply_to > tenant.email > []` chain (L40–45) |
| `BuildBucketHeadersTestCase` | 6 | All 4 headers, prefix precedence chain (L51–63) |
| `GetBaseContextTestCase` | 3 | `platform_name`, `platform_domain`, current `year` (L68–72) |
| `BuildTenantUrlTestCase` | 6 | Verified-custom-domain-only gate (L153), unverified ignored, subdomain build, path normalisation, default `/login` |
| `BuildLoginUrlTestCase` | 3 | Backward-compat wrapper via `_TenantProxy` (L165–172) |

Use of `SimpleNamespace` for tenant fakes is the right pattern — these are pure
functions that only read attributes, no DB access needed. The class-level
`@override_settings` is correct (Django supports it as both class and method
decorator on `TestCase` subclasses).

### 3. `apps/courses/tests_chatbot_auto_ingest.py` decorator fix ✅

Verified at L194: `class CreateKnowledgeForContentTestCase(TestCase):` — no
`@pytest.mark.django_db` above the class. Docstring at L199–200 correctly
explains why (`django.test.TestCase` wraps each test in a transaction
automatically). This matches Minor #1 from `REVIEW-VERDICTS-QA-BATCH-2026-04-29.md`.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

### m1 (non-blocking) — Use `SimpleTestCase` for pure-function suites

Several `TestCase` classes in `test_email_utils.py`
(`GetBaseSenderAddressTestCase`, `BuildSchoolSenderEmailTestCase`,
`BuildTenantReplyToTestCase`, `BuildBucketHeadersTestCase`,
`GetBaseContextTestCase`, `BuildTenantUrlTestCase`, `BuildLoginUrlTestCase`)
use `SimpleNamespace` tenant fakes and never touch the DB. Switching them to
`django.test.SimpleTestCase` would:

- Run faster (no transaction wrap/rollback per test)
- Fail loudly if a future maintainer accidentally adds DB code (`SimpleTestCase`
  raises `DatabaseError` on any DB query)

The current `TestCase` works (it allows `override_settings`), so this is a polish
suggestion, not a blocker. The two `test_tenant_emails.py` suites correctly use
`TestCase` because they create real `Tenant` and `User` rows in `setUp`.

### m2 (non-blocking) — `_make_admin` ignores `first_name=""` sentinel

In `test_tenant_emails.py` lines 109–115, the test passes `first_name=""` to
`_make_admin`, then immediately overrides via `admin_no_name.first_name = ""` +
`save()`. The duplication suggests the author was unsure whether
`User.objects.create_user` accepts an empty `first_name`. It does, so the
explicit `.first_name = ""` + `.save()` is redundant. Drop the two lines for
clarity. Functionally harmless.

### m3 (informational) — `test_context_first_name_fallback_when_empty` doesn't cover `None`

The source uses `admin.first_name or "there"` (truthiness fallback) — that catches
both `""` and `None`. The test only covers `""`. If `User.first_name` could ever
be `None` (it can't with Django's default `CharField(blank=True)`, which
defaults to `""`), this would be a gap. Right now it isn't, so this is just an
FYI for any future field migration.

## Positive Observations

- **Coverage is closing real gaps.** Both `apps/tenants/emails.py` and
  `apps/notifications/email_utils.py` were 0% per `coverage.xml`. These suites
  bring both modules to near-full line coverage with behavior assertions, not
  smoke tests.
- **Tests follow the source contract carefully.** Every test traces to a
  specific source line, including the plural/singular guard, the verified
  custom-domain gate, and the fail-silently fork. The QA author's "Source
  contract verification" section in the review request was accurate to the
  letter.
- **Right mock seam.** Patching `apps.tenants.emails.send_templated_email`
  (the local re-import) rather than `apps.notifications.email_utils.send_templated_email`
  is correct — patching at the import site is the convention that resists future
  imports being shuffled.
- **Decorator fix is paired with an explanatory comment.** Future readers see
  *why* the decorator is missing, so it doesn't get re-added by reflex.
- **`SimpleNamespace` tenant fakes** keep `email_utils` tests fast and
  self-contained — no fixture coupling to the real `Tenant` model schema.

## Static-only verification caveat

Per the request, the QA author could not execute tests in this sandbox. I
verified file presence (`tests/tenants/test_tenant_emails.py`,
`tests/notifications/test_email_utils.py`), structural correctness, decorator
ordering, mock-target paths, and assertion alignment with source. All clean.
The author should run the suite once before relying on coverage gains:

```bash
docker compose exec web pytest tests/tenants/test_tenant_emails.py \
    tests/notifications/test_email_utils.py \
    apps/courses/tests_chatbot_auto_ingest.py -v
```

— lp-reviewer
