---
tags: [review, task/QA-coverage, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-19
---

# Review: QA new tests — billing open-redirect guard + decorator unit tests

## Verdict: APPROVE

## Summary

Two new pure-unit test files plugging real coverage gaps on security-
critical code:

1. `tests/billing/test_billing_redirect_url.py` — **36 tests** pinning
   the exact allow/deny boundary of
   `apps.billing.views._is_tenant_redirect_url_allowed` (the open-redirect
   guard for Stripe Checkout + Customer Portal return URLs). Previously
   0 direct test coverage on a function that must not regress.
2. `tests/test_decorators.py` — **45 tests** covering every public
   decorator in `utils/decorators.py` (the primary RBAC layer). Tested
   only indirectly before — now pinned role-by-role.

Both files are DB-free where possible (SimpleNamespace fixtures), use
`@override_settings` and `pytest.mark.django_db` only where genuinely
required, and pin current behaviour rather than aspirational. They are
exactly the kind of guardrail tests a principal would ask for on code
this security-sensitive.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### m1 (cosmetic) — Test counts in the handoff don't match file totals

Request claims "~52 tests" for billing + "~55 tests" for decorators.
`grep -c '    def test_'` shows **36** (billing) and **45** (decorators)
respectively. Coverage is strong either way — this is a note-keeping nit,
not a code issue. Worth syncing the tracking doc.

Breakdown I counted:

| File | Class | Tests |
|------|-------|-------|
| billing | Production mode | 25 |
| billing | Debug mode | 8 |
| billing | Cross-tenant isolation | 3 |
| decorators | TenantRequired | 6 |
| decorators | AdminOnly | 7 |
| decorators | SuperAdminOnly | 5 |
| decorators | TeacherOrAdmin | 7 |
| decorators | StudentOnly | 5 |
| decorators | StudentOrAdmin | 7 |
| decorators | CheckFeature | 8 |

### m2 (nit) — `test_url_with_credentials_denied` name contradicts its assertion

`test_billing_redirect_url.py:173-180`:

```python
def test_url_with_credentials_denied(self):
    ...
    assert _is_tenant_redirect_url_allowed(
        "https://user:pass@demo.learnpuddle.com/", TENANT
    ) is True  # hostname resolves correctly — not a bypass
```

The test body + docstring correctly explain that urlparse strips userinfo
and resolves `.hostname` to `demo.learnpuddle.com`, so the URL **is**
allowed. The test name says `_denied` which is the opposite. Rename to
`test_url_with_credentials_allowed_when_hostname_matches` (or
`_is_not_a_bypass`) to avoid confusion when someone greps for
"denied" tests during incident review.

Side note (not in scope for this PR): browsers honour user:pass@host
userinfo differently across vendors, and some phishing toolkits use it
to obscure the real host in the URL bar. Not changing test behaviour —
the guard correctly matches the hostname — but worth a backlog ticket
to **reject** userinfo entirely in `_is_tenant_redirect_url_allowed`
for defence-in-depth. File as a separate security hardening item; not
a blocker on this test PR.

### m3 (nit) — Missing coverage for `check_feature` bracket form

`utils/decorators.py:129-130` supports `features["saml"]` (bracket-and-
quote form). The three covered forms are `feature_X`, `X`, and
`features.X`. The bracket form is documented in the docstring but not
exercised. Add one test:

```python
def test_feature_allowed_via_bracket_form(self):
    result = self._call_with_tenant('features["certificates"]', True)
    assert result == "OK"
```

Note the `_make_tenant_with_feature` fixture's `short` derivation will
need to handle `features["X"]` → `X`; current code does
`.split(".")[-1]` which won't produce the right short name for the
bracket form. Small fixture tweak required. Not blocking — the
production code path is dead-simple parsing.

### m4 (nit) — `check_tenant_limit` decorator not covered

`utils/decorators.py:149-169` exposes `check_tenant_limit(resource_name)`
which calls `apps.tenants.services.check_limit`. Out of scope for this
PR (the request lists the covered decorators explicitly), but flagging
because it sits alongside the others and is an obvious gap. Could piggy-
back on the existing `TestCheckFeature` style with a mocked
`check_limit`. File as follow-up.

### m5 (nit) — `TestTenantRequired` tests use mixed styles for user construction

Some tests construct users via the shared `_user()` helper, others inline
`SimpleNamespace(role=..., is_authenticated=..., tenant_id=...)` (see
`test_passes_when_tenant_set_and_user_owns_tenant`,
`test_raises_for_cross_tenant_user`, etc.). The inline form is used
where the `tenant_id` must come from a DB-bound fixture — fine, but
the helper could accept an override (`_user(tenant_id=tenant.id)`)
and collapse both forms into one. Non-functional; readability polish.

## Positive Observations

### billing redirect guard

- **Attack-vector coverage is thoughtful** — tests explicitly name the
  common open-redirect bypasses:
  - suffix confusion (`demo.learnpuddle.com.evil.com`) → DENY
  - path confusion (`evil.com/demo.learnpuddle.com/`) → DENY
  - protocol smuggling (data:, ftp:) → DENY
  - credentials masking (user:pass@host) → correctly resolves to host
  - empty custom_domain string → not matched
  Each attack is a test (not a comment), so a regression flips red.
- **Production vs. DEBUG parity tested separately** via
  `@override_settings` at the class level. Localhost/127.0.0.1 are
  denied in production, allowed in DEBUG — and each of those is a
  distinct test case.
- **Cross-tenant isolation** (3 tests) closes the loop: tenant A's own
  URL is correctly rejected when the request comes with tenant B's
  context. Tenant A's verified custom domain is correctly NOT accepted
  by tenant B. This is the **actual** defence against the cross-tenant
  open-redirect scenario and it's explicitly pinned.
- **Edge inputs** (None, empty, int, list, whitespace-only, relative,
  scheme-less) all return False. Catches the class of bugs where the
  guard accidentally returns truthy for falsy inputs.
- **Zero DB dependency** — `SimpleNamespace` tenant + `@override_settings`.
  Fast. Runs anywhere.

### decorators unit tests

- **Sentinel view + direct call** pattern is clean: `view =
  decorator(_sentinel_view); view(request)`. No DRF HTTP overhead. Each
  test reduces to "given (role, authenticated?), does the decorator
  return 'OK' or raise?"
- **Every role is individually tested** against every role-gated
  decorator. Easy to audit — if someone silently drops `HOD` from
  `teacher_or_admin`'s allowed list, `test_hod_allowed` flips red
  immediately.
- **Error messages are matched with regex** (`match="Admin access
  required"`, `match="Authentication required"`, etc.). If a future
  change swaps the exception message but not the behaviour, at least
  one test surfaces the drift.
- **`tenant_required` cross-tenant isolation is the star test**:
  `test_raises_for_cross_tenant_user` pins the scenario where a user
  from tenant A tries to reach tenant B's context. This is the exact
  class of bug `BUG_tenant_me_cross_tenant.md` patched — now locked.
- **SUPER_ADMIN bypass is tested** explicitly — an important asymmetry
  that's easy to break accidentally.
- **`check_feature` fixture is engineered to exercise both branches**
  (BooleanField attr vs. features dict) by setting both on the
  SimpleNamespace tenant. The three name forms (prefix, short, dotted)
  all resolve correctly and are asserted. The 403 payload shape
  (`upgrade_required`, `feature`) is also pinned — front-end relies on
  that contract.
- **Clear docstrings on each class** describing the decorator's
  contract — these tests double as living documentation.
- **Proper fixture use**: `TestTenantRequired` uses `@pytest.mark.
  django_db` because it needs real `tenant.id` values for comparison,
  but every other class is pure Python and runs without Django DB.
  Right split.
- **`setup_method` / `teardown_method` clear the contextvars** so
  cross-test state doesn't leak. Correct defensive hygiene for the
  thread-local tenant pattern.
- **`# noqa: ARG001`** on the sentinel view's unused `request` param
  shows linter-aware code. Small but indicative.

## Verification

Tests not run in this sandbox (Docker/pytest unavailable). Before merge
/ in CI:

```bash
docker compose exec web pytest \
  tests/billing/test_billing_redirect_url.py \
  tests/test_decorators.py -v
```

Expect: 81 tests pass (36 + 45). If a test fails, it's a real regression
in either `_is_tenant_redirect_url_allowed` or the decorators — both
files pin **current** behaviour and were written against the existing
implementation.

## Recommended follow-ups (post-merge, non-blocking)

1. Fix the `test_url_with_credentials_denied` misnomer (m2).
2. Add one test for the `features["X"]` bracket form (m3).
3. File a follow-up ticket for `check_tenant_limit` coverage (m4).
4. File a hardening ticket: reject URLs with userinfo in
   `_is_tenant_redirect_url_allowed` (defence-in-depth against
   phishing-UX bypass, m2 side note).

## Also addressed in this batch

Per the request note, the qa-tester also landed the cosmetic nits from
`REVIEW-VERDICT-NEW-TESTS-2026-04-19` (M1/M2):
- Rename `test_tenant_isolation_separate_teachers` →
  `test_attempt_number_is_per_teacher` and drop the unused `tenant_b`
  fixture parameter.
- Remove unused `from unittest import mock`, unused `Tenant` import,
  and the shadow `User` import inside a test body.

Both are tidy, diff-only changes — no review surface to speak of.

— lp-reviewer
