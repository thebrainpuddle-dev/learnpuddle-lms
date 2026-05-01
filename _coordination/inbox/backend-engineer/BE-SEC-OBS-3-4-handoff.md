# Handoff: Two non-blocking items from backend-security MAIC audit

**From**: backend-security
**To**: backend-engineer
**Date**: 2026-04-19
**Severity**: Medium / Low — not security bugs, code-hygiene follow-ups
**Context**: proactive MAIC audit after Phase-1 P0 signoff. Full findings in
  `_coordination/shared-log.md`.

Both items are outside my file ownership
(`backend/apps/courses/image_service.py` and
`backend/apps/billing/webhook_views.py` belong to you). Flagging for a
follow-up ticket at your convenience.

---

## OBS-3 — Tempfile leak on error path in `image_service.py` (Medium)

`backend/apps/courses/image_service.py` around line 323 uses
`tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)` to stage image
bytes before `default_storage.save()`. The `os.remove(tmp_path)` cleanup
only runs on the happy path; an exception raised by `default_storage.save()`
(S3 timeout, disk full, permission error) leaves `/tmp/*.jpg` fragments
accumulating.

Suggested pattern:

```python
try:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as f:
            if default_storage.exists(storage_key):
                default_storage.delete(storage_key)
            default_storage.save(storage_key, f)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
except Exception:
    logger.exception("image_service: failed to persist generated image")
    raise
```

Not a security issue on its own — just disk hygiene. Worth batching with
any other `image_service.py` change.

---

## OBS-4 — Stripe webhook exception granularity (Low)

`backend/apps/billing/webhook_views.py` around lines 48-59 catches all
exceptions from `construct_webhook_event` and returns HTTP 400. This
conflates signature-verification failure (genuinely a 400/401) with code-
path bugs (should be 500 so Stripe retries).

Suggested split:

```python
try:
    event = construct_webhook_event(payload, sig_header)
except ValueError as e:
    logger.warning("Invalid Stripe webhook signature: %s", e)
    return Response({"error": "Invalid signature"},
                    status=status.HTTP_401_UNAUTHORIZED)
except Exception as e:
    logger.exception("Stripe webhook processing error: %s", e)
    return Response({"error": "Internal error"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
```

Benefit: Stripe's delivery dashboard shows "401" for real tamper / rotation
problems vs "500" that Stripe will auto-retry — easier on-call triage.

Not a security regression. Stripe's own retry-on-5xx behaviour is the main
win. Defer until next billing-adjacent change.

---

## No commits made

Per agent policy, backend-security never commits. Reporting findings only;
you own the fix and commit flow for both files.
