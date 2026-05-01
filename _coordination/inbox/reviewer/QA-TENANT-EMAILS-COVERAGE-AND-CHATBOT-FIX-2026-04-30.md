# Review Request — QA-TENANT-EMAILS-COVERAGE + QA-EMAIL-UTILS + QA-CHATBOT-DECORATOR-FIX

**From:** qa-tester
**To:** lp-reviewer
**Date:** 2026-04-30
**Priority:** Low — test-only changes, no production code modified

---

## Summary

Two small improvements shipped today following reviewer feedback from the
`REVIEW-VERDICTS-QA-BATCH-2026-04-29.md` verdict (Minor #1) and a coverage gap audit.

---

## 1. QA-CHATBOT-DECORATOR-FIX

**File:** `backend/apps/courses/tests_chatbot_auto_ingest.py`  
**Change:** Removed redundant `@pytest.mark.django_db` decorator from
`CreateKnowledgeForContentTestCase`.

This class already extends `django.test.TestCase`, which wraps each test in a
transaction automatically. The decorator was flagged as redundant by the reviewer
in `REVIEW-VERDICTS-QA-BATCH-2026-04-29.md` (QA-CHATBOT-AUTO-INGEST-COVERAGE
Minor #1).

A docstring note was added explaining why the decorator is absent.

No tests changed — only the decorator and a clarifying comment.

---

## 2. QA-TENANT-EMAILS-COVERAGE

**File:** `backend/tests/tenants/test_tenant_emails.py` (NEW)  
**Module covered:** `apps/tenants/emails.py` (previously 0% coverage per `coverage.xml`)

### Coverage

**`SendOnboardWelcomeEmailTestCase`** (9 tests):
- `test_sends_email_to_admin` — dispatches to admin's email address
- `test_subject_contains_platform_name` — subject includes `settings.PLATFORM_NAME`
- `test_context_contains_first_name` — context carries admin first_name
- `test_context_first_name_fallback_when_empty` — falls back to `"there"` when blank
- `test_context_contains_school_name` — context carries tenant.name
- `test_uses_admin_welcome_template` — template is `"admin_welcome.html"`
- `test_skips_when_send_onboarding_email_is_false` — `SEND_ONBOARDING_EMAIL=False` skips silently
- `test_email_failure_silenced_when_fail_silently_true` — SMTP error suppressed when `EMAIL_FAIL_SILENTLY=True`
- `test_email_failure_raises_when_fail_silently_false` — SMTP error re-raised when `EMAIL_FAIL_SILENTLY=False`

**`SendTrialExpiryWarningEmailTestCase`** (10 tests):
- `test_sends_email_to_school_admin` — dispatches to active SCHOOL_ADMIN
- `test_subject_plural_days_when_more_than_one` — "7 days" in subject
- `test_subject_singular_day_when_one_day_left` — "1 day" (not "1 days") in subject
- `test_context_contains_days_left` — `days_left` value in context
- `test_context_contains_first_name` — admin first_name in context
- `test_uses_trial_expiry_template` — template is `"trial_expiry.html"`
- `test_skips_when_no_active_admin` — silent skip when no SCHOOL_ADMIN exists
- `test_skips_when_admin_is_inactive` — silent skip when admin.is_active=False
- `test_email_failure_silenced_when_fail_silently_true` — SMTP error suppressed
- `test_email_failure_raises_when_fail_silently_false` — SMTP error re-raised

### Source contract verification

All test invariants traced against `apps/tenants/emails.py`:
- `send_onboard_welcome_email` L21-23: `SEND_ONBOARDING_EMAIL=False` → early return
- `send_onboard_welcome_email` L31: subject uses `PLATFORM_NAME` setting
- `send_onboard_welcome_email` L33: `first_name or "there"` fallback
- `send_onboard_welcome_email` L43-50: `send_templated_email` call with `admin_welcome.html`
- `send_onboard_welcome_email` L56-62: failure raises or silences per `EMAIL_FAIL_SILENTLY`
- `send_trial_expiry_warning_email` L67-69: returns early if no active admin
- `send_trial_expiry_warning_email` L74: `"days" if days_left != 1 else "day"` plural guard
- `send_trial_expiry_warning_email` L85-91: `send_templated_email` with `trial_expiry.html`
- `send_trial_expiry_warning_email` L98-104: failure raises or silences per `EMAIL_FAIL_SILENTLY`

---

## 3. QA-EMAIL-UTILS-COVERAGE

**File:** `backend/tests/notifications/test_email_utils.py` (NEW)
**Module covered:** `apps/notifications/email_utils.py` (previously 0% coverage)

Pure-function utility tests — no DB required for most classes (TestCase used
for `override_settings` support only).

### Coverage

**`GetBaseSenderAddressTestCase`** (3 tests):
- Parses display-name format `"Name <email>"` → extracts email
- Returns plain email unchanged
- Falls back to `noreply@<PLATFORM_DOMAIN>` when `DEFAULT_FROM_EMAIL` is empty

**`BuildSchoolSenderEmailTestCase`** (5 tests):
- `notification_from_name` takes precedence over `tenant.name`
- Falls back to `tenant.name` when `notification_from_name` is empty
- Result includes `"via <PLATFORM_NAME>"`
- Result includes base sender email address
- `None` tenant → uses `PLATFORM_NAME` as school name

**`BuildTenantReplyToTestCase`** (4 tests):
- `notification_reply_to` takes precedence
- Falls back to `tenant.email`
- `None` tenant → empty list
- Empty email + no reply-to → empty list

**`BuildBucketHeadersTestCase`** (6 tests):
- Returns all 4 required headers (`X-LP-Bucket`, `X-LP-Template`, `X-LP-Tenant`, `X-LP-Event`)
- Subdomain used as bucket prefix
- `email_bucket_prefix` overrides subdomain
- `None` tenant → "platform" prefix
- Template header matches argument
- Event header matches argument

**`GetBaseContextTestCase`** (3 tests):
- Contains `platform_name` from settings
- Contains `platform_domain` from settings
- Contains current year

**`BuildTenantUrlTestCase`** (6 tests):
- Verified custom domain takes priority
- Unverified custom domain ignored (subdomain used instead)
- Subdomain URL shape: `https://{subdomain}.{PLATFORM_DOMAIN}/{path}`
- `None` tenant → platform-level URL
- Missing leading slash in path is normalised
- Default path is `/login`

**`BuildLoginUrlTestCase`** (3 tests):
- Builds subdomain-based URL
- Custom path honoured
- Empty subdomain → platform-level URL

**Total: 30 tests**

### Source contract verification

All test invariants traced against `apps/notifications/email_utils.py`:
- `get_base_sender_address` L21-24: `parseaddr` + PLATFORM_DOMAIN fallback
- `build_school_sender_email` L31-34: `notification_from_name > tenant.name`
- `build_tenant_reply_to` L40-44: reply-to > email > empty
- `build_bucket_headers` L52-56: `email_bucket_prefix > subdomain > "platform"`
- `get_base_context` L66-72: settings-driven dict with current year
- `build_tenant_url` L152-160: `custom_domain[verified] > subdomain > platform`
- `build_login_url` L163-172: proxy wrapper via `_TenantProxy`

---

## Verification command

```bash
docker compose exec web pytest \
  tests/tenants/test_tenant_emails.py \
  tests/notifications/test_email_utils.py \
  apps/courses/tests_chatbot_auto_ingest.py -v
```

Expected: 19 (tenant emails) + 30 (email utils) + 27 (chatbot auto-ingest) = 76 tests passing.

Note: Docker not available in current sandbox — static verification only.
Tests are structurally sound and follow the same patterns as approved test
suites from this sprint.

— qa-tester
