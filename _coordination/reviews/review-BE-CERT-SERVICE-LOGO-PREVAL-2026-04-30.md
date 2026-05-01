---
tags: [review, task/BE-CERT-SERVICE-LOGO-PREVAL, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: BE-CERT-SERVICE-LOGO-PREVAL — Certificate logo pre-validation (OSError leak fix)

## Verdict: APPROVE

## Summary
Correct, minimal P2 fix. The bug — `Image(...)` defers the OS open to `doc.build()`, so a `try/except` around the constructor never caught the `OSError` — is precisely diagnosed and the fix lands at the right layer (pre-validate the path before ReportLab ever sees it). The inverted regression test pins the new behavior and the inline comment explains *why* this is pre-validation rather than a `try/except` wrapping `doc.build` so a future reader doesn't "simplify" the bug back in.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Defensive inner `try/except: Exception`** — `certificate_service.py:165-170` catches a bare `Exception` after the existence check. The comment in the request explains the intent (covers permissions / corrupt header that survive `os.path.isfile`), which is reasonable. A tighter catch on `(OSError, IOError, ValueError)` would be slightly more precise, but this is a defense-in-depth path that should never fire in practice. Non-blocking.

2. **Redundant `tenant=tenant_name` in the warning log fields.** Both branches (lines 167-170 and 172-176) include `tenant=%s` formatted into the log message rather than as `extra={...}` structured fields. Other logging in the codebase (`apps/webhooks/services.py`) uses the same f-string style, so this matches existing convention. If/when log structured-fields adoption lands, these are easy to migrate.

3. **`os.path.isfile` follows symlinks.** The bug report mentioned "broken symlinks" — `os.path.isfile` correctly returns `False` for a dangling symlink (it follows and the target doesn't exist), so this is fine. Just calling out that the chosen primitive matches the reported symptom.

## Positive Observations

- **Bug-cause explanation in code.** The comment at lines 151-157 explicitly documents that `Image()` defers the open and that a `try/except` around the constructor cannot catch the build-time `OSError`. This is the kind of comment that prevents the bug from re-occurring in 6 months when someone refactors the function.
- **Inverted regression test.** Replacing `pytest.raises(OSError)` with `caplog.at_level(WARNING) → assert "file_missing" in message` flips the test from pinning the bug to pinning the fix — the right move.
- **Warning emits structured-ish reason codes.** `"file_missing"` and `"image_load_failed"` distinguish the existence-check skip from the constructor-catch skip, which is useful for ops dashboards.
- **Module-level `logger` added correctly.** `logger = logging.getLogger(__name__)` at line 24 follows the standard pattern; no `print` statements, no broad swallowing.
- **Option A vs B explained.** The request explains why `os.path.isfile` pre-validation was chosen over wrapping `doc.build` in `try/except` (the latter masks unrelated PDF emission failures). Good engineering judgement.
- **Test-suite verification clean.** `29/29 pass` reported with `--reuse-db`, including the new inverted regression test. No sibling tests needed updating.
- **Single call site verified.** Author confirmed `apps/progress/teacher_views.py:934` is the only caller and the signature is unchanged.

## Notes for Author

The fix is approved as-is. If you do a pass over `apps/progress/certificate_service.py` later, consider also pre-validating any other file paths fed into ReportLab constructors (background images, custom font paths, etc.) — same class of bug if introduced.

— lp-reviewer
