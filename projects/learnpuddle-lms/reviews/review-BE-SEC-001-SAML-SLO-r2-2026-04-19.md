---
tags: [review, task/BE-SEC-001, task/SAML-SLO, verdict/approve, reviewer/lp-reviewer, round/2]
created: 2026-04-19
---

# Review: BE-SEC-001 tenant_me + SAML SLO M1/M2 (Round 2)

## Verdict: APPROVE

All three fixes land correctly. The `@permission_classes([IsAuthenticated])`
sweep claim (51 files, all correctly scoped) holds up on spot-check. No
outstanding issues.

---

## BE-SEC-001 — `tenant_me_view` cross-tenant isolation (RESOLVED)

`backend/apps/tenants/views.py:100-109`:

```python
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@tenant_required
def tenant_me_view(request):
    tenant = request.tenant
    ...
```

`@tenant_required` is in place. The previous `getattr(..., "tenant", None)
or get_tenant_from_request(...)` fallback is gone — the decorator now
ensures a cross-tenant call (user in tenant A hitting subdomain B) is
rejected at the decorator level before the view body runs.

### Sweep verification

The claim of "51 files with `@permission_classes([IsAuthenticated])`, all
tenant-scoped" is accurate. I spot-checked via a multi-line Grep for the
exact anti-pattern — `@permission_classes` followed directly by `def`
with no guard decorator in between:

```
backend/apps/courses/maic_views.py:1510  @permission_classes([IsAuthenticated])
backend/apps/courses/maic_views.py:1511  def maic_list_voices(request):

backend/utils/media_views.py:56         @permission_classes([IsAuthenticated])
backend/utils/media_views.py:57         def protected_media_view(request, path):
```

Both are legitimate documented exceptions:

1. **`maic_list_voices`** (line 1507-1508 above the decorator):
   ```python
   # No @tenant_required: returns a static platform-wide list of Azure TTS
   # voice options; no tenant-scoped data accessed.
   ```
   Verified — the view only returns `AZURE_IN_VOICES` (module constant).
   No DB query, no `request.tenant` access.

2. **`protected_media_view`** — does inline tenant check at lines 74-83:
   extracts `path_tenant_id` from the URL, compares to
   `request.user.tenant_id`, raises `Http404` on mismatch. Super-admins
   bypass. This is the correct pattern for a file-serving view where the
   tenant is carried in the path rather than the Host header.

All other `@permission_classes([IsAuthenticated])` sites have one of:
`@tenant_required`, `@admin_only`, `@super_admin_only`, `@teacher_or_admin`,
`@student_or_admin`, `@student_only`, or `@check_feature` on the next
decorator line. Claim verified.

---

## SAML SLO M1 — Unsigned LogoutRequest rejected when certs configured (RESOLVED)

`backend/apps/users/saml_service.py:576-590`:

```python
sig = root.find("ds:Signature", NS)
normalized_certs = [_ensure_pem(c) for c in idp_certs_pem if c]
if normalized_certs:
    if sig is None:
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            "LogoutRequest is unsigned but IdP certificates are configured; "
            "unsigned requests are rejected when a trust anchor is present",
        )
    _verify_xml_signature(root, normalized_certs)
```

Correct logic. The comment on lines 576-580 explains the threat model
(SLS is `@csrf_exempt`, so without signature verification a third-party
page could force-logout users by cross-posting a forged LogoutRequest).
Good defensive documentation.

**When no certs configured** — unsigned request still accepted. This is
the right default ("secure by configuration") because some IdP deployments
legitimately don't sign SLO requests; if the operator hasn't loaded a
trust anchor we can't verify anyway.

### Test coverage

`backend/apps/users/tests_saml.py:688-715`:

- `test_unsigned_logout_request_rejected_when_certs_configured` — uses
  `_UNSIGNED_LOGOUT_REQUEST` + `[DUMMY_CERT]`, asserts
  `exc.value.code == "REJECT_SIGNATURE"`. ✓
- `test_unsigned_logout_request_allowed_when_no_certs_configured` — same
  payload, `idp_certs_pem=[]`, asserts parse succeeds and
  `result.name_id == "user@example.org"`. ✓

Both the positive and negative paths are covered. Docstrings capture the
rationale so future "simplify to always-require-signature" refactors
stop and think first.

---

## SAML SLO M2 — XML escaping in response + AuthnRequest (RESOLVED)

`saml_service.py:34`:

```python
from xml.sax.saxutils import escape as _xml_escape, quoteattr as _xml_quoteattr
```

`build_logout_response` (lines 634-649) now uses `_xml_quoteattr()` for
every attribute (`ID`, `IssueInstant`, `Destination`, `InResponseTo`,
`StatusCode/@Value`) and `_xml_escape()` for `<saml:Issuer>` text
content. `quoteattr()` both escapes special characters and wraps in
quotes — that's why the f-string no longer has the surrounding `"..."`.

`saml_views.py:219-228` — `saml_login` AuthnRequest also hardened:
`ID`, `IssueInstant`, `Destination`, `AssertionConsumerServiceURL`
all via `_xml_quoteattr()`, `<saml:Issuer>` via `_xml_escape()`. Comment
on lines 214-218 flags this as defence-in-depth (values are server-
controlled but a misconfigured URL with `&` would otherwise blow up the
request silently).

### Test coverage

`tests_saml.py:718-736`:

```python
injected_id = 'req-123"><injected/><x y="'
xml_str = build_logout_response(in_response_to=injected_id, ...)
root = ET.fromstring(xml_str)  # must be well-formed
assert root.get("InResponseTo") == injected_id  # recovered verbatim
```

Good test. Round-trips through `ET.fromstring` — if the escaping were
broken, either XML parsing would raise or the attribute round-trip would
lose characters. Exercises both failure modes in one assertion pair.

Minor gap (non-blocking): no test for `<saml:Issuer>` element escaping
via `_xml_escape`. Values there are server-controlled today so the
exposure is lower, but a follow-up test `test_build_logout_response_escapes_issuer`
with `issuer='sp-entity<script>'` would lock in the guarantee.

---

## OBS-3 + OBS-4 — already approved

Confirmed still in place:

- **OBS-3** (`image_service.py:322-336`) — inner `try/finally` ensures
  `os.remove(tmp_path)` runs even when `default_storage.save()` raises.
- **OBS-4** (`billing/webhook_views.py`) — three-clause exception split
  (`ValueError`/`SignatureVerificationError`/`Exception`) already
  approved in `review-BE-OBS4-SAML-SLO-2026-04-19.md`. No regression.

---

## Pytest caveat acknowledged

Tests can't execute in the agent sandbox (no Docker). Handing to
qa-tester for:

```
pytest backend/apps/users/tests_saml.py -k "logout or slo or build_logout" -v
pytest backend/tests/tenants/test_tenant_views.py::TenantMeViewTestCase::test_tenant_me_cross_tenant_denied -v
```

Test bodies read as correct — high confidence they pass.

---

## Positive observations

- The "no certs → allow unsigned" fallback is explicitly documented in
  the docstring and the code comment. This is the kind of security
  trade-off that future auditors will reach for — having the reasoning
  inline prevents a reflexive "tighten this" refactor that would break
  legitimate unsigned-SLO IdPs.
- `_xml_quoteattr` for attributes, `_xml_escape` for text — correct
  choice of primitive. `quoteattr()` includes the wrapping quotes, which
  is why the f-strings no longer have them; easy to miss in review but
  the `saml_views.py` and `saml_service.py` diffs both handle this
  correctly.
- The `51 files` sweep claim is the kind of assertion that's usually
  wrong — here it holds up. Good discipline.

---

## Action items

None blocking. Optional follow-up:

1. Add `test_build_logout_response_escapes_issuer` covering the
   `<saml:Issuer>` text-content escape path (symmetrical to the
   attribute test).
2. Flag the `# No @tenant_required` comment convention to agents as
   first-class: the sweep script would be more robust if a single-line
   regex could find these at the decorator site. Low priority —
   `grep -B5 "@permission_classes" | grep "No @tenant_required"`
   works today.
