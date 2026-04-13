# Academic Structure, Auth & Course Workflow — Design Spec

**Pilot client:** Keystone International School, Hyderabad
**Date:** 2026-04-11
**Status:** Approved

---

## 1. Overview

LearnPuddle currently supports flat user management: admins create teachers, assign courses individually or via TeacherGroups. Students are assigned individually or broadcast to all. There is no concept of grades, sections, subjects, or teaching assignments.

This spec introduces the **academic structure backbone** — grades, sections, subjects, and teaching assignments — that enables:
- Visual school management UI (grade-card navigation)
- Teacher-created academic courses with auto-assignment to students
- Flexible login (email or student ID)
- Academic year promotion
- White-label branding per grade band
- Contextual CSV import

**Pilot-first approach:** Built for Keystone's specific structure (Nursery through Grade 12, Cambridge + IB curriculum). Generalization comes from real usage.

---

## 2. Keystone Education — Context

- **School:** Keystone International School, Puppalguda, Financial District, Hyderabad
- **Grades:** Nursery → PP1 → PP2 → Grade 1-12 (K-12)
- **Curriculum:**
  - Early Years (Nursery, PP1, PP2): Reggio Emilia approach
  - Primary (G1-G5): Cambridge Primary
  - Middle School (G6-G8): Cambridge Secondary 1
  - High School (G9-G10): IGCSE, (G11-G12): KIPP (Cambridge + IB hybrid)
- **Campus:** Single campus, co-ed day school
- **Identity:** Green/nature-forward branding, IGBC Platinum-rated campus, "Idea Loom" pedagogical model
- **Founder:** Srilakshmi Reddy (M.Ed, Santa Clara University)

---

## 3. Design Principles

1. **LearnPuddle is an LMS, not a SIS.** We manage learning content and progress. School structure (who teaches what, who's in which section) is admin-configured data that drives access control.
2. **Admin owns all structural decisions.** Teacher visibility, course ownership, student transfers, user creation/deletion — all admin actions.
3. **Design for flexibility.** School email is the primary login, student ID is an alternative. SSO can be plugged in later via existing `sso_domains` infrastructure.
4. **Start manual, add automation.** Elective-aware auto-assignment is a future phase. Manual assignment works now, data model supports automation later.

---

## 4. New Data Models

### 4.1 GradeBand

Groups grades into pedagogical stages. Controls per-stage theming and login defaults.

```
GradeBand
├── id (UUID, PK)
├── tenant (FK → Tenant)
├── name (CharField, e.g., "Early Years", "Primary", "High School")
├── short_code (CharField, e.g., "KEY", "PRI", "MID", "HS")
├── order (PositiveIntegerField, display order)
├── curriculum_framework (CharField, choices: REGGIO_EMILIA, CAMBRIDGE_PRIMARY, CAMBRIDGE_SECONDARY, IGCSE, KIPP, CUSTOM)
├── theme_config (JSONField, nullable)
│   ├── accent_color (string)
│   ├── bg_image (string, URL)
│   └── welcome_msg (string)
├── created_at (DateTimeField)
└── updated_at (DateTimeField)

Manager: TenantManager
Unique: (tenant, name)
Ordering: [order]
```

### 4.2 Grade

Individual grade/year level within a grade band.

```
Grade
├── id (UUID, PK)
├── tenant (FK → Tenant)
├── grade_band (FK → GradeBand)
├── name (CharField, e.g., "Nursery", "PP1", "Grade 9")
├── short_code (CharField, e.g., "NUR", "PP1", "G9")
├── order (PositiveIntegerField, global sort order across all grade bands)
├── created_at (DateTimeField)
└── updated_at (DateTimeField)

Manager: TenantManager
Unique: (tenant, short_code)
Ordering: [order]
```

### 4.3 Section

Optional division within a grade for a specific academic year.

```
Section
├── id (UUID, PK)
├── tenant (FK → Tenant)
├── grade (FK → Grade)
├── name (CharField, e.g., "A", "B", "C")
├── academic_year (CharField, e.g., "2026-27")
├── class_teacher (FK → User, nullable, on_delete=SET_NULL)
├── created_at (DateTimeField)
└── updated_at (DateTimeField)

Manager: TenantManager
Unique: (tenant, grade, name, academic_year)
Ordering: [grade__order, name]
```

### 4.4 Subject

Curriculum subjects tied to applicable grades.

```
Subject
├── id (UUID, PK)
├── tenant (FK → Tenant)
├── name (CharField, e.g., "Physics", "English Language")
├── code (CharField, e.g., "PHY", "ENG")
├── department (CharField, e.g., "Science", "Languages")
├── applicable_grades (M2M → Grade)
├── is_elective (BooleanField, default=False)
├── created_at (DateTimeField)
└── updated_at (DateTimeField)

Manager: TenantManager
Unique: (tenant, code)
Ordering: [department, name]
```

### 4.5 TeachingAssignment

Maps a teacher to the subjects and sections they teach in a given academic year.

```
TeachingAssignment
├── id (UUID, PK)
├── tenant (FK → Tenant)
├── teacher (FK → User)
├── subject (FK → Subject)
├── sections (M2M → Section)
├── academic_year (CharField, e.g., "2026-27")
├── is_class_teacher (BooleanField, default=False)
├── created_at (DateTimeField)
└── updated_at (DateTimeField)

Manager: TenantManager
Unique: (tenant, teacher, subject, academic_year)
```

---

## 5. Changes to Existing Models

### 5.1 Tenant Model — New Fields

| Field | Type | Purpose |
|-------|------|---------|
| `current_academic_year` | CharField(20) | e.g., "2026-27" |
| `academic_year_start_date` | DateField, nullable | Start of academic year |
| `academic_year_end_date` | DateField, nullable | End of academic year |
| `id_prefix` | CharField(10) | Auto-ID prefix, e.g., "KIS" |
| `student_id_counter` | PositiveIntegerField, default=1 | Next student sequence |
| `teacher_id_counter` | PositiveIntegerField, default=1 | Next teacher sequence |
| `white_label` | BooleanField, default=False | Hide LearnPuddle branding |
| `login_bg_image` | URLField, blank | Login page background image |
| `welcome_message` | CharField(200), blank | Dashboard greeting |
| `school_motto` | CharField(200), blank | Footer/about text |

### 5.2 User Model — Field Changes

| Current | New | Notes |
|---------|-----|-------|
| `grade_level` (CharField) | `grade` (FK → Grade, nullable) | Proper relationship |
| `section` (CharField) | `section` (FK → Section, nullable) | Proper relationship |
| `student_id` (CharField) | Keep, but auto-generated | Format: `{prefix}-S-{counter}` |
| `employee_id` (CharField) | Keep, but auto-generated | Format: `{prefix}-T-{counter}` |

Old text fields (`grade_level`, `section`) are kept temporarily for backward compatibility during migration, then removed in a follow-up cleanup migration.

### 5.3 Course Model — New Fields

| Field | Type | Purpose |
|-------|------|---------|
| `course_type` | CharField, choices: PD, ACADEMIC | Distinguishes PD from academic courses |
| `subject` | FK → Subject, nullable | For academic courses |
| `target_grades` | M2M → Grade | Which grades this course targets |
| `target_sections` | M2M → Section | Specific sections (optional, defaults to all in target grades) |

Existing fields stay: `assigned_teachers`, `assigned_students`, `assigned_to_all`, `assigned_groups`, `assigned_to_all_students`.

---

## 6. Auto-Generated User IDs

### Format

- Students: `{tenant.id_prefix}-S-{zero_padded(tenant.student_id_counter, 4)}` → `KIS-S-0001`
- Teachers: `{tenant.id_prefix}-T-{zero_padded(tenant.teacher_id_counter, 4)}` → `KIS-T-0001`

### Rules

- Generated on user creation (in `create_user` or bulk import)
- Permanent — never changes, never recycled
- Counter is atomic (F-expression increment on Tenant to avoid race conditions)
- Admin configures `id_prefix` in tenant settings
- IDs serve as alternative login identifiers

---

## 7. Authentication Flow

### Login — Flexible Identifier

Single login endpoint. System auto-detects identifier type:

| Input | Detection Rule | Lookup Field |
|-------|---------------|-------------|
| Contains `@` | Email | `User.email` |
| Matches `{prefix}-S-{digits}` | Student ID | `User.student_id` |
| Matches `{prefix}-T-{digits}` | Teacher ID | `User.employee_id` |

Login view tries email first, then student_id, then employee_id. Returns standard JWT tokens on success.

### SSO (Future-Ready)

Existing infrastructure supports Google/Microsoft SSO when Keystone enables it:
1. Admin adds `keystoneeducation.in` to `tenant.sso_domains`
2. Login page shows "Sign in with Google" button
3. No new code needed — already built

### Password Policy

- All users get `must_change_password=True` on bulk import
- Forced password change on first login (existing behavior)
- Standard Django password validation (minimum length, complexity)

---

## 8. User Provisioning

### Admin Creates Users via School View

**Contextual CSV import:**
1. Admin navigates to Grade 9 → Section A → clicks "Import Students"
2. CSV template requires only: `first_name, last_name, email`
3. Grade and section are pre-filled from navigation context
4. System auto-generates `student_id` (e.g., `KIS-S-0023`)
5. System sets `must_change_password=True`

**Individual creation:**
- "Add Student" button within a section view
- Form: first_name, last_name, email (student_id auto-generated)

**Teacher provisioning:**
- Same CSV import from teacher management view
- System auto-generates `employee_id` (e.g., `KIS-T-0015`)
- After import, admin maps Teaching Assignments

### Mid-Year Changes

- **Transfer student:** Admin moves student from 9A to 9B. System updates `user.section`, re-evaluates course auto-assignments (add courses targeting 9B, optionally remove 9A-only courses).
- **New student joins:** Added to section, signal auto-assigns existing courses targeting that section.
- **Student leaves:** Soft-delete. Progress preserved.

---

## 9. Academic Year Promotion

Admin triggers "Promote to Next Year" workflow:

1. **Preview:** System shows grade-by-grade promotion plan: "87 students G9 → G10, 45 G10 → G11..."
2. **Exceptions:** Admin can exclude specific students (holdbacks) or mark as graduated (G12 students)
3. **On confirm:**
   - `tenant.current_academic_year` updates (e.g., "2026-27" → "2027-28")
   - Students' `grade` FK moves to next Grade in order
   - Students' `section` FK is set to null (admin re-assigns for new year)
   - `TeachingAssignment` records for old year are kept (archived by `academic_year` field)
   - `assigned_students` on academic courses are cleared
   - New sections are created for the new academic year
   - Progress records preserved, tagged with academic year for historical queries
4. **Post-promotion:** Admin sets up new sections, re-assigns students, re-creates teaching assignments

---

## 10. Course Creation Workflow

### Two Course Types

| Aspect | PD Course | Academic Course |
|--------|-----------|-----------------|
| Created by | Admin | Teacher (or Admin) |
| Consumed by | Teachers | Students |
| `course_type` | `PD` | `ACADEMIC` |
| Subject | Optional | Required (FK) |
| Target grades | N/A | Required (M2M) |
| Target sections | N/A | Optional (M2M) |
| Assignment method | TeacherGroups + individual + teaching-assignment targeting | Auto via grade/section + manual override |

### Teacher Creates Academic Course

1. Teacher opens section view (e.g., "Grade 9A · Physics")
2. Clicks "Create Course" → form pre-fills: subject=Physics, target_grades=G9, target_sections=9A
3. Teacher can expand targeting (add 9B, 9C, all G9 sections)
4. Builds content using existing course editor
5. On publish → system populates `assigned_students` with all students in targeted sections
6. New student joins section mid-year → signal auto-assigns

### Teacher Permissions (Enforced by TeachingAssignment)

- Can only create courses for sections in their teaching assignments
- Can only view students in their assigned sections
- Can edit/delete their own courses only
- Cannot create PD courses
- Cannot access other teachers' courses (admin can share explicitly)

### Admin PD Course Assignment (Enhanced)

Existing mechanisms plus new targeting options:
- "Assign to all Science teachers" → `TeachingAssignment.subject.department = 'Science'`
- "Assign to all Grade 9 teachers" → `TeachingAssignment.sections__grade = G9`
- TeacherGroups remain for ad-hoc grouping

### Course Lifecycle

- **Clone Course:** Teacher duplicates a course for next year/different section. Content copied, progress reset, targeting adjusted.
- **Teacher leaves:** Courses stay active. Admin reassigns ownership via "Transfer Courses" action.
- **Multiple teachers, same subject+section:** Allowed. Both see the section, both can create courses.

---

## 11. School View UI

### Admin View

**Level 1 — School Overview:**
- Grade cards grid grouped by grade band (Early Years, Primary, Middle, High School)
- Each card shows: grade name, student count, section count
- Top bar: school name, academic year, settings gear

**Level 2 — Grade Detail:**
- Section cards showing: section name, student count, class teacher, subject count, course count
- Actions: Add Section, Import CSV (contextual to grade)

**Level 3 — Section Detail (3 tabs):**
- **Students tab:** Roster with name, ID, progress %, last active, traffic-light status (green >60%, amber 30-60%, red <30%). Search, sort, actions (edit, transfer, deactivate).
- **Teachers tab:** Subject teachers assigned to this section via TeachingAssignment.
- **Courses tab:** All academic courses targeting this section.

### Teacher View

**Level 1 — My Classes:**
- Section cards grouped by subject (derived from TeachingAssignment)
- Each card: grade+section, student count, avg progress, course count

**Level 2 — Section Dashboard (4 tabs):**
- **Students:** Roster with per-student progress, last active, pending assignments. Traffic-light indicators.
- **Courses:** Teacher's courses for this section. "Create Course" button (pre-filled). Course cards with completion rates.
- **Analytics:** Section-level stats — avg completion, top performers, students needing attention, submission rates, time-on-platform trends, section comparison (anonymized).
- **Assignments & Quizzes:** Submission status grid (student x assignment), quick grading access, average scores.

---

## 12. White-Label Branding

### Tenant Config

| Field | Example (Keystone) |
|-------|-------------------|
| `white_label` | `True` |
| `login_bg_image` | Keystone campus photo URL |
| `welcome_message` | "Welcome to Keystone Learning" |
| `school_motto` | "Powered by the Idea-Loom Model" |

### White-Label Behavior (when enabled)

- **Login page:** School logo, school name, campus background. No "LearnPuddle" anywhere.
- **Footer:** "© 2026 Keystone International School"
- **Email templates:** From name = school name, not "LearnPuddle"
- **Browser tab title:** School name
- **Dashboard greeting:** `welcome_message` from tenant config

### Grade Band Theming

`GradeBand.theme_config` (JSONField) allows per-stage visual customization:
- `accent_color`: Override default accent for student portal
- `bg_image`: Background image for student dashboard
- `welcome_msg`: Grade-band-specific greeting

Student portal reads theme from their grade's grade band. Falls back to tenant defaults.

---

## 13. Keystone Seed Data

Pre-configured for pilot launch:

```
Tenant:
  name: Keystone International School
  subdomain: keystone
  current_academic_year: 2026-27
  id_prefix: KIS
  white_label: true

Grade Bands:
  1. Early Years (KEY) — REGGIO_EMILIA
     Grades: Nursery, PP1, PP2
  2. Primary (PRI) — CAMBRIDGE_PRIMARY
     Grades: Grade 1, Grade 2, Grade 3, Grade 4, Grade 5
  3. Middle School (MID) — CAMBRIDGE_SECONDARY
     Grades: Grade 6, Grade 7, Grade 8
  4. High School (HS) — IGCSE / KIPP
     Grades: Grade 9, Grade 10, Grade 11, Grade 12

Subjects (initial set, admin can modify):
  All grades: English, Mathematics, Science (integrated), Social Studies
  G6+: Hindi, Computer Science
  G9+: Physics, Chemistry, Biology, Economics, Business Studies
  G11+: Psychology, Sociology, Art & Design
```

---

## 14. Scope Boundaries

### In Scope (This Spec)
- 5 new Django models (GradeBand, Grade, Section, Subject, TeachingAssignment)
- Tenant model additions (academic year, ID generation, white-label fields)
- User model FK migration (grade_level → grade, section → section)
- Course model additions (course_type, subject, target_grades, target_sections)
- Auto-generated student/teacher IDs
- Flexible login (email or ID)
- Auto-assignment of courses based on section targeting
- Academic year promotion workflow
- School View admin UI (grade cards, drill-down, contextual CSV import)
- Teacher "My Classes" view (filtered section dashboard with 4 tabs)
- White-label tenant branding
- Keystone seed data / management command
- Clone Course action

### Out of Scope (Future Phases)
- Elective-aware auto-assignment (data model supports it, workflow not built)
- SIS / Google Workspace / Azure AD sync
- Parent portal (parent_email stored, portal not built)
- Custom domain SSL/nginx (subdomain only for now)
- Attendance tracking
- Student notes / teacher comments on students
- Timetable / scheduling integration

---

## 15. Migration Strategy

1. New models created with no impact on existing data
2. User model: add `grade` (FK) and `section` (FK) as nullable fields alongside existing text fields
3. Data migration: for tenants that have students with `grade_level` text, attempt to match to Grade objects (best-effort)
4. Course model: add new fields as nullable/blank — existing courses default to `course_type='PD'`
5. Old text fields (`grade_level`, `section` on User) deprecated but not removed in this phase
6. No breaking changes to existing API endpoints — all new endpoints are additive
