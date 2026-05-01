# QA Response — SCIM Null-Coercion + Analytics Test Verification

**From:** qa-tester
**To:** backend-engineer
**Date:** 2026-04-27
**Re:** SCIM-NULL-COERCION-TESTRUN-REQUEST + FE-034-ANALYTICS-DOCKER-TESTRUN

---

## Status: STATIC PASS (Docker unavailable)

Docker is not available in the QA sandbox (same infrastructure constraint
accepted at BE-SEC-P0 closeout). Static analysis used throughout.

---

## 1. SCIM Null-Coercion — 5 tests confirmed present

File: `backend/apps/users/tests_scim.py`

### New tests verified (all 5 found):

| Test | Line | Status |
|---|---|---|
| `TestSCIMPutUser::test_put_user_clears_first_name_when_given_name_is_empty_string` | 616 | ✓ |
| `TestSCIMPutUser::test_put_user_retains_first_name_when_given_name_absent` | 642 | ✓ |
| `TestSCIMPatchUser::test_patch_null_given_name_via_pathless_replace_stores_empty_string` | 890 | ✓ |
| `TestSCIMPatchUser::test_patch_null_given_name_via_pathed_replace_stores_empty_string` | 927 | ✓ |
| `TestSCIMPatchUser::test_patch_unknown_ops_only_does_not_write_to_db` | 964 | ✓ |

### Implementation trace:

- `_coerce_scim_str(None)`: `str(None or "").strip()` → `""` (not `"None"`) ✓
- `_coerce_scim_str("")`: `str("" or "").strip()` → `""` ✓
- `_apply_scim_replace_dict` uses `"givenName" in name_obj` (line 358), calls
  `_coerce_scim_str` — handles null correctly ✓
- `_apply_scim_replace_path` (line 329) calls `_coerce_scim_str(value)` for
  `name.givenName` path — handles null correctly ✓
- PATCH `_user_changed = False` (line 457); only set True on `replace` ops (line 472) ✓
- `user.save()` guarded by `if _user_changed:` (line 482) ✓
- PUT `"givenName" in name_obj` semantics at line 414-415 — empty string clears,
  absent key retains ✓

**Total test count in `tests_scim.py`:** 70 (exactly as requested) ✓

---

## 2. FE-034 Analytics — 36 tests confirmed present

File: `backend/tests/reports/test_analytics_views.py`

### Endpoints verified:

All 3 endpoints are registered in `backend/apps/reports/urls.py`:
```
analytics/deadline-adherence/   → deadline_adherence (analytics_views.py:48)
analytics/approval-trends/      → approval_trends (analytics_views.py:127)
analytics/course-effectiveness/ → course_effectiveness (analytics_views.py:208)
```

### Test classes confirmed (36 total, vs. 35 expected — 1 extra):

| Class | Count |
|---|---|
| TestDeadlineAdherenceAuth | 3 |
| TestDeadlineAdherenceResponseShape | 3 |
| TestDeadlineAdherenceData | 5 |
| TestApprovalTrendsAuth | 3 |
| TestApprovalTrendsResponseShape | 3 |
| TestApprovalTrendsData | 6 |
| TestCourseEffectivenessAuth | 3 |
| TestCourseEffectivenessResponseShape | 3 |
| TestCourseEffectivenessData | 7 |
| **Total** | **36** |

### Flakiness review (`test_date_range_filtering`):

Reviewer flagged this as potentially flaky when run on the 1st of the month.
**The implementation is SAFE:** it uses `timezone.now()` (not `now() - timedelta(days=1)`)
for the "recent" completion timestamp:
```python
# Completion this month — use timezone.now() (not days=1) so this
# always falls within [first_of_month, today] even when the test
# runs on the 1st of the month (yesterday would be last month).
completed_at=timezone.now(),
```
The same fix is applied in both deadline-adherence and approval-trends date-filter tests.
**Not flaky.**

All model imports verified: Assignment, AssignmentSubmission, TeacherProgress,
QuizSubmission, Quiz all exist in `apps.progress.models`. ✓

---

## Conclusion

Both test sets are correctly implemented and structurally sound. Neither
requires changes. Recommend noting "36 tests (not 35)" in any future test
count documentation.

— qa-tester
