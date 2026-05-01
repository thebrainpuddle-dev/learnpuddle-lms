# Production Bug — Certificate doc.build() OSError leaks past logo guard

**From:** qa-tester
**To:** backend-engineer
**Date:** 2026-04-30
**Severity:** P2 (graceful-degradation gap; user-facing 500 if a tenant has a stale logo path)

---

## Summary

`apps/progress/certificate_service.py::generate_certificate_pdf` is *intended*
to skip a missing/broken tenant logo silently — but the existing guard does
not actually catch the OSError that ReportLab raises. A tenant with a stale
or invalid `tenant_logo_path` will cause `generate_certificate_pdf(...)` to
raise `OSError: Cannot open resource '...'`, which propagates uncaught to the
caller (PDF download view / Celery task). The certificate cannot be issued
until the bad path is cleared.

## Repro

```python
from datetime import datetime
from apps.progress.certificate_service import generate_certificate_pdf

generate_certificate_pdf(
    teacher_name="Jane",
    course_title="Math",
    completion_date=datetime(2026, 3, 15),
    tenant_name="Acme",
    tenant_logo_path="/nonexistent/path/logo.png",
)
# → OSError: Cannot open resource "/nonexistent/path/logo.png"
```

The new test
`backend/tests/progress/test_certificate_service.py::TestGenerateCertificatePdf::test_with_invalid_logo_path_raises_oserror`
pins this current behavior with `pytest.raises(OSError)`.

## Root cause

`apps/progress/certificate_service.py:146-153`:

```python
if tenant_logo_path:
    try:
        logo = Image(tenant_logo_path, width=1.5*inch, height=1.5*inch)   # <-- guarded
        logo.hAlign = 'CENTER'
        elements.append(logo)
        elements.append(Spacer(1, 20))
    except Exception:
        pass  # Skip logo if there's an error loading it
```

ReportLab's `Image()` constructor only stores the path. It does not actually
open the file. The OS-level `open()` happens later inside
`apps/progress/certificate_service.py:189`:

```python
doc.build(elements)   # <-- NOT inside any try/except
```

So the OSError is raised from `doc.build`, outside the guard, and propagates.

## Suggested fix

Two reasonable options:

1. **Pre-validate the path** before constructing `Image`, e.g.
   ```python
   import os
   if tenant_logo_path and os.path.isfile(tenant_logo_path):
       try:
           logo = Image(tenant_logo_path, width=1.5*inch, height=1.5*inch)
           ...
       except Exception:
           pass
   ```
   Cheap, explicit, and matches the existing "skip on error" intent.

2. **Wrap `doc.build` in a fallback**: try once, if it raises an `OSError` /
   `IOError` related to a missing logo, drop the logo from `elements` and
   retry. More forgiving but more complex; risks masking unrelated build
   errors.

Option 1 is preferred — narrow, predictable, and easy to test.

## Test note

When this bug is fixed:

- Flip the assertion in
  `backend/tests/progress/test_certificate_service.py::TestGenerateCertificatePdf::test_with_invalid_logo_path_raises_oserror`
  to assert the PDF is produced (i.e. the `%PDF-` header check that the test
  originally claimed). Rename it to `test_with_invalid_logo_path_skips_gracefully`.
- Optionally add a separate test that verifies a *valid* logo path still
  embeds the image (would require a tiny PNG fixture in the test tree).

## References

- `apps/progress/certificate_service.py:146-153` — partial guard
- `apps/progress/certificate_service.py:189` — unguarded `doc.build`
- `backend/tests/progress/test_certificate_service.py::test_with_invalid_logo_path_raises_oserror` — current pinned behavior

— qa-tester
