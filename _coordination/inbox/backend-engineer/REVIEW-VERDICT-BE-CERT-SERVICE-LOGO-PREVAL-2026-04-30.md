# Review Verdict — Certificate logo pre-validation (OSError leak fix)

**From:** lp-reviewer
**To:** backend-engineer
**Date:** 2026-04-30
**Re:** `_coordination/inbox/reviewer/BE-CERT-SERVICE-LOGO-PREVAL-2026-04-30.md`

---

## Verdict: **APPROVE**

The fix is correct, minimally invasive, well-commented, and the regression
test is precisely scoped. Tests pass cleanly (29/29 in 0.78s on this host).
No blocking findings.

---

## Verified fixes

| Claim | Status | Evidence |
|---|---|---|
| `os.path.isfile()` guard runs BEFORE `Image(...)` | ✅ verified | `certificate_service.py:159` (check) precedes `:161` (`Image(...)`) |
| Missing logo → fully skipped, never reaches `doc.build` | ✅ verified | When `isfile` is False the `else` branch only logs; nothing is appended to `elements`. `doc.build(elements)` at `:212` therefore never sees the bad path. |
| Module-level `logger` added | ✅ verified | `certificate_service.py:10` (`import logging`), `:24` (`logger = logging.getLogger(__name__)`) |
| Structured warning includes `path=` and tenant identifier | ✅ verified | `:172-176` emits `"certificate logo skipped: file_missing path=%s tenant=%s"` with `tenant_logo_path` and `tenant_name`. (See nit below re: `tenant_name` vs `tenant_id`.) |
| Inner try/except retained, now logs (no silent swallow) | ✅ verified | `:165-170` — `except Exception` now calls `logger.warning("...image_load_failed path=%s tenant=%s", ...)` instead of `pass`. |
| Test inverted to `test_with_invalid_logo_path_skips_gracefully` | ✅ verified | `test_certificate_service.py:229-259`. Asserts `BytesIO`, position 0, `%PDF-` magic, AND a warning whose message contains both `certificate logo skipped` AND `file_missing`. |
| Caller signature unchanged | ✅ verified | `teacher_views.py:934-942` still calls with the same kwargs; `tenant_logo_path` is `None` or a `str` from `tenant.logo.path` (`:923-929`). |
| 29/29 tests pass | ✅ reproduced locally | `.venv/bin/pytest tests/progress/test_certificate_service.py -q --reuse-db` → `29 passed in 0.78s` |

---

## Findings

### Blocking
None.

### Should-fix
None.

### Nits (non-blocking, optional follow-ups)

1. **Warning carries `tenant_name`, not `tenant_id`.** The review brief asked
   for "`tenant_id` (or equivalent useful identifier)" — `tenant_name` is an
   equivalent useful identifier and is what the function already has in
   scope, so this satisfies the contract. If you want stricter ops-grep
   semantics later (names can collide / be renamed), `tenant_id` would be
   marginally better, but that would mean threading a new arg through the
   sole caller. Not worth changing for this fix.

2. **TOCTOU window is real but harmless here.** Between
   `os.path.isfile(tenant_logo_path)` returning True and `Image(...)`
   actually opening the file inside `doc.build`, the file could in theory
   be deleted, surfacing the original `OSError`. In practice this code
   reads tenant logos that aren't deleted mid-request, so the inner
   try/except is sufficient defense-in-depth — but note that the inner
   block only wraps the `Image(...)` constructor + `elements.append`, NOT
   the later `doc.build` call. Since ReportLab defers the open to build
   time (the whole reason for this fix), a TOCTOU race would still escape
   the inner guard and 500 the request. Acceptable risk for now;
   long-term, if this ever becomes flaky in prod, the right fix is to
   `open(path, "rb")` once up-front and pass the file handle / BytesIO to
   `Image(...)`. Logging only.

3. **Permission errors (`EACCES` on a file that exists but is unreadable).**
   `os.path.isfile()` returns True for a file you can't read. ReportLab's
   later open will raise `PermissionError` from inside `doc.build` and
   escape the inner try/except (same reason as the original bug). Same
   acceptable-risk note as #2 — production tenant logos under
   `media/tenant/{id}/` should always be readable by the worker user, and
   this hasn't been observed in prod. Mention only for completeness.

4. **`os.path.isfile("")` and `os.path.isfile(None)`.** Verified locally:
   `isfile("")` → `False` (safe, falls through to warning), `isfile(None)`
   → `TypeError`. The outer `if tenant_logo_path:` guard at `:158` is
   falsy for both `None` and `""`, so neither value reaches `os.path.isfile`.
   Caller (`teacher_views.py:923-929`) only ever passes `None` or a real
   string path. Safe.

5. **The "logo present → identical rendering" claim.** The happy path is
   structurally unchanged — same `Image(...)` call, same `hAlign`, same
   `Spacer`, same append order. No visual diff expected. The existing
   `test_pdf_is_landscape_a4` and `test_buffer_has_non_zero_size` cover
   the structure smoke-check.

---

## Verification evidence

```
$ cd backend && .venv/bin/pytest tests/progress/test_certificate_service.py -q --reuse-db
.............................                                           [100%]
29 passed in 0.78s
```

Static review confirmed:
- `certificate_service.py` lines 158-176 implement the documented control flow.
- Lines 151-157 contain the explanatory comment requested in the writeup,
  warning future readers not to "simplify" the pre-check back into a
  try/except wrapper around `doc.build`. Good.
- Test `:229-259` pins both the success outcome (PDF bytes) AND the
  branch-specific reason string (`file_missing`), so a regression that
  routes through a different warning path (e.g. `image_load_failed`)
  would NOT pass — no false-positive risk.
- Sole caller `teacher_views.py:934-942` is untouched; `tenant_logo_path`
  argument continues to be `Optional[str]`.

---

— lp-reviewer
