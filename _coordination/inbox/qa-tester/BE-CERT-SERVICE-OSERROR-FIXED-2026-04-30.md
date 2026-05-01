# Cert OSError leak — fixed (your test inverts)

**From:** backend-engineer
**To:** qa-tester
**Date:** 2026-04-30

---

The P2 bug you filed in
`_coordination/inbox/backend-engineer/CERT-SERVICE-DOCBUILD-OSERROR-LEAK-2026-04-30.md`
is fixed. Took **Option A** as you recommended: pre-validate the logo path
with `os.path.isfile()` before constructing `Image(...)`, so `doc.build`
never sees a stale path. A warning is logged on skip
(`"certificate logo skipped: file_missing path=... tenant=..."`). The
inner try/except is retained as defense-in-depth and now logs instead of
swallowing silently. Happy-path behavior is unchanged.

## Test flip — heads up

Your `test_with_invalid_logo_path_raises_oserror` (which correctly pinned
the broken behavior with `pytest.raises(OSError)`) has been **inverted**
to `test_with_invalid_logo_path_skips_gracefully`. It now asserts the
function returns a valid PDF (`BytesIO`, seeked to 0, `%PDF-` magic
bytes) AND that a warning record with `"certificate logo skipped"` +
`"file_missing"` was emitted via `caplog`.

All 29 tests in `tests/progress/test_certificate_service.py` pass:

```
.............................                                           [100%]
29 passed in 1.09s
```

Review request sent to reviewer at
`_coordination/inbox/reviewer/BE-CERT-SERVICE-LOGO-PREVAL-2026-04-30.md`.

— backend-engineer
