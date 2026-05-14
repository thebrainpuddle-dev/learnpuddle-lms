"""
Sync production Keystone tenant data to match local development.
Creates all missing: students, skills, badges, certifications, accreditations,
compliance, rankings, discussions, groups, gamification, course skills, MAIC classrooms, chatbots.

Idempotent — safe to run multiple times.
"""
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Full sync of Keystone demo data to match local development"

    def handle(self, *args, **options):
        from apps.tenants.models import Tenant
        from apps.users.models import User
        from apps.academics.models import Grade, Section, Subject, TeachingAssignment
        from apps.courses.models import Course

        try:
            tenant = Tenant.objects.get(subdomain="keystone")
        except Tenant.DoesNotExist:
            self.stderr.write("Keystone tenant not found.")
            return

        now = timezone.now()

        def get_user(email):
            try:
                return User.objects.all_tenants().get(email=email, tenant=tenant)
            except User.DoesNotExist:
                return None

        def get_course(title):
            try:
                return Course.objects.filter(tenant=tenant, title=title).first()
            except Exception:
                return None

        admin = get_user("admin@keystoneeducation.in")
        priya = get_user("priya.sharma@keystoneeducation.in")
        raj = get_user("raj.patel@keystoneeducation.in")
        anita = get_user("anita.desai@keystoneeducation.in")
        vikram = get_user("vikram.singh@keystoneeducation.in")
        teacher = get_user("teacher@keystoneeducation.in")

        # ── 1. CREATE MISSING STUDENTS ─────────────────────────────────
        self.stdout.write("\n[1/12] Creating missing students...")
        student_data = [
            ("daksh.agarwal@keystoneeducation.in", "Daksh", "Agarwal", "", "A"),
            ("rishi.banerjee@keystoneeducation.in", "Rishi", "Banerjee", "", "A"),
            ("devika.bhat@keystoneeducation.in", "Devika", "Bhat", "", "A"),
            ("uday.bhatt@keystoneeducation.in", "Uday", "Bhatt", "", "B"),
            ("lavanya.bose@keystoneeducation.in", "Lavanya", "Bose", "", "B"),
            ("jiya.chauhan@keystoneeducation.in", "Jiya", "Chauhan", "", "B"),
            ("manav.choudhary@keystoneeducation.in", "Manav", "Choudhary", "", "A"),
            ("nandini.das@keystoneeducation.in", "Nandini", "Das", "", "A"),
            ("yash.dubey@keystoneeducation.in", "Yash", "Dubey", "", "B"),
            ("ishan.ghosh@keystoneeducation.in", "Ishan", "Ghosh", "", "B"),
            ("nishka.goswami@keystoneeducation.in", "Nishka", "Goswami", "", "B"),
            ("rohan.gupta@keystoneeducation.in", "Rohan", "Gupta", "KIS-S005", "A"),
            ("kavya.hegde@keystoneeducation.in", "Kavya", "Hegde", "", "A"),
            ("neha.iyer@keystoneeducation.in", "Neha", "Iyer", "KIS-S004", "A"),
            ("kunal.jain@keystoneeducation.in", "Kunal", "Jain", "", "A"),
            ("ananya.joshi@keystoneeducation.in", "Ananya", "Joshi", "", "A"),
            ("diya.kapoor@keystoneeducation.in", "Diya", "Kapoor", "KIS-S002", "A"),
            ("ritika.kaur@keystoneeducation.in", "Ritika", "Kaur", "", "B"),
            ("zara.khan@keystoneeducation.in", "Zara", "Khan", "", "B"),
            ("gaurav.khanna@keystoneeducation.in", "Gaurav", "Khanna", "", "B"),
            ("pooja.kulkarni@keystoneeducation.in", "Pooja", "Kulkarni", "", "A"),
            ("aryan.kumar@keystoneeducation.in", "Aryan", "Kumar", "", "A"),
            ("chirag.malhotra@keystoneeducation.in", "Chirag", "Malhotra", "", "B"),
            ("aarav.mehta@keystoneeducation.in", "Aarav", "Mehta", "KIS-S001", "B"),
            ("charvi.menon@keystoneeducation.in", "Charvi", "Menon", "", "A"),
            ("hridya.menon@keystoneeducation.in", "Hridya", "Menon", "", "B"),
            ("saanvi.mishra@keystoneeducation.in", "Saanvi", "Mishra", "", "B"),
            ("falguni.modi@keystoneeducation.in", "Falguni", "Modi", "", "B"),
            ("karthik.mohan@keystoneeducation.in", "Karthik", "Mohan", "", "B"),
            ("jayesh.naik@keystoneeducation.in", "Jayesh", "Naik", "", "A"),
            ("advait.nair@keystoneeducation.in", "Advait", "Nair", "", "A"),
            ("bhumi.nanda@keystoneeducation.in", "Bhumi", "Nanda", "", "B"),
            ("om.pandey@keystoneeducation.in", "Om", "Pandey", "", "A"),
            ("gauri.pillai@keystoneeducation.in", "Gauri", "Pillai", "", "A"),
            ("esha.rao@keystoneeducation.in", "Esha", "Rao", "", "A"),
            ("eklavya.rathore@keystoneeducation.in", "Eklavya", "Rathore", "", "B"),
            ("aditya.rawat@keystoneeducation.in", "Aditya", "Rawat", "", "B"),
            ("arjun.reddy@keystoneeducation.in", "Arjun", "Reddy", "KIS-S003", "B"),
            ("bhavya.reddy@keystoneeducation.in", "Bhavya", "Reddy", "", "A"),
            ("ishita.saxena@keystoneeducation.in", "Ishita", "Saxena", "", "A"),
            ("divya.sen@keystoneeducation.in", "Divya", "Sen", "", "B"),
            ("pranav.sethi@keystoneeducation.in", "Pranav", "Sethi", "", "B"),
            ("vedika.shetty@keystoneeducation.in", "Vedika", "Shetty", "", "B"),
            ("mihir.sinha@keystoneeducation.in", "Mihir", "Sinha", "", "B"),
            ("lakshmi.suresh@keystoneeducation.in", "Lakshmi", "Suresh", "", "A"),
            ("farhan.syed@keystoneeducation.in", "Farhan", "Syed", "", "A"),
            ("tanvi.thakur@keystoneeducation.in", "Tanvi", "Thakur", "", "B"),
            ("harsh.tiwari@keystoneeducation.in", "Harsh", "Tiwari", "", "A"),
            ("aanya.verma@keystoneeducation.in", "Aanya", "Verma", "", "A"),
        ]

        # Find Grade 10 sections A and B
        grade10 = Grade.objects.filter(tenant=tenant, name__icontains="grade 10").first()
        if not grade10:
            grade10 = Grade.objects.filter(tenant=tenant, name__icontains="g10").first()

        sec_a = sec_b = None
        if grade10:
            sec_a = Section.objects.filter(grade=grade10, name="A").first()
            sec_b = Section.objects.filter(grade=grade10, name="B").first()

        student_count = 0
        for email, first, last, sid, sec_name in student_data:
            if User.objects.all_tenants().filter(email=email, tenant=tenant).exists():
                # Update section assignment if needed
                u = User.objects.all_tenants().get(email=email, tenant=tenant)
                target_sec = sec_a if sec_name == "A" else sec_b
                if target_sec and u.section_fk != target_sec:
                    u.section_fk = target_sec
                    u.grade_fk = grade10
                    if sid:
                        u.student_id = sid
                    u.save(update_fields=["section_fk", "grade_fk", "student_id"])
                continue
            section = sec_a if sec_name == "A" else sec_b
            u = User(
                email=email,
                first_name=first,
                last_name=last,
                tenant=tenant,
                role="STUDENT",
                is_active=True,
                email_verified=True,
                section_fk=section,
                grade_fk=grade10,
            )
            if sid:
                u.student_id = sid
            u.set_password("Student@123")
            u.save()
            student_count += 1

        # Also ensure student@keystoneeducation.in has correct name and section
        student_user = get_user("student@keystoneeducation.in")
        if student_user and sec_b and student_user.section_fk != sec_b:
            student_user.first_name = "Arjun"
            student_user.last_name = "Patel"
            student_user.section_fk = sec_b
            student_user.grade_fk = grade10
            student_user.save(update_fields=["first_name", "last_name", "section_fk", "grade_fk"])

        self.stdout.write(f"  {student_count} new students created. All in Grade 10 A/B.")

        # ── 2. MISSING SKILLS ──────────────────────────────────────────
        self.stdout.write("[2/12] Creating missing skills...")
        from apps.progress.models import Skill
        missing_skills = [
            ("Assessment Design", "Assessment", 3),
            ("Data Literacy", "Assessment", 2),
            ("IB Curriculum Knowledge", "Curriculum", 4),
            ("AI & EdTech Literacy", "Digital Skills", 2),
            ("Scientific Communication", "Subject Expertise", 3),
            ("Classroom Management", "Teaching Methods", 2),
            ("Collaborative Learning Design", "Teaching Methods", 2),
            ("Differentiated Instruction", "Teaching Methods", 3),
            ("Inquiry-Based Pedagogy", "Teaching Methods", 3),
        ]
        skill_count = 0
        for name, cat, level_req in missing_skills:
            _, created = Skill.objects.get_or_create(
                tenant=tenant, name=name,
                defaults={"category": cat, "level_required": level_req},
            )
            if created:
                skill_count += 1
        self.stdout.write(f"  {skill_count} skills created.")

        # ── 3. MISSING BADGES ──────────────────────────────────────────
        self.stdout.write("[3/12] Creating missing badge definitions...")
        from apps.progress.models import BadgeDefinition
        missing_badges = [
            ("Quick Learner", "milestone", "content_completed", 5, "zap", "#F59E0B", 2),
            ("Course Champion", "completion", "courses_completed", 1, "trophy", "#EF4444", 4),
            ("On Fire", "streak", "streak_days", 3, "flame", "#F97316", 5),
            ("Unstoppable", "streak", "streak_days", 7, "rocket", "#EC4899", 6),
            ("XP Milestone: 50", "milestone", "xp_threshold", 50, "star", "#8B5CF6", 7),
            ("XP Milestone: 200", "milestone", "xp_threshold", 200, "award", "#06B6D4", 8),
            ("Quiz Ace", "skill", "manual", 0, "check-circle", "#14B8A6", 9),
            ("Trailblazer", "special", "manual", 0, "compass", "#D946EF", 10),
        ]
        badge_count = 0
        for name, cat, ctype, cval, icon, color, sort in missing_badges:
            _, created = BadgeDefinition.objects.get_or_create(
                tenant=tenant, name=name,
                defaults={
                    "category": cat,
                    "criteria_type": ctype,
                    "criteria_value": cval,
                    "icon": icon,
                    "color": color,
                    "sort_order": sort,
                },
            )
            if created:
                badge_count += 1
        self.stdout.write(f"  {badge_count} badges created.")

        # ── 4. STAFF CERTIFICATIONS (replace with local data) ──────────
        self.stdout.write("[4/12] Syncing staff certifications...")
        from apps.tenants.accreditation_models import StaffCertification
        # Delete existing and recreate from local data
        StaffCertification.objects.filter(tenant=tenant).delete()
        local_certs = [
            ("anita.desai@keystoneeducation.in", "CHILD_SAFEGUARDING", "NOT_STARTED", "2024-06-15", "2025-06-15", "School Internal Training"),
            ("anita.desai@keystoneeducation.in", "FIRE_SAFETY", "NOT_STARTED", "2024-11-05", "2025-11-05", "Karnataka Fire Dept"),
            ("anita.desai@keystoneeducation.in", "FIRST_AID", "NOT_STARTED", "2024-01-20", "2026-01-20", "Indian Red Cross Society"),
            ("anita.desai@keystoneeducation.in", "GOOGLE_CERT", "NOT_STARTED", "2023-09-01", "2026-09-01", "Google for Education"),
            ("anita.desai@keystoneeducation.in", "IB_CAT1", "NOT_STARTED", "2021-03-15", None, "IB Asia Pacific"),
            ("anita.desai@keystoneeducation.in", "IB_CAT2", "NOT_STARTED", "2023-07-20", None, "IB Asia Pacific"),
            ("anita.desai@keystoneeducation.in", "POCSO", "NOT_STARTED", "2024-08-10", "2025-08-10", "Childline India Foundation"),
            ("priya.sharma@keystoneeducation.in", "CHILD_SAFEGUARDING", "NOT_STARTED", "2024-06-15", "2025-06-15", "School Internal Training"),
            ("teacher@keystoneeducation.in", "FIRE_SAFETY", "NOT_STARTED", "2024-11-05", "2025-11-05", "Karnataka Fire Dept"),
            ("priya.sharma@keystoneeducation.in", "FIRE_SAFETY", "NOT_STARTED", "2024-11-05", "2025-11-05", "Karnataka Fire Dept"),
            ("priya.sharma@keystoneeducation.in", "FIRST_AID", "NOT_STARTED", "2024-01-20", "2026-01-20", "Indian Red Cross Society"),
            ("teacher@keystoneeducation.in", "IB_CAT1", "NOT_STARTED", "2024-11-01", None, "IB Asia Pacific"),
            ("priya.sharma@keystoneeducation.in", "IB_CAT1", "NOT_STARTED", "2019-04-20", None, "IB Asia Pacific"),
            ("priya.sharma@keystoneeducation.in", "IB_CAT2", "NOT_STARTED", "2021-11-15", None, "IB Asia Pacific"),
            ("priya.sharma@keystoneeducation.in", "IB_CAT3", "NOT_STARTED", "2024-03-01", None, "IB Online - Self-paced"),
            ("priya.sharma@keystoneeducation.in", "IB_LEADER", "NOT_STARTED", "2023-01-10", None, "IB Global Conference"),
            ("priya.sharma@keystoneeducation.in", "POCSO", "NOT_STARTED", "2024-08-10", "2025-08-10", "Childline India Foundation"),
            ("teacher@keystoneeducation.in", "POCSO", "NOT_STARTED", "2024-08-10", "2025-08-10", "Childline India Foundation"),
            ("priya.sharma@keystoneeducation.in", "POSH", "NOT_STARTED", "2024-09-01", "2025-09-01", "POSH India"),
            ("raj.patel@keystoneeducation.in", "FIRE_SAFETY", "NOT_STARTED", "2024-11-05", "2025-11-05", "Karnataka Fire Dept"),
            ("raj.patel@keystoneeducation.in", "IB_CAT1", "NOT_STARTED", "2022-06-10", None, "IB Asia Pacific"),
            ("raj.patel@keystoneeducation.in", "POCSO", "NOT_STARTED", "2024-08-10", "2025-08-10", "Childline India Foundation"),
            ("vikram.singh@keystoneeducation.in", "CHILD_SAFEGUARDING", "NOT_STARTED", "2025-01-10", "2026-01-10", "School Internal Training"),
            ("vikram.singh@keystoneeducation.in", "DIGITAL_LITERACY", "NOT_STARTED", "2024-04-15", "2025-06-15", "Microsoft Education"),
            ("vikram.singh@keystoneeducation.in", "FIRE_SAFETY", "NOT_STARTED", "2024-11-05", "2025-11-05", "Karnataka Fire Dept"),
            ("vikram.singh@keystoneeducation.in", "FIRST_AID", "NOT_STARTED", "2022-03-10", "2024-03-10", "Indian Red Cross Society"),
            ("vikram.singh@keystoneeducation.in", "IB_CAT1", "NOT_STARTED", "2020-08-15", None, "IB Asia Pacific"),
            ("vikram.singh@keystoneeducation.in", "IB_CAT2", "NOT_STARTED", "2022-12-10", None, "IB Online"),
            ("vikram.singh@keystoneeducation.in", "NEP_TRAINING", "NOT_STARTED", "2024-07-01", None, "NCERT Online"),
            ("vikram.singh@keystoneeducation.in", "POCSO", "NOT_STARTED", "2023-05-20", "2024-05-20", "Childline India Foundation"),
        ]
        cert_count = 0
        for email, ctype, status, completed, expiry, provider in local_certs:
            t_user = get_user(email)
            if not t_user:
                continue
            StaffCertification.objects.create(
                tenant=tenant,
                teacher=t_user,
                certification_type=ctype,
                status=status,
                completed_date=date.fromisoformat(completed) if completed else None,
                expiry_date=date.fromisoformat(expiry) if expiry else None,
                provider=provider,
            )
            cert_count += 1
        self.stdout.write(f"  {cert_count} certifications synced.")

        # ── 5. ACCREDITATIONS (replace with local data) ────────────────
        self.stdout.write("[5/12] Syncing accreditations...")
        from apps.tenants.accreditation_models import SchoolAccreditation, AccreditationMilestone
        # Delete and recreate
        SchoolAccreditation.objects.filter(tenant=tenant).delete()
        local_accreds = [
            {
                "accreditation_type": "NABET", "status": "AUTHORIZED",
                "valid_from": date(2023, 6, 1), "valid_to": date(2026, 5, 31),
                "issuing_body": "NABET (QCI)", "renewal_cycle_months": 36,
                "notes": "Quality Council of India — NABET Accreditation for school improvement",
                "milestones": [
                    ("Initial Application", "COMPLETED", date(2023, 2, 1)),
                    ("School Visit", "COMPLETED", date(2023, 5, 15)),
                    ("Accreditation Granted", "COMPLETED", date(2023, 6, 1)),
                    ("Annual Report", "PENDING", date(2026, 6, 1)),
                ],
            },
            {
                "accreditation_type": "CIS", "status": "CONSIDERATION",
                "valid_from": None, "valid_to": None,
                "issuing_body": "Council of International Schools", "renewal_cycle_months": 60,
                "notes": "Preliminary interest stage — exploring CIS membership",
                "milestones": [
                    ("Preliminary Visit", "PENDING", date(2026, 3, 1)),
                ],
            },
            {
                "accreditation_type": "CBSE", "status": "AUTHORIZED",
                "affiliation_number": "830456",
                "valid_from": date(2015, 4, 1), "valid_to": date(2030, 3, 31),
                "issuing_body": "CBSE", "renewal_cycle_months": 60,
                "notes": "CBSE affiliation up to Senior Secondary level",
                "milestones": [
                    ("Affiliation Granted", "COMPLETED", date(2015, 4, 1)),
                    ("Extension Granted", "COMPLETED", date(2020, 3, 31)),
                    ("Inspection Visit", "COMPLETED", date(2023, 11, 15)),
                    ("Next Renewal", "PENDING", date(2030, 3, 31)),
                ],
            },
            {
                "accreditation_type": "IB_MYP", "status": "CANDIDACY",
                "valid_from": None, "valid_to": None,
                "issuing_body": "IBO", "renewal_cycle_months": 60,
                "notes": "MYP candidacy applied — awaiting authorization visit",
                "milestones": [
                    ("Application Submitted", "COMPLETED", date(2025, 1, 15)),
                    ("Candidacy Granted", "IN_PROGRESS", date(2025, 6, 1)),
                ],
            },
            {
                "accreditation_type": "IB_PYP", "status": "AUTHORIZED",
                "valid_from": date(2019, 8, 15), "valid_to": date(2025, 8, 15),
                "issuing_body": "IBO", "renewal_cycle_months": 60,
                "notes": "PYP authorization — evaluation visit due for renewal",
                "milestones": [
                    ("Authorization Granted", "COMPLETED", date(2019, 8, 15)),
                    ("Self-Study", "COMPLETED", date(2024, 2, 1)),
                    ("Programme Evaluation Visit", "PENDING", date(2025, 8, 1)),
                ],
            },
        ]
        accred_count = 0
        for a in local_accreds:
            milestones = a.pop("milestones")
            obj = SchoolAccreditation.objects.create(tenant=tenant, **a)
            accred_count += 1
            for idx, (title, status, target) in enumerate(milestones):
                AccreditationMilestone.objects.create(
                    accreditation=obj, title=title, status=status,
                    due_date=target,
                    completed_date=target if status == "COMPLETED" else None,
                    order=idx,
                )
        self.stdout.write(f"  {accred_count} accreditations with milestones synced.")

        # ── 6. COMPLIANCE ITEMS (replace with local data) ──────────────
        self.stdout.write("[6/12] Syncing compliance items...")
        from apps.tenants.accreditation_models import ComplianceItem
        ComplianceItem.objects.filter(tenant=tenant).delete()
        local_compliance = [
            ("BOARD", "RTE 25% EWS Quota Compliance", "COMPLIANT", "2025-07-31", "Admissions Director", "ANNUAL"),
            ("BOARD", "UDISE+ Data Submission 2024-25", "COMPLIANT", "2025-09-30", "Data Entry Coordinator", "ANNUAL"),
            ("BOARD", "CBSE Affiliation Extension Application", "COMPLIANT", "2025-03-31", "Principal", "ONE_TIME"),
            ("BOARD", "CBSE Mandatory Disclosures on Website", "PENDING", "2026-07-31", "IT Admin", "ANNUAL"),
            ("BOARD", "Annual Affidavit Submission to CBSE", "PENDING", "2026-09-30", "Admin Office", "ANNUAL"),
            ("BOARD", "UDISE+ Annual Update", "PENDING", "2026-09-30", "Data Entry Coordinator", "ANNUAL"),
            ("BOARD", "RTE 25% Quota Admission Report", "PENDING", "2026-04-30", "Admissions Head", "ANNUAL"),
            ("DATA", "DPDPA 2023 Compliance Readiness", "IN_PROGRESS", "2026-05-29", "IT Head & Legal Counsel", "ONE_TIME"),
            ("DATA", "Student Data Privacy Policy Review", "PENDING", "2026-06-30", "IT Admin", "ANNUAL"),
            ("DATA", "Website Privacy Policy Update", "PENDING", "2026-06-30", "IT Admin", "ANNUAL"),
            ("FINANCIAL", "GST Registration & Filing", "COMPLIANT", "2025-12-31", "Finance Team", "QUARTERLY"),
            ("FINANCIAL", "Fee Regulation Compliance", "COMPLIANT", "2025-06-30", "Finance Director", "ANNUAL"),
            ("FINANCIAL", "Fee Regulation Annual Filing", "PENDING", "2026-06-30", "Finance Director", "ANNUAL"),
            ("FINANCIAL", "Annual Financial Audit", "PENDING", "2026-09-30", "External Auditor", "ANNUAL"),
            ("FINANCIAL", "Trust/Society Registration Renewal", "PENDING", "2026-12-31", "Legal Counsel", "ONE_TIME"),
            ("IB", "ATL Skills Framework Implementation", "PENDING", "2025-06-30", "IB Coordinator", "ONE_TIME"),
            ("IB", "IB PYP Authorization Renewal", "IN_PROGRESS", "2025-07-01", "IB Coordinator", "ONE_TIME"),
            ("IB", "IB Programme Evaluation Preparation", "IN_PROGRESS", "2025-08-10", "IB Coordinator", "ONE_TIME"),
            ("NEP", "NEP 5+3+3+4 Structure Mapping", "IN_PROGRESS", "2026-07-13", "Academic Director", "ONE_TIME"),
            ("NEP", "Competency-Based Assessment Framework", "PENDING", "2026-09-11", "Assessment Coordinator", "ONE_TIME"),
            ("NEP", "Competency-Based Assessment Pilot", "IN_PROGRESS", "2026-03-31", "Assessment Coordinator", "ANNUAL"),
            ("NEP", "Vocational Education Integration (Grade 6+)", "PENDING", "2026-07-31", "Academic Director", "ONE_TIME"),
            ("NEP", "Multilingual Instruction Policy", "COMPLIANT", "2025-06-30", "Language Dept Head", "ANNUAL"),
            ("NEP", "Holistic Report Card Implementation", "PENDING", "2026-03-31", "Academic Coordinator", "ANNUAL"),
            ("NEP", "5+3+3+4 Structure Plan", "IN_PROGRESS", "2026-07-31", "Principal", "ONE_TIME"),
            ("NEP", "Multilingual Instruction Compliance", "PENDING", "2026-06-30", "Language Dept Head", "ANNUAL"),
            ("SAFETY", "School Bus Fitness Certificate Renewal", "NON_COMPLIANT", "2026-03-30", "Transport Manager", "ANNUAL"),
            ("SAFETY", "POCSO Awareness Training for Staff", "IN_PROGRESS", "2026-06-13", "HR & Child Protection Officer", "ANNUAL"),
            ("SAFETY", "Water Quality & Sanitation Compliance", "COMPLIANT", "2025-07-31", "Facilities Team", "QUARTERLY"),
            ("SAFETY", "POSH Internal Committee", "COMPLIANT", "2025-12-31", "HR Director", "ANNUAL"),
            ("SAFETY", "Building Stability Certificate", "COMPLIANT", "2025-06-30", "Facilities Manager", "ONE_TIME"),
            ("SAFETY", "Fire Safety NOC Renewal", "PENDING", "2026-06-30", "Facilities Manager", "ANNUAL"),
            ("SAFETY", "CCTV & Security Audit", "PENDING", "2026-06-30", "Security Head", "ANNUAL"),
            ("SAFETY", "First Aid & Medical Room Compliance", "PENDING", "2026-04-30", "School Nurse", "ANNUAL"),
            ("SAFETY", "POCSO Compliance Audit", "PENDING", "2026-06-30", "Child Protection Officer", "ANNUAL"),
            ("SAFETY", "Building Safety Certificate Renewal", "PENDING", "2026-12-31", "Facilities Manager", "ANNUAL"),
            ("OTHER", "Staff Background Verification", "IN_PROGRESS", "2026-04-30", "HR Manager", "ANNUAL"),
        ]
        comp_count = 0
        for cat, name, status, due, resp, recurrence in local_compliance:
            ComplianceItem.objects.create(
                tenant=tenant, name=name, category=cat, status=status,
                due_date=date.fromisoformat(due), responsible_person=resp,
                recurrence=recurrence,
            )
            comp_count += 1
        self.stdout.write(f"  {comp_count} compliance items synced.")

        # ── 7. RANKING ENTRIES ─────────────────────────────────────────
        self.stdout.write("[7/12] Seeding ranking entries...")
        from apps.tenants.accreditation_models import RankingEntry
        from decimal import Decimal
        rankings = [
            ("EducationToday", 2025, 35, "Top IB Schools in India", None),
            ("EducationWorld (EWISR)", 2025, 42, "Top International Day Schools", Decimal("78.50")),
            ("India Today", 2025, 15, "Top International Schools - South India", Decimal("85.30")),
            ("Times School Survey", 2025, 8, "Best IB Schools - Bengaluru", Decimal("82.00")),
            ("EducationWorld (EWISR)", 2024, 48, "Top International Day Schools", Decimal("74.20")),
            ("India Today", 2024, 18, "Top International Schools - South India", Decimal("82.10")),
            ("Times School Survey", 2024, 11, "Best IB Schools - Bengaluru", Decimal("79.00")),
            ("EducationWorld (EWISR)", 2023, 55, "Top International Day Schools", Decimal("70.10")),
        ]
        rank_count = 0
        for platform, year, rank, cat, score in rankings:
            _, created = RankingEntry.objects.get_or_create(
                tenant=tenant, platform=platform, year=year, category=cat,
                defaults={"rank": rank, "score": score},
            )
            if created:
                rank_count += 1
        self.stdout.write(f"  {rank_count} ranking entries created.")

        # ── 8. TEACHER GROUPS ──────────────────────────────────────────
        self.stdout.write("[8/12] Creating teacher groups...")
        from apps.courses.models import TeacherGroup
        groups = [
            ("IB Cat 1 Workshop Required", "CUSTOM", ["raj.patel@keystoneeducation.in", "teacher@keystoneeducation.in"]),
            ("IB Leadership Team", "CUSTOM", ["anita.desai@keystoneeducation.in", "priya.sharma@keystoneeducation.in", "vikram.singh@keystoneeducation.in"]),
            ("IB PYP Teachers", "DEPARTMENT", ["anita.desai@keystoneeducation.in", "raj.patel@keystoneeducation.in", "teacher@keystoneeducation.in", "priya.sharma@keystoneeducation.in", "vikram.singh@keystoneeducation.in"]),
            ("Languages & Humanities Faculty", "SUBJECT", ["anita.desai@keystoneeducation.in", "priya.sharma@keystoneeducation.in", "teacher@keystoneeducation.in"]),
            ("NEP 2020 Implementation Committee", "CUSTOM", ["anita.desai@keystoneeducation.in", "raj.patel@keystoneeducation.in", "vikram.singh@keystoneeducation.in"]),
            ("Safety Certification Group", "CUSTOM", ["anita.desai@keystoneeducation.in", "raj.patel@keystoneeducation.in", "teacher@keystoneeducation.in", "priya.sharma@keystoneeducation.in", "vikram.singh@keystoneeducation.in"]),
            ("Science & Math Faculty", "SUBJECT", ["raj.patel@keystoneeducation.in", "vikram.singh@keystoneeducation.in"]),
        ]
        group_count = 0
        for name, gtype, member_emails in groups:
            grp, created = TeacherGroup.objects.get_or_create(
                tenant=tenant, name=name,
                defaults={"group_type": gtype},
            )
            if created:
                group_count += 1
                for em in member_emails:
                    u = get_user(em)
                    if u:
                        grp.members.add(u)
        self.stdout.write(f"  {group_count} teacher groups created.")

        # ── 9. DISCUSSION THREADS + REPLIES + LIKES ────────────────────
        self.stdout.write("[9/12] Creating discussions...")
        try:
            from apps.discussions.models import DiscussionThread, DiscussionReply, DiscussionLike

            atl_course = get_course("IB Approaches to Learning (ATL)")
            if not atl_course:
                self.stdout.write("  Skipping discussions: ATL course not found.")
            elif DiscussionThread.objects.filter(tenant=tenant).exists():
                self.stdout.write("  Discussion threads already exist, skipping.")
            else:
                threads_data = [
                    {
                        "title": "Can someone explain electromagnetic induction simply?",
                        "body": "I'm struggling with Faraday's law and Lenz's law. The textbook explanation is confusing - can someone break it down in simpler terms? Especially the part about the direction of induced current.",
                        "author": "daksh.agarwal@keystoneeducation.in",
                        "is_pinned": False, "view_count": 44,
                        "replies": [
                            ("rishi.banerjee@keystoneeducation.in", "Think of it like Newton's third law but for magnets! When you push a magnet through a coil, the coil 'pushes back' by creating its own magnetic field. That's Lenz's law in a nutshell. The induced current always opposes the change that caused it.", ["uday.bhatt@", "lavanya.bose@", "devika.bhat@", "daksh.agarwal@", "jiya.chauhan@"]),
                            ("devika.bhat@keystoneeducation.in", "The video at 3:45 has a good animation that really helped me visualize the flux lines. Try watching it at 0.75x speed.", ["daksh.agarwal@", "rishi.banerjee@", "jiya.chauhan@", "uday.bhatt@"]),
                            ("priya.sharma@keystoneeducation.in", "Great explanations! Think about it this way: nature is lazy. It resists change. When magnetic flux through a loop changes, the induced current creates its own magnetic field to oppose that change. That's ALL Lenz's law is.", ["daksh.agarwal@", "lavanya.bose@", "uday.bhatt@", "rishi.banerjee@"]),
                            ("daksh.agarwal@keystoneeducation.in", "Oh that makes so much sense now! The 'nature is lazy' analogy really clicks. Thanks everyone!", []),
                        ],
                    },
                    {
                        "title": "Study group for the waves unit test?",
                        "body": "Hey everyone! The waves unit test is next Thursday. Would anyone be interested in forming a study group? We could meet in the library after school on Tuesday. I'm particularly confused about standing waves and harmonics.",
                        "author": "manav.choudhary@keystoneeducation.in",
                        "is_pinned": True, "view_count": 25,
                        "replies": [
                            ("rishi.banerjee@keystoneeducation.in", "I'm in! I'm good with standing waves but need help with the Doppler effect. We could teach each other.", ["devika.bhat@", "daksh.agarwal@", "jiya.chauhan@"]),
                            ("nandini.das@keystoneeducation.in", "Count me in too. Can we do Tuesday and Thursday? That gives us two sessions before the test.", []),
                            ("devika.bhat@keystoneeducation.in", "I'll join! I made flashcards for all the wave equations - happy to share them with the group.", ["jiya.chauhan@", "rishi.banerjee@"]),
                            ("priya.sharma@keystoneeducation.in", "Love seeing this initiative! I'll reserve the physics lab for you on Tuesday 3:30-5pm. I can drop in to answer questions too.", ["uday.bhatt@"]),
                        ],
                    },
                    {
                        "title": "Confusion about vector vs scalar quantities",
                        "body": "Why does it matter if something is a vector or scalar? Like, speed vs velocity - aren't they basically the same thing? When would the direction actually matter in a real physics problem?",
                        "author": "uday.bhatt@keystoneeducation.in",
                        "is_pinned": False, "view_count": 40,
                        "replies": [
                            ("lavanya.bose@keystoneeducation.in", "They're different! Speed is just how fast you go, but velocity includes direction. If you run around a track and end up where you started, your average velocity is ZERO even though your speed wasn't.", ["daksh.agarwal@", "uday.bhatt@", "devika.bhat@", "jiya.chauhan@", "rishi.banerjee@"]),
                            ("jiya.chauhan@keystoneeducation.in", "It matters a lot in real physics! If you throw a ball straight up, gravity (a vector) changes the velocity direction. Without vectors, you can't predict where the ball goes. Forces, momentum, electric fields - all vectors.", ["daksh.agarwal@", "uday.bhatt@", "rishi.banerjee@", "devika.bhat@"]),
                            ("priya.sharma@keystoneeducation.in", "Perfect examples from Lavanya and Jiya! Here's another: the ISS orbits Earth at a constant speed (~28,000 km/h) but its velocity is always changing because its direction changes. That changing velocity = centripetal acceleration. Vectors make this make sense.", []),
                        ],
                    },
                    {
                        "title": "Physics joke thread (for stress relief before exams)",
                        "body": "We all need a laugh before the exam. Drop your best physics jokes below! I'll start: A photon checks into a hotel. The bellhop asks 'Can I help with your luggage?' The photon says 'No thanks, I'm traveling light.'",
                        "author": "devika.bhat@keystoneeducation.in",
                        "is_pinned": False, "view_count": 28,
                        "replies": [
                            ("nandini.das@keystoneeducation.in", "A neutron walks into a bar and asks 'How much for a drink?' The bartender says 'For you, no charge!'", ["devika.bhat@", "daksh.agarwal@", "rishi.banerjee@"]),
                            ("daksh.agarwal@keystoneeducation.in", "Schrodinger's cat walks into a bar. And doesn't.", ["lavanya.bose@"]),
                            ("rishi.banerjee@keystoneeducation.in", "Knock knock. Who's there? Heisenberg. Heisenberg who? You can't know both who I am and where I am at the same time! ...okay I'll see myself out. Let me atom!", ["lavanya.bose@", "devika.bhat@", "daksh.agarwal@", "jiya.chauhan@", "uday.bhatt@"]),
                            ("priya.sharma@keystoneeducation.in", "Why did the photon refuse to check luggage? Because it was traveling light! Wait... Devika already used that one. Okay - why can't you trust atoms? Because they make up everything!", ["rishi.banerjee@", "uday.bhatt@", "daksh.agarwal@"]),
                        ],
                    },
                    {
                        "title": "Lab report: How do I write the evaluation section?",
                        "body": "I'm writing up the pendulum lab report and I'm stuck on the evaluation section. I know I need to talk about errors and improvements but I'm not sure what level of detail is expected for the IB criteria. Can anyone share tips?",
                        "author": "yash.dubey@keystoneeducation.in",
                        "is_pinned": False, "view_count": 23,
                        "replies": [
                            ("lavanya.bose@keystoneeducation.in", "You need to discuss what went wrong and why. Systematic errors (like air resistance, friction at the pivot) and random errors (timing with a stopwatch). Then suggest specific improvements - don't just say 'use better equipment', say HOW and WHY.", []),
                            ("priya.sharma@keystoneeducation.in", "Good start from Lavanya! For Criterion C (Processing & Evaluation) in IB, the key is: 1) Identify both systematic and random errors, 2) Estimate their impact on results, 3) Propose REALISTIC improvements (not 'go to space to remove gravity').", ["rishi.banerjee@"]),
                            ("uday.bhatt@keystoneeducation.in", "Thanks Ms. Sharma! Quick question - should we calculate percentage error or is qualitative discussion enough?", []),
                            ("priya.sharma@keystoneeducation.in", "Great question! Human reaction time is a RANDOM error (~0.2s). For a 2-second period, that's 10% uncertainty. For systematic errors like air resistance, discuss the direction of effect (does it make the period longer or shorter?). Both quantitative AND qualitative analysis will score well.", ["devika.bhat@", "rishi.banerjee@", "lavanya.bose@", "uday.bhatt@"]),
                            ("student@keystoneeducation.in", "hello", []),
                        ],
                    },
                ]

                thread_count = 0
                reply_count = 0
                like_count = 0
                section_a = sec_a
                section_b = sec_b

                for td in threads_data:
                    author = get_user(td["author"])
                    if not author:
                        continue
                    sec = section_a if td["author"] in [
                        "daksh.agarwal@keystoneeducation.in",
                        "manav.choudhary@keystoneeducation.in",
                        "devika.bhat@keystoneeducation.in",
                    ] else section_b

                    thread = DiscussionThread.objects.create(
                        tenant=tenant,
                        course=atl_course,
                        section=sec,
                        title=td["title"],
                        body=td["body"],
                        author=author,
                        is_pinned=td["is_pinned"],
                        view_count=td["view_count"],
                        reply_count=len(td["replies"]),
                        status="ACTIVE",
                    )
                    thread_count += 1

                    for reply_body_author_likes in td["replies"]:
                        r_email, r_body, r_likers = reply_body_author_likes
                        r_author = get_user(r_email)
                        if not r_author:
                            continue
                        reply = DiscussionReply.objects.create(
                            thread=thread,
                            body=r_body,
                            author=r_author,
                            like_count=len(r_likers),
                        )
                        reply_count += 1

                        for liker_prefix in r_likers:
                            # liker_prefix is like "daksh.agarwal@"
                            full_email = liker_prefix + "keystoneeducation.in" if not liker_prefix.endswith(".in") else liker_prefix
                            liker = get_user(full_email)
                            if liker:
                                DiscussionLike.objects.get_or_create(reply=reply, user=liker)
                                like_count += 1

                self.stdout.write(f"  {thread_count} threads, {reply_count} replies, {like_count} likes created.")
        except Exception as e:
            self.stdout.write(f"  Skipping discussions: {e}")

        # ── 10. COURSE SKILLS ──────────────────────────────────────────
        self.stdout.write("[10/12] Creating course skills...")
        from apps.progress.models import CourseSkill
        course_skills = [
            ("IB Approaches to Learning (ATL)", "IB Curriculum Knowledge", 3),
            ("IB Approaches to Learning (ATL)", "Inquiry-Based Pedagogy", 2),
            ("Data-Driven Decision Making", "Data Literacy", 3),
            ("Data-Driven Decision Making", "Assessment Design", 2),
            ("Inquiry-Based Science Teaching", "Inquiry-Based Pedagogy", 1),
            ("Inquiry-Based Science Teaching", "Scientific Communication", 1),
            ("Inquiry-Based Science Teaching", "Assessment Design", 3),
            ("Effective Classroom Communication", "Classroom Management", 2),
            ("Effective Classroom Communication", "Differentiated Instruction", 3),
            ("Effective Classroom Communication", "Collaborative Learning Design", 1),
            ("Introduction to Machine Learning", "Technology Integration", 2),
            ("Introduction to Machine Learning", "AI & EdTech Literacy", 3),
        ]
        cs_count = 0
        for course_title, skill_name, level in course_skills:
            c = get_course(course_title)
            s = Skill.objects.filter(tenant=tenant, name=skill_name).first()
            if c and s:
                _, created = CourseSkill.objects.get_or_create(
                    course=c, skill=s,
                    defaults={"level_taught": level},
                )
                if created:
                    cs_count += 1
        self.stdout.write(f"  {cs_count} course skills created.")

        # ── 11. GAMIFICATION SYNC (XP, badges, streaks, teacher skills, progress) ──
        self.stdout.write("[11/12] Syncing gamification data...")
        from apps.progress.models import (
            TeacherXPSummary, XPTransaction, TeacherBadge,
            TeacherStreak, TeacherSkill, TeacherProgress,
            LeaderboardSnapshot,
        )

        # Teacher XP Summaries
        xp_summaries = [
            ("raj.patel@keystoneeducation.in", 140, 2, "Associate Educator", 56, 21),
            ("teacher@keystoneeducation.in", 95, 1, "Associate Educator", 38, 14),
            ("anita.desai@keystoneeducation.in", 220, 4, "Associate Educator", 88, 33),
            ("vikram.singh@keystoneeducation.in", 60, 1, "Associate Educator", 24, 9),
            ("priya.sharma@keystoneeducation.in", 175, 3, "Senior Educator", 95, 40),
            ("student@keystoneeducation.in", 20, 1, "Associate Educator", 20, 20),
        ]
        xps_count = 0
        for email, total, level, level_name, monthly, weekly in xp_summaries:
            u = get_user(email)
            if not u:
                continue
            obj, created = TeacherXPSummary.objects.get_or_create(
                tenant=tenant, teacher=u,
                defaults={
                    "total_xp": total, "level": level, "level_name": level_name,
                    "xp_this_month": monthly, "xp_this_week": weekly,
                },
            )
            if not created:
                obj.total_xp = total
                obj.level = level
                obj.level_name = level_name
                obj.xp_this_month = monthly
                obj.xp_this_week = weekly
                obj.save()
            xps_count += 1
        self.stdout.write(f"  {xps_count} XP summaries synced.")

        # Teacher Streaks
        streaks = [
            ("raj.patel@keystoneeducation.in", 5, 14),
            ("anita.desai@keystoneeducation.in", 3, 10),
            ("vikram.singh@keystoneeducation.in", 2, 7),
            ("priya.sharma@keystoneeducation.in", 5, 8),
            ("student@keystoneeducation.in", 1, 1),
        ]
        streak_count = 0
        for email, current, longest in streaks:
            u = get_user(email)
            if not u:
                continue
            obj, created = TeacherStreak.objects.get_or_create(
                tenant=tenant, teacher=u,
                defaults={
                    "current_streak": current,
                    "longest_streak": longest,
                    "last_activity_date": now.date(),
                },
            )
            if not created:
                obj.current_streak = current
                obj.longest_streak = longest
                obj.last_activity_date = now.date()
                obj.save()
            streak_count += 1
        self.stdout.write(f"  {streak_count} streaks synced.")

        # Teacher Badges (add missing)
        badge_awards = [
            ("vikram.singh@keystoneeducation.in", "Course Pioneer", "Auto: courses_completed"),
            ("vikram.singh@keystoneeducation.in", "Century Club", "Auto: xp_threshold"),
            ("vikram.singh@keystoneeducation.in", "First Steps", "Auto: content_completed"),
            ("anita.desai@keystoneeducation.in", "Course Pioneer", "Auto: courses_completed"),
            ("anita.desai@keystoneeducation.in", "Century Club", "Auto: xp_threshold"),
            ("raj.patel@keystoneeducation.in", "Consistent Learner", "Auto: streak_days"),
            ("raj.patel@keystoneeducation.in", "Course Pioneer", "Auto: courses_completed"),
            ("raj.patel@keystoneeducation.in", "Century Club", "Auto: xp_threshold"),
            ("priya.sharma@keystoneeducation.in", "IB Practitioner", "Auto: manual"),
            ("priya.sharma@keystoneeducation.in", "Consistent Learner", "Auto: streak_days"),
            ("priya.sharma@keystoneeducation.in", "Curriculum Explorer", "Auto: courses_completed"),
            ("priya.sharma@keystoneeducation.in", "Course Pioneer", "Auto: courses_completed"),
            ("priya.sharma@keystoneeducation.in", "Century Club", "Auto: xp_threshold"),
            ("raj.patel@keystoneeducation.in", "Quick Learner", "Criteria met"),
            ("raj.patel@keystoneeducation.in", "First Steps", "Criteria met"),
            ("anita.desai@keystoneeducation.in", "Quick Learner", "Criteria met"),
            ("anita.desai@keystoneeducation.in", "First Steps", "Criteria met"),
            ("priya.sharma@keystoneeducation.in", "Quiz Ace", "Auto"),
            ("priya.sharma@keystoneeducation.in", "XP Milestone: 50", "Auto"),
            ("priya.sharma@keystoneeducation.in", "On Fire", "Auto"),
            ("priya.sharma@keystoneeducation.in", "Course Champion", "Auto"),
            ("priya.sharma@keystoneeducation.in", "Knowledge Seeker", "Auto"),
            ("priya.sharma@keystoneeducation.in", "Quick Learner", "Auto"),
            ("priya.sharma@keystoneeducation.in", "First Steps", "Auto"),
        ]
        tb_count = 0
        for email, badge_name, reason in badge_awards:
            u = get_user(email)
            badge_def = BadgeDefinition.objects.filter(tenant=tenant, name=badge_name).first()
            if u and badge_def:
                _, created = TeacherBadge.objects.get_or_create(
                    tenant=tenant, teacher=u, badge=badge_def,
                    defaults={"awarded_reason": reason},
                )
                if created:
                    tb_count += 1
        self.stdout.write(f"  {tb_count} teacher badges awarded.")

        # Teacher Skills (assign all 28 skills to all 5 teachers)
        all_skills = list(Skill.objects.filter(tenant=tenant))
        teachers_for_skills = [priya, raj, anita, vikram, teacher]
        ts_count = 0
        for t_user in teachers_for_skills:
            if not t_user:
                continue
            for skill in all_skills:
                _, created = TeacherSkill.objects.get_or_create(
                    tenant=tenant, teacher=t_user, skill=skill,
                    defaults={
                        "current_level": 1,
                        "target_level": skill.level_required,
                        "last_assessed": now.date(),
                    },
                )
                if created:
                    ts_count += 1
        self.stdout.write(f"  {ts_count} teacher skills created.")

        # Teacher Progress (ensure each teacher/student has progress for each course)
        all_courses = list(Course.objects.filter(tenant=tenant))
        all_teachers = [priya, raj, anita, vikram, teacher]
        all_students = list(User.objects.all_tenants().filter(tenant=tenant, role="STUDENT", is_deleted=False))
        all_progress_users = all_teachers + all_students
        tp_count = 0
        statuses = ["NOT_STARTED", "IN_PROGRESS", "COMPLETED"]
        for u in all_progress_users:
            if not u:
                continue
            for i, course in enumerate(all_courses):
                status = statuses[i % 3]
                pct = {"NOT_STARTED": 0, "IN_PROGRESS": 45, "COMPLETED": 100}[status]
                _, created = TeacherProgress.objects.get_or_create(
                    tenant=tenant, teacher=u, course=course,
                    defaults={
                        "status": status,
                        "progress_percentage": pct,
                        "started_at": now - timedelta(days=30) if status != "NOT_STARTED" else None,
                        "completed_at": now - timedelta(days=5) if status == "COMPLETED" else None,
                    },
                )
                if created:
                    tp_count += 1
        self.stdout.write(f"  {tp_count} progress records created.")

        # Leaderboard Snapshots
        today = now.date()
        yesterday = today - timedelta(days=2)
        leaderboard_data = [
            # (date, period, email, rank, total_xp, period_xp)
            (today, "weekly", "anita.desai@keystoneeducation.in", 1, 220, 33),
            (today, "weekly", "priya.sharma@keystoneeducation.in", 2, 175, 40),
            (today, "weekly", "raj.patel@keystoneeducation.in", 3, 140, 21),
            (today, "weekly", "teacher@keystoneeducation.in", 4, 95, 14),
            (today, "weekly", "vikram.singh@keystoneeducation.in", 5, 60, 9),
            (today, "weekly", "student@keystoneeducation.in", 6, 20, 20),
            (yesterday, "weekly", "anita.desai@keystoneeducation.in", 1, 220, 33),
            (yesterday, "weekly", "priya.sharma@keystoneeducation.in", 2, 175, 40),
            (yesterday, "weekly", "raj.patel@keystoneeducation.in", 3, 140, 21),
            (yesterday, "weekly", "teacher@keystoneeducation.in", 4, 95, 14),
            (yesterday, "weekly", "vikram.singh@keystoneeducation.in", 5, 60, 9),
            (yesterday, "monthly", "anita.desai@keystoneeducation.in", 1, 220, 88),
            (yesterday, "monthly", "priya.sharma@keystoneeducation.in", 2, 175, 95),
            (yesterday, "monthly", "raj.patel@keystoneeducation.in", 3, 140, 56),
            (yesterday, "monthly", "teacher@keystoneeducation.in", 4, 95, 38),
            (yesterday, "monthly", "vikram.singh@keystoneeducation.in", 5, 60, 24),
            (yesterday, "all_time", "anita.desai@keystoneeducation.in", 1, 220, 220),
            (yesterday, "all_time", "priya.sharma@keystoneeducation.in", 2, 175, 175),
            (yesterday, "all_time", "raj.patel@keystoneeducation.in", 3, 140, 140),
            (yesterday, "all_time", "teacher@keystoneeducation.in", 4, 95, 95),
            (yesterday, "all_time", "vikram.singh@keystoneeducation.in", 5, 60, 60),
        ]
        lb_count = 0
        for snap_date, period, email, rank, total, period_xp in leaderboard_data:
            u = get_user(email)
            if not u:
                continue
            _, created = LeaderboardSnapshot.objects.get_or_create(
                tenant=tenant, teacher=u, snapshot_date=snap_date, period=period,
                defaults={"rank": rank, "xp_total": total, "xp_period": period_xp},
            )
            if created:
                lb_count += 1
        self.stdout.write(f"  {lb_count} leaderboard snapshots created.")

        # XP Transactions
        xp_types = [
            ("priya.sharma@keystoneeducation.in", 10, "content_completion", "Completed: Introduction to ATL Framework"),
            ("priya.sharma@keystoneeducation.in", 10, "content_completion", "Completed: Communication Skills in Practice"),
            ("priya.sharma@keystoneeducation.in", 10, "content_completion", "Completed: Research Methods Overview"),
            ("priya.sharma@keystoneeducation.in", 10, "content_completion", "Completed: Self-Management Strategies"),
            ("priya.sharma@keystoneeducation.in", 10, "content_completion", "Completed: Social Skills Development"),
            ("priya.sharma@keystoneeducation.in", 10, "content_completion", "Completed: Thinking Skills Framework"),
            ("priya.sharma@keystoneeducation.in", 15, "quiz_submission", "Quiz passed: ATL Skills Assessment"),
            ("priya.sharma@keystoneeducation.in", 15, "assignment_submission", "Assignment: ATL Portfolio"),
            ("priya.sharma@keystoneeducation.in", 50, "course_completion", "Completed: IB Approaches to Learning"),
            ("priya.sharma@keystoneeducation.in", 2, "streak_bonus", "3-day streak bonus"),
            ("priya.sharma@keystoneeducation.in", 10, "badge_award", "Earned: First Steps"),
            ("priya.sharma@keystoneeducation.in", 10, "badge_award", "Earned: Quick Learner"),
            ("priya.sharma@keystoneeducation.in", 10, "badge_award", "Earned: Course Champion"),
            ("raj.patel@keystoneeducation.in", 10, "content_completion", "Completed: Data Collection Methods"),
            ("raj.patel@keystoneeducation.in", 10, "content_completion", "Completed: Statistical Analysis Basics"),
            ("raj.patel@keystoneeducation.in", 15, "assignment_submission", "Assignment: Data Analysis Project"),
            ("raj.patel@keystoneeducation.in", 50, "course_completion", "Completed: Data-Driven Decision Making"),
            ("raj.patel@keystoneeducation.in", 50, "course_completion", "Completed: Inquiry-Based Science Teaching"),
            ("vikram.singh@keystoneeducation.in", 15, "assignment_submission", "Assignment: ML Integration Plan"),
            ("vikram.singh@keystoneeducation.in", 10, "content_completion", "Completed: Intro to ML Concepts"),
            ("vikram.singh@keystoneeducation.in", 50, "course_completion", "Completed: Introduction to Machine Learning"),
            ("anita.desai@keystoneeducation.in", 10, "content_completion", "Completed: Communication Foundations"),
            ("anita.desai@keystoneeducation.in", 10, "content_completion", "Completed: Active Listening Techniques"),
            ("anita.desai@keystoneeducation.in", 15, "quiz_submission", "Quiz passed: Communication Assessment"),
            ("anita.desai@keystoneeducation.in", 50, "course_completion", "Completed: Effective Classroom Communication"),
            ("student@keystoneeducation.in", 10, "content_completion", "Completed: Module 1"),
            ("student@keystoneeducation.in", 10, "content_completion", "Completed: Module 2"),
        ]
        xp_count = 0
        for email, amount, reason, description in xp_types:
            u = get_user(email)
            if not u:
                continue
            if not XPTransaction.objects.filter(tenant=tenant, teacher=u, reason=reason, description=description).exists():
                XPTransaction.objects.create(
                    tenant=tenant, teacher=u,
                    xp_amount=amount,
                    reason=reason,
                    description=description,
                )
                xp_count += 1
        self.stdout.write(f"  {xp_count} XP transactions created.")

        # ── 12. MAIC CLASSROOMS (add missing ones) ─────────────────────
        self.stdout.write("[12/12] Creating missing MAIC classrooms...")
        try:
            from apps.courses.maic_models import MAICClassroom
            maic_extras = [
                {"title": "deep learning advance", "topic": "deep learning advance", "language": "en", "status": "DRAFT", "is_public": False, "creator": priya, "est_minutes": 0, "num_scenes": 0},
                {"title": "Machine Learning Advance", "topic": "Machine Learning Advance", "language": "en", "status": "DRAFT", "is_public": False, "creator": priya, "est_minutes": 0, "num_scenes": 0},
                {"title": "Claude mythos", "topic": "Claude mythos", "language": "en", "status": "DRAFT", "is_public": False, "creator": priya, "est_minutes": 0, "num_scenes": 0},
                {"title": "deep learning", "topic": "deep learning", "language": "en", "status": "DRAFT", "is_public": False, "creator": teacher, "est_minutes": 0, "num_scenes": 0},
                {"title": "Claude", "topic": "Claude", "language": "en", "status": "DRAFT", "is_public": False, "creator": teacher, "est_minutes": 0, "num_scenes": 0},
                {"title": "AI marketing", "topic": "AI marketing", "language": "en", "status": "DRAFT", "is_public": False, "creator": teacher, "est_minutes": 0, "num_scenes": 0},
                {"title": "OpenAI", "topic": "OpenAI", "language": "en", "status": "DRAFT", "is_public": False, "creator": teacher, "est_minutes": 0, "num_scenes": 0},
                {"title": "Photosynthesis", "topic": "Photosynthesis", "language": "en", "status": "DRAFT", "is_public": False, "creator": teacher, "est_minutes": 0, "num_scenes": 0},
                {"title": "LIO", "topic": "LIO", "language": "en", "status": "DRAFT", "is_public": False, "creator": priya, "est_minutes": 0, "num_scenes": 0},
            ]
            maic_count = 0
            repaired = 0
            for classroom in MAICClassroom.objects.filter(tenant=tenant, status="READY"):
                meta = classroom.content_meta or {}
                has_playable_content = bool(
                    classroom.content_scenes
                    and isinstance(meta, dict)
                    and isinstance(meta.get("slides"), list)
                    and meta.get("slides")
                )
                if not has_playable_content:
                    classroom.status = "DRAFT"
                    classroom.is_public = False
                    classroom.scene_count = 0
                    classroom.estimated_minutes = 0
                    classroom.save(update_fields=[
                        "status",
                        "is_public",
                        "scene_count",
                        "estimated_minutes",
                        "updated_at",
                    ])
                    repaired += 1
            if repaired:
                self.stdout.write(f"  {repaired} empty READY classrooms moved back to DRAFT.")
            deduped = 0
            seen_keys = set()
            for mc in maic_extras:
                creator = mc.get("creator")
                if not creator:
                    continue
                key = (mc["title"], creator.id)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                empty_duplicates = list(
                    MAICClassroom.objects.filter(
                        tenant=tenant,
                        title=mc["title"],
                        creator=creator,
                        status="DRAFT",
                        scene_count=0,
                        estimated_minutes=0,
                        content_scenes=[],
                        content_agents=[],
                        content_meta={},
                    ).order_by("-updated_at")
                )
                for duplicate in empty_duplicates[1:]:
                    duplicate.delete()
                    deduped += 1
            if deduped:
                self.stdout.write(f"  Removed {deduped} duplicate empty MAIC classrooms.")
            default_config = {
                "agents": [
                    {"role": "professor", "name": "Dr. Smith", "expertise": "Subject Expert", "personality": "Knowledgeable and encouraging"},
                    {"role": "student", "name": "Alex", "expertise": "Curious Learner", "personality": "Inquisitive and enthusiastic"},
                    {"role": "critic", "name": "Dr. Chen", "expertise": "Critical Thinker", "personality": "Analytical and thorough"},
                ],
                "generation_params": {"num_scenes": 5, "estimated_minutes": 25},
            }
            for mc in maic_extras:
                creator = mc.pop("creator")
                est = mc.pop("est_minutes")
                scenes = mc.pop("num_scenes")
                if not creator:
                    continue
                config = dict(default_config)
                config["generation_params"] = {"num_scenes": scenes, "estimated_minutes": est}
                # Check if already exists by title + creator. The previous
                # seed let the same "LIO" demo row accumulate, which made the
                # teacher library look duplicated and broken.
                existing = MAICClassroom.objects.filter(
                    tenant=tenant, title=mc["title"], creator=creator,
                ).count()
                if existing > 0:
                    continue
                MAICClassroom.objects.create(
                    tenant=tenant, creator=creator, config=config,
                    **mc,
                )
                maic_count += 1
            self.stdout.write(f"  {maic_count} MAIC classrooms created.")
        except Exception as e:
            self.stdout.write(f"  Skipping MAIC classrooms: {e}")

        # ── 13. CHATBOTS (add missing ones) ────────────────────────────
        self.stdout.write("[Bonus] Creating missing chatbots...")
        try:
            from apps.courses.models import AIChatbot
            chatbot_extras = [
                {
                    "name": "IB Physics Assistant",
                    "persona_preset": "study_buddy",
                    "block_off_topic": True,
                    "is_active": True,
                    "creator": priya,
                    "persona_description": "A knowledgeable IB Physics study companion that helps students understand concepts from the IB Physics syllabus.",
                    "welcome_message": "Hello! I'm your IB Physics study buddy. I can help you with mechanics, waves, electromagnetism, and more. What topic would you like to explore?",
                },
                {
                    "name": "Physics",
                    "persona_preset": "study_buddy",
                    "block_off_topic": True,
                    "is_active": True,
                    "creator": teacher,
                },
                {
                    "name": "Physics (Copy)",
                    "persona_preset": "study_buddy",
                    "block_off_topic": True,
                    "is_active": True,
                    "creator": teacher,
                },
                {
                    "name": "Lab",
                    "persona_preset": "study_buddy",
                    "block_off_topic": True,
                    "is_active": False,
                    "creator": teacher,
                },
                {
                    "name": "Social",
                    "persona_preset": "study_buddy",
                    "block_off_topic": True,
                    "is_active": False,
                    "creator": teacher,
                },
                {
                    "name": "vdfv",
                    "persona_preset": "study_buddy",
                    "block_off_topic": True,
                    "is_active": True,
                    "creator": teacher,
                },
            ]
            bot_count = 0
            for cb in chatbot_extras:
                creator = cb.pop("creator")
                if not creator:
                    continue
                if AIChatbot.objects.filter(tenant=tenant, name=cb["name"]).exists():
                    continue
                AIChatbot.objects.create(tenant=tenant, creator=creator, **cb)
                bot_count += 1
            self.stdout.write(f"  {bot_count} chatbots created.")
        except Exception as e:
            self.stdout.write(f"  Skipping chatbots: {e}")

        # ── Summary ────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*60}\n"
            f"  Full Keystone sync complete!\n"
            f"{'='*60}\n"
        ))
