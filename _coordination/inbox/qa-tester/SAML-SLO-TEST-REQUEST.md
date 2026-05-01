# Test Request: SAML SLO (Single Logout) Implementation

**From:** backend-engineer
**To:** qa-tester
**Date:** 2026-04-19
**Files changed:**
- `backend/apps/users/saml_service.py` — `parse_logout_request()`, `build_logout_response()`, `SAMLLogoutRequest`
- `backend/apps/users/saml_views.py` — `_invalidate_user_tokens()`, full `saml_sls()` view

**STATUS: PROCESSED 2026-04-19 by qa-tester.** Backend-engineer landed
two core tests (M1 unsigned-rejection + M2 XML-escape). I added 8 more
to `backend/apps/users/tests_saml.py` covering:

- `test_build_logout_response_escapes_issuer_and_destination` (escape
  defence-in-depth)
- `test_parse_logout_request_deflate_fallback` (HTTP-Redirect binding)
- `test_parse_logout_request_missing_id_rejected`
- `test_sls_missing_saml_request_returns_400`
- `test_sls_malformed_base64_still_redirects_with_responder_status`
- `test_sls_valid_request_blacklists_user_tokens` (token blacklist
  assertion per request spec test #3)
- `test_sls_valid_request_unknown_user_still_redirects`
- `test_sls_relay_state_is_echoed`
- `test_sls_returns_200_json_when_no_idp_slo_url_configured`
- `test_sls_response_in_response_to_matches_request_id`

10 new SLO tests total (2 landed by BE + 8 new by QA). Docker
unavailable in sandbox; see shared-log for the commands to run.


The SAML SLO endpoint at `POST /api/v1/auth/saml/<tenant>/sls/` was a no-op
placeholder.  It is now a full IdP-initiated SLO implementation.

---

## Tests needed (file: `backend/apps/users/tests_saml.py`)

There is an existing `tests_saml.py` — please add a `SAMLSLSViewTestCase` class.

### Helpers needed

You'll need factories / helpers for:
- A tenant with `features={"saml": True}`
- A `TenantSAMLConfig` with `idp_slo_url`, `idp_x509_certs`, `enabled=True`
- A `User` belonging to that tenant
- A helper to build a base64-encoded LogoutRequest XML string:

```python
import base64, zlib, uuid
from django.utils import timezone

def make_logout_request(name_id="user@example.com", signed=False):
    now = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    rid = f"id-{uuid.uuid4().hex}"
    xml = (
        f'<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        f'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{rid}" Version="2.0" IssueInstant="{now}">'
        f'<saml:Issuer>https://idp.example.com</saml:Issuer>'
        f'<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">'
        f'{name_id}</saml:NameID>'
        f'</samlp:LogoutRequest>'
    )
    return base64.b64encode(xml.encode("utf-8")).decode("ascii"), rid
```

### Test cases

| # | Name | Description |
|---|------|-------------|
| 1 | `test_sls_missing_saml_request` | POST with no `SAMLRequest` → 400 BAD_REQUEST |
| 2 | `test_sls_malformed_base64` | POST `SAMLRequest=notbase64!!!` → redirects to idp_slo_url with `Responder` status (view continues, doesn't 500) |
| 3 | `test_sls_valid_request_known_user` | Valid LogoutRequest with NameID of existing user → 302 redirect to `idp_slo_url`; user's outstanding tokens blacklisted |
| 4 | `test_sls_valid_request_unknown_user` | Valid LogoutRequest with unknown NameID → 302 redirect (no crash); no tokens blacklisted |
| 5 | `test_sls_relay_state_echoed` | POST with `RelayState=xyz` → redirect URL includes `RelayState=xyz` |
| 6 | `test_sls_no_idp_slo_url` | Config has blank `idp_slo_url` → 200 JSON `{"message": "Logout processed"}` |
| 7 | `test_sls_audit_event_accept` | Valid request → `SAMLAuthEvent` row with `decision="ACCEPT"` |
| 8 | `test_sls_audit_event_reject_on_parse_error` | Malformed request → `SAMLAuthEvent` row with `decision="REJECT_MALFORMED"` |
| 9 | `test_parse_logout_request_deflate_fallback` | Unit test for `parse_logout_request` with raw-deflate-compressed base64 |
| 10 | `test_build_logout_response_structure` | Unit test: `build_logout_response(...)` returns XML with correct `ID`, `InResponseTo`, `Destination`, `StatusCode` |

### Specific assertions for test 3

```python
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

# Issue a real refresh token for the user
token = RefreshToken.for_user(user)
# OutstandingToken row should now exist
assert OutstandingToken.objects.filter(user=user).exists()

# Call SLS
response = client.post(sls_url, {"SAMLRequest": saml_request_b64}, format="multipart")
assert response.status_code == 302

# Token should now be blacklisted
outstanding = OutstandingToken.objects.get(user=user)
assert BlacklistedToken.objects.filter(token=outstanding).exists()
```

### Notes
- `parse_logout_request` and `build_logout_response` are pure functions (no DB) —
  unit-test them directly, not through the HTTP layer.
- The SLS endpoint is CSRF-exempt so no CSRF token is needed in tests.
- The LogoutResponse in the redirect is raw-deflate + base64 + URL-encoded — to
  inspect the StatusCode in test 8, decode:
  ```python
  from urllib.parse import urlparse, parse_qs
  import base64, zlib
  loc = response["Location"]
  qs = parse_qs(urlparse(loc).query)
  xml = zlib.decompress(base64.b64decode(qs["SAMLResponse"][0]), -15).decode()
  assert "Responder" in xml
  ```
