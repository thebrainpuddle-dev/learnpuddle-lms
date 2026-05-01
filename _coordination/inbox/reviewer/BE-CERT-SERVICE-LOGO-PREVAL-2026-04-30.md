# Review Request — Certificate logo pre-validation (OSError leak fix)

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-30
**Severity:** P2 fix (graceful-degradation gap closed)

---

## Context

QA-tester filed a production bug:
`_coordination/inbox/backend-engineer/CERT-SERVICE-DOCBUILD-OSERROR-LEAK-2026-04-30.md`

`apps/progress/certificate_service.py::generate_certificate_pdf` *intended*
to silently skip a bad tenant logo, but the existing try/except only wrapped
the `Image(...)` constructor. ReportLab's constructor stores the path
without opening the file; the OS open happens later inside
`doc.build(elements)`, which sat outside any guard. A tenant with a stale
`tenant_logo_path` (deleted file, broken symlink, etc.) thus got a 500 on
every certificate render.

## Production change

**File:** `backend/apps/progress/certificate_service.py`

1. Lines 9-22: added `import logging`, `import os`, and a module-level
   `logger = logging.getLogger(__name__)`.
2. Lines 146-172 (formerly 145-153): chose **Option A** from the bug report
   — pre-validate the path with `os.path.isfile()` BEFORE handing it to
   `Image(...)`. If the file is missing, log a warning and skip the logo
   entirely (it never reaches `doc.build`). The inner try/except is kept
   defensively for image-load issues that survive the existence check (e.g.
   permissions / corrupt header) and now logs a warning instead of swallowing
   silently.
3. Added an explanatory comment immediately above the new check noting
   *why* this is pre-validation and not a try/except wrapping `doc.build`
   (so a future reader doesn't "simplify" it back to the bug).

Why not Option B (wrap `doc.build` in try/except)? It's blunter — would
mask any unrelated PDF emission failure. The bug report explicitly
preferred A; this fix takes that path.

Happy-path behavior (valid logo, no logo, all other parameters) is
unchanged.

## Test change

**File:** `backend/tests/progress/test_certificate_service.py`

Inverted the test that previously pinned the broken behavior:

- **Old:** `test_with_invalid_logo_path_raises_oserror` — asserted
  `pytest.raises(OSError)`.
- **New:** `test_with_invalid_logo_path_skips_gracefully` — uses
  `caplog.at_level(WARNING, logger="apps.progress.certificate_service")`
  to assert that:
  1. The function returns a `BytesIO` seeked to 0 with the `%PDF-` magic
     header (PDF was produced despite the bad logo).
  2. A warning record was emitted whose message contains both
     `"certificate logo skipped"` and `"file_missing"`.

No other tests in the file needed updating; all 28 sibling tests are
unchanged and still cover hex_to_rgb, get_certificate_filename, and the
happy paths of generate_certificate_pdf.

## Verification

```
cd backend && .venv/bin/pytest tests/progress/test_certificate_service.py -q --reuse-db
.............................                                           [100%]
29 passed in 1.09s
```

29/29 pass, including the inverted regression test.

## Files touched

- `backend/apps/progress/certificate_service.py` (production)
- `backend/tests/progress/test_certificate_service.py` (test)

No other call sites needed changes. `apps/progress/teacher_views.py:934`
imports and calls `generate_certificate_pdf` with the same signature.

— backend-engineer
