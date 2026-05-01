---
tags: [review, task/QA-TASK-021-SUPPLEMENTAL, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: QA-TASK-021-SUPPLEMENTAL — Mode Switching Supplemental Tests

## Verdict: APPROVE

## Summary
Good supplemental coverage that fills real gaps: auth matrix, `validate_mode_label_overrides` coercion (including the malformed-payload case flagged in the TASK-021 review request), partial overrides, a corporate↔education round-trip, and a 12-key canonical completeness check. The tests accurately reflect the serializer's current "silently drop invalid" contract (verified in `serializers_admin.py` lines 49–66). One documentation discrepancy to note.

## Verification

### File and test class counts
- `backend/apps/tenants/tests_mode_switching_supplemental.py` — new file created. ✅
- 5 test classes present as described. ✅
- **Test count discrepancy**: the request says "25 new tests across 5 test classes" but `grep -c "def test_"` returns **14**. Breakdown:
  - `ModeAuthTests`: 6 tests ✅
  - `ModeOverrideCoercionTests`: 4 tests ✅ (request said 4)
  - `ModePartialOverrideTests`: 1 test ✅
  - `ModeRoundTripTests`: 1 test ✅
  - `ModeLabelCompletenessTests`: 2 tests ✅
  - **Total: 14, not 25.**

The request prose also claims "`ModeAuthTests` (6 tests)", "coercion (4 tests)", etc. which add to 14 — so the "25" in the header is just a typo. Approving on the content; please correct the headline count in the handoff note and any tracking tickets.

### Coercion tests match the serializer contract
Cross-checked `validate_mode_label_overrides` in `backend/apps/tenants/serializers_admin.py` lines 49–66:
```python
if isinstance(raw, str) and raw.strip():
    cleaned[key.strip()] = raw.strip()
```
The tests' expectations (non-strings dropped, whitespace-only dropped, valid strings preserved) line up exactly. ✅

### Auth matrix completeness
`ModeAuthTests` covers the gap that `tests_mode_switching.py` had — specifically the teacher→`/settings` 403 case and the anon→401 trio. These are real regressions we'd want to catch. ✅

### Positive: the mixed payload test
`test_mixed_payload_drops_non_strings_preserves_strings` (lines 195–216) is the strongest assertion in the file. Unlike the single-field tests (which can pass trivially when the entire overrides dict ends up `{}`), the mixed test proves per-key selectivity: `badge`/`xp` are kept, `course`/`learner` are dropped. This is the test I'd use to catch a regression in the validator loop.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Headline count overstated ("25" vs actual 14)**
   See Verification above. Not a code issue — a handoff note fix.

2. **Single-field coercion tests can pass via full-dict replacement** (lines 160–184)
   `test_non_string_override_value_is_dropped` patches `{"course": 42}` → serializer cleans to `{}` → response shows `mode_label_overrides = {}` → `assertNotIn("course", {})` trivially passes even if the validator regressed to "accept everything, replace whole dict". The mixed-payload test (#4 in the class) does catch this, so the overall class coverage is adequate — but the single-field tests could be hardened by asserting on the full response shape, e.g.:
   ```python
   self.assertEqual(stored, {})  # explicit empty, not just "course absent"
   ```
   or seeding a valid override first and confirming the seeded override survives the invalid PATCH.

3. **`test_switching_back_to_education_reverts_labels` doesn't exercise overrides** (lines 275–301)
   The stronger contract question is: "when an admin sets overrides in corporate mode, then flips to education, what happens to the overrides?" The current test only flips mode without overrides. Recommend extending it (or adding a sibling test) to set an override → flip → confirm behaviour matches product intent (likely: mode change doesn't clear overrides, so they re-apply to the new mode's default layer — which could be confusing UX).

4. **Tenant mutation bypasses the serializer** in `ModeLabelCompletenessTests.test_corporate_mode_exposes_all_12_canonical_keys` (lines 343–344):
   ```python
   self.tenant.mode = "corporate"
   self.tenant.save(update_fields=["mode"])
   ```
   Acceptable for a model-level keys check, but noting that this short-circuits the serializer's normalisation. If a future migration changes how `mode` is stored, this test would silently succeed while the HTTP path breaks. Minor.

5. **`_CTR` module-level counter** (line 32)
   Same note as the other new supplemental QA file: `uuid4().hex[:6]` would make the suite safer under `pytest-xdist`. Consistent with existing suite style; not blocking.

## Positive Observations
- **Directly addresses the TASK-021 review-request open question** about `{"course": 42}` coercion — this is exactly the "fill the gap" work QA should be doing.
- **Design note on tightening to 400** (in the handoff) correctly identifies that the coercion test must change if the serializer switches to hard-400 behaviour. Good anticipation.
- **All 12 canonical keys enumerated** matches the frontend's `ModeLabelKey` union in `tenantStore.ts` — if a new key is added backend-side but not here, the test fails loudly. Good contract assertion.
- **Teacher positive-control on `/me`** (`test_teacher_get_me_returns_200_with_mode_labels`) — presence + content assertion combo is exactly what I'd want to guard against a silent auth-tightening regression.
- **Isinstance + non-empty strip check** in completeness tests rejects both `None` and empty-string regressions in one go.

## Recommended Next Steps
- Approve and merge.
- Correct the "25" → "14" in the handoff / tracking note.
- Follow-up (small): harden the single-field coercion tests to seed a valid override before the invalid PATCH, to prove per-key selectivity rather than whole-dict emptying.
- Follow-up (small): extend the round-trip test to include an overrides seed and confirm the product-intended behaviour after mode flips.
- CI: run
  ```bash
  cd backend && pytest apps/tenants/tests_mode_switching.py \
      apps/tenants/tests_mode_switching_supplemental.py -v
  ```
  to confirm no regressions (blocked in QA sandbox per handoff note).

— lp-reviewer
