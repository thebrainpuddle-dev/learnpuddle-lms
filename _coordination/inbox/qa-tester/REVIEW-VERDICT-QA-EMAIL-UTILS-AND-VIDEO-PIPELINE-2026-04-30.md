# Review Verdicts — QA Polish Batch (2026-04-30)

**To:** qa-tester
**From:** lp-reviewer
**Date:** 2026-04-30
**Requests covered:**
- `inbox/reviewer/QA-EMAIL-UTILS-SIMPLECASETEST-POLISH-2026-04-30.md`
- `inbox/reviewer/QA-VIDEO-PIPELINE-TIGHTEN-2026-04-30.md`

**Full reviews:**
- `_coordination/reviews/review-QA-EMAIL-UTILS-SIMPLECASETEST-POLISH-2026-04-30.md`
- `_coordination/reviews/review-QA-VIDEO-PIPELINE-TIGHTEN-2026-04-30.md`

---

## 1. QA Email Utils SimpleTestCase + Tenant Emails Redundant-Save

### Verdict: **APPROVE** ✅

What I verified:
- `tests/notifications/test_email_utils.py`: import is `SimpleTestCase`, all
  7 classes inherit `SimpleTestCase`, no bare `TestCase` references remain.
  Each class is genuinely DB-free (SimpleNamespace, `@override_settings`,
  `@patch`), so the swap is correct and gives a fail-loud guard against
  accidental DB coupling.
- `tests/tenants/test_tenant_emails.py`: redundant
  `admin_no_name.first_name = ""` + `.save()` removed from
  `test_context_first_name_fallback_when_empty`. `_make_admin(..., first_name="")`
  already creates the user with the empty name, so removal is a true no-op
  cleanup. The fallback assertion `context["first_name"] == "there"` is
  retained.

No issues.

---

## 2. QA Video Pipeline Test Tightening

### Verdict: **APPROVE** ✅

What I verified in `tests/courses/test_video_tasks.py`:
- `test_happy_path_sets_thumbnail_url`: now calls `refresh_from_db()` and
  asserts `video_asset.thumbnail_url == "https://cdn.example.com/thumb.jpg"`.
  Catches any future regression that drops the `save()` or removes
  `thumbnail_url` from `update_fields`.
- `test_happy_path_creates_transcript`: asserts a `VideoTranscript` row is
  created with `full_text == "Hello world"`,
  `vtt_url == "https://cdn.example.com/captions.vtt"`, `language == "en"`.
  Lazy-imports `VideoTranscript` inside the test, consistent with the
  surrounding pattern.
- No production code modified (request says so; spot-checked the file
  list — only the test file changed).

Each new assertion has a descriptive failure message — when these fire in
CI, the message alone tells the reader what regressed.

No issues.

---

## Action
- Mark both QA follow-up notes → **status/done**.
- Both files are clean — no further work required from these requests.

— lp-reviewer
