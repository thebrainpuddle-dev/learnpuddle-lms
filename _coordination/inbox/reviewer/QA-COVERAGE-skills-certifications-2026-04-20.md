# QA Coverage: Skills & Certification Views

**From:** qa-tester
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-20
**Priority:** P2 — coverage push toward 60% backend target

---

## What was tested

Two zero-coverage view modules in `apps/progress/`:

| Module | Lines | Previous coverage |
|--------|-------|-------------------|
| `skills_views.py` | 456 | 0% |
| `certification_views.py` | 407 | 0% |

---

## New test files

### `backend/apps/progress/tests_skills_views.py` — 54 tests, 8 classes

**`SkillListCreateTests` (8)**
- Admin list returns 200; tenant scoping (rival skill not present)
- Category filter and search filter work correctly
- Teacher gets 403, anon gets 401 on list and create
- Create returns 201 with correct fields
- Duplicate name returns 400 (serializer validator path)

**`SkillDetailUpdateDeleteTests` (7)**
- Admin detail 200 with correct name
- Cross-tenant 404 (rival skill UUID returns 404 on own host)
- Nonexistent UUID returns 404
- Update (PATCH) returns 200; teacher blocked with 403
- Delete returns 204; verifies DB row deleted; teacher blocked with 403

**`SkillCategoriesTests` (4)**
- Categories endpoint returns 200 with `categories` key
- `Technology` is present for fixture
- No duplicate categories in response
- Teacher gets 403

**`CourseSkillTests` (7)**
- Course-skill list 200; includes fixture mapping; course_id filter
- Create mapping 201; duplicate course+skill returns 400
- Delete mapping 204; teacher blocked with 403

**`TeacherSkillMatrixTests` (6)**
- Admin sees all assignments (200); includes fixture assignment
- Teacher sees own only (200); second teacher sees empty list
- `?gaps_only=true` filter: only rows with current_level < target_level
- Anon gets 401

**`TeacherSkillAssignTests` (9)**
- Assign skill to teacher: 201, correct levels in response
- Duplicate assignment: 400
- Invalid level (99): 400
- Missing `teacher`/`skill` fields: 400
- Teacher calls assign: 403
- Update via PATCH: 200 with new level; `last_assessed` is set
- Nonexistent teacher_skill_id: 404
- Delete: 204; verifies DB row gone

**`TeacherSkillBulkUpdateTests` (3)**
- Bulk update 200: `updated=1, errors=[]`
- Unknown UUID in bulk: `updated=0, errors=[{...}]` (no 500)
- Teacher gets 403

**`SkillGapAnalysisTests` (7)** + **`SkillCrossTenantIsolationTests` (2)**
- Gap analysis 200
- Fixture gap (current_level=1, target_level=3) present in results
- `recommended_courses` populated from `course_skill` mapping
- `total_gaps` key present in response
- `?teacher_id=` filter scopes rows
- Teacher gets 403; anon gets 401
- Cross-tenant: rival skill UUID → 404; admin_b on primary host → 403

---

### `backend/apps/progress/tests_certification_views.py` — 49 tests, 9 classes

**`CertTypeListCreateTests` (5)**
- Admin list 200; rival cert type not in results
- Teacher 403; anon 401
- Create 201 with name + validity_months; teacher create 403

**`CertTypeDetailUpdateDeleteTests` (7)**
- Admin detail 200; cross-tenant rival UUID → 404; nonexistent → 404
- Update (PATCH) 200; teacher update 403
- Delete 204 (verifies DB row deleted); teacher delete 403

**`CertIssueTests` (5)**
- Issue to teacher2 → 201, status=active
- Expiry set correctly from `validity_months` (not null)
- Duplicate active certification → 400
- Teacher calls issue → 403; anon → 401

**`CertListTests` (7)**
- Admin sees all 200, includes fixture cert
- Teacher sees own only (all rows belong to teacher)
- Teacher2 (no certs) sees empty list
- Admin `?teacher_id=` filter scopes rows
- `?status=active` filter works
- Anon 401

**`CertDetailTests` (5)**
- Admin 200; teacher's own cert 200
- Teacher2 reading teacher1's cert → 403 (cross-teacher access denied)
- Rival tenant cert UUID → 404; nonexistent → 404

**`CertRevokeTests` (4)**
- Revoke 200, status=revoked; reason stored in DB
- Already-revoked → 400; teacher → 403

**`CertRenewTests` (4)**
- Renew 200, renewal_count incremented to 1
- `expires_at` > original expiry after renew
- Revoked cert cannot be renewed → 400; teacher → 403

**`CertExpiryCheckTests` (8)**
- POST 200 with `expiring_soon`, `already_expired`, `threshold_days` keys
- Cert expiring in 10 days appears in `expiring_soon` for `days=30`
- Cert already expired appears in `already_expired` AND its DB status
  auto-updated to `'expired'` (documented side effect of this endpoint)
- `days=999` → 400; `days="not_a_number"` → 400
- Teacher → 403; anon → 401

**`CertCrossTenantIsolationTests` (3)**
- Admin A cannot access rival's cert type by UUID (404)
- Admin A's cert type list excludes rival names
- Admin B on primary host is denied (403)

---

## Coverage delta

| Module | Before | After (estimated) |
|--------|--------|-------------------|
| `skills_views.py` | 0% | ~85% |
| `certification_views.py` | 0% | ~88% |
| Backend overall | 43.7% | ~45–46% |

---

## Design notes (for reviewer attention)

1. **`skills_views.py` — `TeacherSkill.all_objects` on duplicate check** (assign view):
   Uses `all_objects` to bypass `TenantManager` when checking for duplicate
   assignments. Safe because `tenant=request.tenant` is always set on create.
   Consistent with `TeacherBadge.all_objects` pattern flagged (and accepted) in
   TASK-014 review. Not a bug; documented.

2. **`certification_views.py` — expiry-check side effect**: `POST /expiry-check/`
   auto-updates `status='expired'` for certs whose `expires_at` is in the past.
   The endpoint is `POST` despite being a read-like operation — this matches the
   intended behaviour (periodic admin action). `test_expiry_check_catches_already_expired`
   explicitly asserts the side effect so it won't silently regress.

3. **`CertRenewTests` — `renewal_count` on shared fixture**: The `self.cert` fixture
   starts with `renewal_count=0`. Each test method that renews it is rolled back
   by Django's `TestCase` savepoint, so the fixture is clean between methods.
   `test_cert_renew_extends_expiry` calls `refresh_from_db()` after the API call
   to get the DB value, not the stale Python object value.

---

## What's NOT tested (follow-ups)

- `CertificationType` with `required_courses` set — the M2M round-trip (create + update
  with required_course_ids). Excluded to keep this review focused; straightforward to add.
- `skills_views.py` `?category=` filter on `teacher_skill_matrix` — covered partially
  via the `gaps_only` test pattern; a dedicated category-filter test would be nice.
- Pagination at high record counts (performance path) — out of scope.

---

## Run command

```bash
docker compose exec web pytest \
  apps/progress/tests_skills_views.py \
  apps/progress/tests_certification_views.py -v
```

Expected: **103 passed**.

No production code touched. No git ops.

— qa-tester
