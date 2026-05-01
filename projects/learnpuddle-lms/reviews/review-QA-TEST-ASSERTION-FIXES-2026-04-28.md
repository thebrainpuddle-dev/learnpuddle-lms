---
tags: [review, task/QA-TEST-ASSERTION-FIXES, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: QA-TEST-ASSERTION-FIXES — Test assertion follow-ups (3 files)

## Verdict: APPROVE

## Summary
Test-only changes that (1) realign a buggy assertion to the now-fixed `ReportRun.status="error"` contract, (2) tighten three lenient assertions in the new chat-integration view tests, and (3) add a parity assertion in the video-pipeline thumbnail test. Every change was verified against the production source it pins.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None blocking. Two small observations, both fine to defer:

- **(nit)** `test_list_includes_soft_deleted_integration` is an excellent behavior pin, but the docstring/comment is the only signal that the *expected* end-state is to flip to "excludes". If/when an `is_active=True` filter is added, a future reviewer might delete the test instead of converting it. Consider tagging it with a `# TODO(soft-delete-filter): convert to excludes when filter lands` so a grep finds it. Optional.
- **(nit)** In `test_create_with_ssrf_url_returns_400`, the chosen SSRF host (`hooks.slack.com.evil.example.com`) tests the suffix-confusion case, which is good. If the SSRF guard is later strengthened to also block private IPs at the resolver level, you may want a second test with a literal `http://127.0.0.1/...` to cover both branches. Not in scope here.

## Detailed Verification

### 1) `apps/reports_builder/tests_report_builder.py`
- Diff inspected at lines 1017–1040.
- `ReportRun.STATUS_CHOICES` (models.py:151–156) = `pending, running, success, error`. `"failed"` is **not** a valid choice; `"error"` is. ✓
- `ReportSchedule.STATUS_CHOICES` (models.py:91–96) includes `delivery_failed`. ✓
- `tasks.py:374` now sets `run.status = "error"` with an in-line comment explaining the constraint. The renamed test (`..._sets_run_status_error`) correctly asserts that contract.
- Test renamed to match its assertion — good practice, search-friendly.

### 2) `apps/integrations_chat/tests_chat_integration_views.py`
- `test_list_response_masks_webhook_url` (L235–249): unconditional `assertTrue(item["webhook_url_masked"])` + `assertNotIn(SLACK_WEBHOOK, str(item))`. The lenient `if item.get(...)` guard is gone — empty-string regression now fails loudly. ✓
- `test_create_routing_rule_returns_201` (L590–599): tightened to `assertEqual(resp.status_code, 201)`. ✓
- `test_create_with_ssrf_url_returns_400` (L330–344): tightened to `assertEqual(resp.status_code, 400)`. ✓
- `test_list_includes_soft_deleted_integration` (L251–273): clean behavior pin with a docstring spelling out the inversion path. The mutation (`integration.is_active = False; save(update_fields=["is_active"])`) is minimal and isolated. ✓
- Test count 33 → 34 matches the diff.

### 3) `apps/courses/tests_video_pipeline.py`
- `test_thumbnail_marks_failed_when_source_file_missing` (L457): `self.assertIn("source_file", self.asset.error_message.lower())`. ✓
- Production code (`apps/courses/tasks.py:771–772`): `if not asset.source_file: _mark_failed(asset, "Missing source_file for video asset")` — the literal `"source_file"` substring is present, so the `.lower()` assertion is sound.
- Parity confirmed with the transcode counterpart at L331 — same pattern, same message.

## Positive Observations
- **Discipline**: every loosened assertion (`assertIn(code, [200, 201])`, `if x:` guards) was located and tightened. That's exactly the right response to a "tighten lenient assertions" verdict.
- **Documentation**: docstrings on the renamed/new tests explain *why* the contract is what it is, including the `STATUS_CHOICES` rationale. That makes the tests self-explaining when the next engineer hits them.
- **Source verification**: each new assertion has a concrete production line backing it (cited in the request body), and I verified each one. No assertions invented from imagination.
- **Surface area**: zero production code touched, no new fixtures, no skipped tests, no flake risk. Cleanest kind of follow-up.
- **Behavior pin pattern**: the soft-delete pin is a textbook example — encode the current contract so the next change to that queryset is forced through review, not silently merged.

## Decision
APPROVE — merge as-is. The earlier review verdicts are fully addressed.
