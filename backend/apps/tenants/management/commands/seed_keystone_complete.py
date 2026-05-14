"""
Seed ALL remaining Keystone demo data not covered by other seed commands.
Covers: certifications, accreditations, compliance, teaching assignments,
study summaries, and attendance.

Run AFTER: seed_keystone, seed_keystone_demo, seed_maic_data, seed_teacher_data
"""
import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Seed complete Keystone demo data (certifications, accreditations, compliance, teaching assignments)"

    def handle(self, *args, **options):
        from apps.tenants.models import Tenant
        from apps.users.models import User
        from apps.academics.models import Grade, Section, Subject, TeachingAssignment

        try:
            tenant = Tenant.objects.get(subdomain="keystone")
        except Tenant.DoesNotExist:
            self.stderr.write("Keystone tenant not found. Run seed_keystone first.")
            return

        now = timezone.now()
        academic_year = tenant.current_academic_year or "2026-27"
        teachers = list(User.objects.all_tenants().filter(tenant=tenant, role="TEACHER", is_deleted=False))
        students = list(User.objects.all_tenants().filter(tenant=tenant, role="STUDENT", is_deleted=False))
        admin = User.objects.all_tenants().filter(tenant=tenant, role="SCHOOL_ADMIN", is_deleted=False).first()

        self.stdout.write(f"\nFound {len(teachers)} teachers, {len(students)} students\n")

        # ── 1. Teaching Assignments ──────────────────────────────────
        self.stdout.write("  [1/5] Seeding teaching assignments...")
        sections = list(Section.objects.filter(grade__tenant=tenant))
        subjects = list(Subject.objects.filter(tenant=tenant))

        ta_count = 0
        if sections and subjects:
            assignments_map = [
                # (teacher_email, subject_codes, grade_range)
                ("priya.sharma@keystoneeducation.in", ["SCI", "PHY"], range(6, 13)),
                ("raj.patel@keystoneeducation.in", ["MAT"], range(6, 13)),
                ("anita.desai@keystoneeducation.in", ["ENG"], range(1, 8)),
                ("vikram.singh@keystoneeducation.in", ["CS", "MAT"], range(9, 13)),
                ("teacher@keystoneeducation.in", ["SST", "HIN"], range(6, 10)),
            ]
            for email, subj_codes, grade_range in assignments_map:
                teacher = next((t for t in teachers if t.email == email), None)
                if not teacher:
                    continue
                for subj in subjects:
                    if subj.code not in subj_codes:
                        continue
                    # TeachingAssignment uses M2M sections, not FK section
                    ta, created = TeachingAssignment.objects.get_or_create(
                        tenant=tenant,
                        teacher=teacher,
                        subject=subj,
                        academic_year=academic_year,
                    )
                    if created:
                        ta_count += 1
                    # Add matching sections to the M2M
                    for section in sections:
                        grade_num = None
                        gname = section.grade.name.lower()
                        for i in range(1, 13):
                            if f"grade {i}" == gname or f"g{i}" == gname:
                                grade_num = i
                                break
                        if grade_num is not None and grade_num in grade_range:
                            ta.sections.add(section)
            self.stdout.write(f"        {ta_count} teaching assignments created.")
        else:
            self.stdout.write("        No sections/subjects found, skipping.")

        # ── 2. Assign students to sections ───────────────────────────
        self.stdout.write("  [2/5] Assigning students to sections...")
        student_count = 0
        if sections and students:
            # Spread students across middle/high school sections
            target_sections = [s for s in sections if any(
                x in s.grade.name.lower() for x in ["grade 9", "grade 10", "g9", "g10"]
            )]
            if not target_sections:
                target_sections = sections[:5]
            for i, student in enumerate(students):
                section = target_sections[i % len(target_sections)]
                if student.section_fk != section:
                    student.section_fk = section
                    student.grade_fk = section.grade
                    student.save(update_fields=["section_fk", "grade_fk"])
                    student_count += 1
            self.stdout.write(f"        {student_count} students assigned to sections.")

        # ── 3. Certifications ────────────────────────────────────────
        self.stdout.write("  [3/5] Seeding certifications...")
        cert_count = 0
        try:
            from apps.tenants.accreditation_models import StaffCertification
            from datetime import date
            cert_data = [
                {
                    "teacher_email": "priya.sharma@keystoneeducation.in",
                    "certs": [
                        ("IB_CAT1", "2024-06-15", "2027-06-15", "VALID", "IB Education"),
                        ("GOOGLE_CERT", "2025-01-10", "2028-01-10", "VALID", "Google Education"),
                        ("FIRST_AID", "2024-09-01", "2026-09-01", "VALID", "Red Cross"),
                    ],
                },
                {
                    "teacher_email": "raj.patel@keystoneeducation.in",
                    "certs": [
                        ("SUBJECT_CERT", "2024-03-01", "2027-03-01", "VALID", "Cambridge University"),
                        ("DIGITAL_LITERACY", "2025-02-20", "2026-02-20", "EXPIRING", "Microsoft Education"),
                    ],
                },
                {
                    "teacher_email": "anita.desai@keystoneeducation.in",
                    "certs": [
                        ("IB_CAT2", "2023-04-01", "2026-04-01", "EXPIRED", "IB Education"),
                        ("CHILD_SAFEGUARDING", "2025-06-01", "2028-06-01", "VALID", "NSPCC"),
                    ],
                },
                {
                    "teacher_email": "vikram.singh@keystoneeducation.in",
                    "certs": [
                        ("GOOGLE_CERT", "2024-11-15", "2027-11-15", "VALID", "Google Education"),
                        ("NEP_TRAINING", "2025-03-01", None, "VALID", "NCERT"),
                    ],
                },
                {
                    "teacher_email": "teacher@keystoneeducation.in",
                    "certs": [
                        ("POCSO", "2025-01-10", "2028-01-10", "VALID", "Govt of India"),
                        ("POSH", "2025-02-15", "2028-02-15", "VALID", "Govt of India"),
                    ],
                },
            ]

            for entry in cert_data:
                teacher = next((t for t in teachers if t.email == entry["teacher_email"]), None)
                if not teacher:
                    continue
                for cert_type, completed, expires, status, provider in entry["certs"]:
                    _, created = StaffCertification.objects.get_or_create(
                        tenant=tenant,
                        teacher=teacher,
                        certification_type=cert_type,
                        defaults={
                            "completed_date": date.fromisoformat(completed),
                            "expiry_date": date.fromisoformat(expires) if expires else None,
                            "status": status,
                            "provider": provider,
                        },
                    )
                    if created:
                        cert_count += 1
            self.stdout.write(f"        {cert_count} staff certifications created.")
        except (ImportError, Exception) as e:
            self.stdout.write(f"        Skipping certifications: {e}")

        # ── 4. School Accreditations ─────────────────────────────────
        self.stdout.write("  [4/5] Seeding accreditations...")
        accred_count = 0
        try:
            from apps.tenants.accreditation_models import SchoolAccreditation, AccreditationMilestone
            from datetime import date

            accreds = [
                {
                    "accreditation_type": "CAMBRIDGE_IGCSE",
                    "status": "AUTHORIZED",
                    "valid_from": date(2020, 8, 1),
                    "valid_to": date(2027, 8, 1),
                    "issuing_body": "Cambridge Assessment International Education",
                    "affiliation_number": "IN-845",
                    "notes": "Full Cambridge International School status",
                    "renewal_cycle_months": 84,
                    "milestones": [
                        ("Self-Study Report", "COMPLETED", date(2020, 3, 1)),
                        ("Team Visit", "COMPLETED", date(2020, 5, 15)),
                        ("Mid-Cycle Review", "COMPLETED", date(2023, 9, 1)),
                        ("Next Re-Authorization", "PENDING", date(2027, 8, 1)),
                    ],
                },
                {
                    "accreditation_type": "IB_PYP",
                    "status": "CANDIDACY",
                    "valid_from": date(2025, 1, 15),
                    "valid_to": date(2027, 1, 15),
                    "issuing_body": "International Baccalaureate Organization",
                    "notes": "PYP Candidacy phase — working toward authorization",
                    "renewal_cycle_months": 60,
                    "milestones": [
                        ("Interest Application", "COMPLETED", date(2024, 6, 1)),
                        ("Candidacy Granted", "COMPLETED", date(2025, 1, 15)),
                        ("School Self-Study", "IN_PROGRESS", date(2026, 6, 1)),
                        ("IB Verification Visit", "PENDING", date(2027, 1, 1)),
                    ],
                },
                {
                    "accreditation_type": "NABET",
                    "status": "AUTHORIZED",
                    "valid_from": date(2022, 4, 10),
                    "valid_to": date(2025, 4, 10),
                    "issuing_body": "NAAC-NABET (QCI)",
                    "affiliation_number": "NABET-2022-1834",
                    "notes": "NAAC-NABET quality accreditation (renewal due)",
                    "renewal_cycle_months": 36,
                    "milestones": [
                        ("Initial Assessment", "COMPLETED", date(2022, 2, 1)),
                        ("Accreditation Granted", "COMPLETED", date(2022, 4, 10)),
                        ("Annual Compliance Report", "COMPLETED", date(2024, 4, 10)),
                        ("Renewal Application", "IN_PROGRESS", date(2025, 4, 10)),
                    ],
                },
                {
                    "accreditation_type": "CBSE",
                    "status": "AUTHORIZED",
                    "valid_from": date(2018, 4, 1),
                    "valid_to": date(2028, 3, 31),
                    "issuing_body": "Central Board of Secondary Education",
                    "affiliation_number": "3630192",
                    "notes": "CBSE affiliation up to Senior Secondary level",
                    "renewal_cycle_months": 120,
                    "milestones": [
                        ("Affiliation Granted", "COMPLETED", date(2018, 4, 1)),
                        ("Inspection Visit", "COMPLETED", date(2023, 11, 15)),
                        ("Next Renewal", "PENDING", date(2028, 3, 31)),
                    ],
                },
            ]

            for accred in accreds:
                milestones = accred.pop("milestones")
                obj, created = SchoolAccreditation.objects.get_or_create(
                    tenant=tenant,
                    accreditation_type=accred["accreditation_type"],
                    defaults=accred,
                )
                if created:
                    accred_count += 1
                    for idx, (title, status, target) in enumerate(milestones):
                        AccreditationMilestone.objects.get_or_create(
                            accreditation=obj,
                            title=title,
                            defaults={
                                "status": status,
                                "due_date": target,
                                "completed_date": target if status == "COMPLETED" else None,
                                "order": idx,
                            },
                        )
            self.stdout.write(f"        {accred_count} accreditations created with milestones.")
        except (ImportError, Exception) as e:
            self.stdout.write(f"        Skipping accreditations: {e}")

        # ── 5. Compliance Items ──────────────────────────────────────
        self.stdout.write("  [5/5] Seeding compliance items...")
        compliance_count = 0
        try:
            from apps.tenants.accreditation_models import ComplianceItem
            from datetime import date

            items = [
                ("SAFETY", "Fire Safety NOC Renewal", "COMPLIANT", date(2026, 1, 15), "Admin Office", "ANNUAL"),
                ("SAFETY", "Fire Drill & Evacuation Record", "COMPLIANT", date(2026, 3, 15), "Safety Officer", "QUARTERLY"),
                ("BOARD", "CBSE Annual Return Filing", "IN_PROGRESS", date(2026, 6, 30), "Principal", "ANNUAL"),
                ("BOARD", "UDISE+ Data Submission", "COMPLIANT", date(2025, 12, 31), "Data Entry Operator", "ANNUAL"),
                ("NEP", "NEP 2020 Competency Mapping", "IN_PROGRESS", date(2026, 7, 31), "Academic Coordinator", "ONE_TIME"),
                ("NEP", "Foundational Literacy & Numeracy Plan", "COMPLIANT", date(2025, 8, 1), "Primary Head", "ANNUAL"),
                ("FINANCIAL", "Annual Fee Regulation Compliance", "PENDING", date(2026, 9, 30), "Finance Director", "ANNUAL"),
                ("FINANCIAL", "RTE 25% Quota Admission Report", "COMPLIANT", date(2026, 4, 30), "Admissions Head", "ANNUAL"),
                ("DATA", "Student Data Privacy Policy Review", "IN_PROGRESS", date(2026, 5, 1), "IT Admin", "ANNUAL"),
                ("IB", "IB Standards & Practices Self-Study", "IN_PROGRESS", date(2026, 6, 1), "IB Coordinator", "ONE_TIME"),
                ("SAFETY", "Building Accessibility Audit", "NON_COMPLIANT", date(2026, 3, 1), "Facilities Manager", "ONE_TIME"),
                ("OTHER", "Staff Background Verification", "IN_PROGRESS", date(2026, 4, 30), "HR Manager", "ANNUAL"),
            ]
            for category, name, status, due, responsible, recurrence in items:
                _, created = ComplianceItem.objects.get_or_create(
                    tenant=tenant,
                    name=name,
                    category=category,
                    defaults={
                        "status": status,
                        "due_date": due,
                        "responsible_person": responsible,
                        "recurrence": recurrence,
                        "notes": f"Auto-seeded for demo",
                    },
                )
                if created:
                    compliance_count += 1
            self.stdout.write(f"        {compliance_count} compliance items created.")
        except (ImportError, Exception) as e:
            self.stdout.write(f"        Skipping compliance: {e}")

        # ── Done ─────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*60}\n"
            f"  Keystone complete data seeded!\n"
            f"  Teaching Assignments: {ta_count}\n"
            f"  Students Assigned: {student_count}\n"
            f"  Staff Certifications: {cert_count}\n"
            f"  Accreditations: {accred_count}\n"
            f"  Compliance Items: {compliance_count}\n"
            f"{'='*60}\n"
        ))
