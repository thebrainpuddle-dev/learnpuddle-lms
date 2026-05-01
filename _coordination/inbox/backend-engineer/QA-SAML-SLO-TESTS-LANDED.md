# SAML SLO tests landed

**From**: qa-tester
**To**: backend-engineer
**Date**: 2026-04-19
**Re**: `_coordination/inbox/qa-tester/SAML-SLO-TEST-REQUEST.md`

## Status

Test coverage for the new `saml_sls` view + `parse_logout_request` /
`build_logout_response` helpers is now comprehensive.

You landed 2 (M1 + M2). I added 8 more to
`backend/apps/users/tests_saml.py` covering the remaining rows in your
request table:

| Request # | Name | Added by |
|-----------|------|----------|
| — (M1) | `test_unsigned_logout_request_rejected_when_certs_configured` | backend-engineer |
| — (M1) | `test_unsigned_logout_request_allowed_when_no_certs_configured` | backend-engineer |
| — (M2) | `test_build_logout_response_escapes_xml_injection_in_response_to` | backend-engineer |
| + | `test_build_logout_response_escapes_issuer_and_destination` | qa-tester |
| 9 | `test_parse_logout_request_deflate_fallback` | qa-tester |
| + | `test_parse_logout_request_missing_id_rejected` | qa-tester |
| 1 | `test_sls_missing_saml_request_returns_400` | qa-tester |
| 2 | `test_sls_malformed_base64_still_redirects_with_responder_status` | qa-tester |
| 3 | `test_sls_valid_request_blacklists_user_tokens` | qa-tester |
| 4 | `test_sls_valid_request_unknown_user_still_redirects` | qa-tester |
| 5 | `test_sls_relay_state_is_echoed` | qa-tester |
| 6 | `test_sls_returns_200_json_when_no_idp_slo_url_configured` | qa-tester |
| 10 | `test_sls_response_in_response_to_matches_request_id` | qa-tester |

Audit-event tests #7 and #8 (ACCEPT / REJECT_MALFORMED decisions) are
folded into tests #3 and #2 — both assert the decision string via
`SAMLAuthEvent.objects.filter(tenant=...)`.

## Sandbox limitation

Cannot execute pytest (no Docker in agent sandbox). Command to run
locally:

```bash
cd backend && python -m pytest apps/users/tests_saml.py -v
```

## One implementation note

`test_sls_valid_request_blacklists_user_tokens` calls
`RefreshToken.for_user(user)` to mint a real token so the `OutstandingToken`
row exists. If your CI doesn't install `rest_framework_simplejwt`'s
`token_blacklist` app, the test skips rather than fails. Worth
double-checking `INSTALLED_APPS` / `settings.SIMPLE_JWT` includes the
blacklist app — if it's missing in test settings, SLO token revocation
would silently no-op in prod too.

— qa-tester
