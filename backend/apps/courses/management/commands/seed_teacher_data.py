"""
Seed rich data for Priya Sharma's teacher portal so every tab shows content.

Tabs to populate:
  - Overview (Dashboard): notifications, calendar-like activity
  - My Courses: already has 5 courses + progress (enhance)
  - My Classes: students already in sections A/B
  - AI Classroom: MAIC classrooms
  - AI Chatbots: already has 1 chatbot (skip)
  - Discussions: threads + replies
  - Announcements (Reminders): campaigns + deliveries
  - Assessments: assignments + quizzes + submissions
  - Competency: skills + teacher skill levels
  - Reports (Gamification): badges, XP, leaderboard
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.courses.maic_models import MAICClassroom
from apps.courses.models import Course, Module, Content
from apps.discussions.models import DiscussionThread, DiscussionReply, DiscussionLike
from apps.notifications.models import Notification
from apps.progress.gamification_models import (
    BadgeDefinition, LeaderboardSnapshot, TeacherBadge,
    TeacherStreak, TeacherXPSummary, XPTransaction,
)
from apps.progress.models import Assignment, AssignmentSubmission, Quiz, QuizQuestion, QuizSubmission
from apps.progress.skills_models import CourseSkill, Skill, TeacherSkill
from apps.reminders.models import ReminderCampaign, ReminderDelivery
from apps.tenants.models import Tenant
from apps.users.models import User
from utils.tenant_middleware import set_current_tenant, clear_current_tenant


class Command(BaseCommand):
    help = "Seed teacher portal data for Priya Sharma at Keystone"

    def handle(self, *args, **options):
        tenant = Tenant.objects.get(subdomain="keystone")
        set_current_tenant(tenant)
        priya = User.objects.get(email="priya.sharma@keystoneeducation.in")
        admin = User.objects.filter(tenant=tenant, role="SCHOOL_ADMIN").first()
        teachers = list(User.objects.filter(tenant=tenant, role="TEACHER").exclude(pk=priya.pk)[:4])
        courses = list(Course.objects.filter(tenant=tenant))
        now = timezone.now()

        self.stdout.write("Seeding data for Priya Sharma…")

        self._seed_assignments(tenant, priya, courses, now)
        self._seed_discussions(tenant, priya, teachers, courses, now)
        self._seed_notifications(tenant, priya, courses, now)
        self._seed_reminders(tenant, priya, admin, teachers, courses, now)
        self._seed_badges_and_xp(tenant, priya, teachers, courses, now)
        self._seed_skills(tenant, priya, teachers, courses)
        self._seed_maic_classrooms(tenant, priya, courses, now)

        clear_current_tenant()
        self.stdout.write(self.style.SUCCESS("Done — all tabs populated."))

    # ── Assessments ──────────────────────────────────────────────────────

    def _seed_assignments(self, tenant, priya, courses, now):
        if Assignment.objects.filter(tenant=tenant).exists():
            self.stdout.write("  Assignments already exist, skipping.")
            return

        quiz_data = [
            {
                "course_idx": 0,  # ATL
                "title": "ATL Thinking Skills Quiz",
                "description": "Test your understanding of Bloom's Taxonomy and thinking routines in the IB context.",
                "questions": [
                    {
                        "prompt": "Which level of Bloom's Taxonomy involves breaking information into parts to explore understandings and relationships?",
                        "type": "MCQ",
                        "options": [
                            {"id": "a", "text": "Remember"},
                            {"id": "b", "text": "Apply"},
                            {"id": "c", "text": "Analyze"},
                            {"id": "d", "text": "Evaluate"},
                        ],
                        "correct": {"answer": "c"},
                        "explanation": "Analyze is the 4th level of Bloom's Taxonomy, involving breaking down information into component parts.",
                    },
                    {
                        "prompt": "True or False: The 'See-Think-Wonder' routine is primarily used for developing research skills.",
                        "type": "TRUE_FALSE",
                        "options": [{"id": "true", "text": "True"}, {"id": "false", "text": "False"}],
                        "correct": {"answer": "false"},
                        "explanation": "See-Think-Wonder is a thinking routine used to encourage observation and curiosity, classified under Thinking Skills.",
                    },
                    {
                        "prompt": "Name two IB Approaches to Learning skill categories.",
                        "type": "SHORT_ANSWER",
                        "options": [],
                        "correct": {"answer": "Any two of: Thinking, Communication, Social, Self-management, Research"},
                        "explanation": "The five ATL skill categories are Thinking, Communication, Social, Self-management, and Research.",
                    },
                ],
            },
            {
                "course_idx": 2,  # Inquiry-Based Science
                "title": "5E Model Assessment",
                "description": "Evaluate your understanding of the 5E Instructional Model and inquiry-based lab design.",
                "questions": [
                    {
                        "prompt": "What are the five phases of the 5E Instructional Model in the correct order?",
                        "type": "MCQ",
                        "options": [
                            {"id": "a", "text": "Engage, Explore, Explain, Elaborate, Evaluate"},
                            {"id": "b", "text": "Explore, Explain, Engage, Evaluate, Elaborate"},
                            {"id": "c", "text": "Explain, Engage, Explore, Elaborate, Evaluate"},
                            {"id": "d", "text": "Evaluate, Engage, Explore, Explain, Elaborate"},
                        ],
                        "correct": {"answer": "a"},
                        "explanation": "The correct order is Engage, Explore, Explain, Elaborate, Evaluate.",
                    },
                    {
                        "prompt": "In the 'Explore' phase, the teacher's role is primarily to:",
                        "type": "MCQ",
                        "options": [
                            {"id": "a", "text": "Lecture on the concept"},
                            {"id": "b", "text": "Facilitate hands-on investigation"},
                            {"id": "c", "text": "Administer a test"},
                            {"id": "d", "text": "Assign homework"},
                        ],
                        "correct": {"answer": "b"},
                        "explanation": "During Explore, teachers facilitate hands-on investigation where students discover concepts themselves.",
                    },
                    {
                        "prompt": "True or False: Lab safety protocols should only be reviewed at the beginning of the academic year.",
                        "type": "TRUE_FALSE",
                        "options": [{"id": "true", "text": "True"}, {"id": "false", "text": "False"}],
                        "correct": {"answer": "false"},
                        "explanation": "Safety protocols should be reviewed before every lab activity, not just once a year.",
                    },
                    {
                        "prompt": "Describe one advantage of inquiry-based learning over traditional lecture-based instruction.",
                        "type": "SHORT_ANSWER",
                        "options": [],
                        "correct": {"answer": "Students develop deeper understanding through active exploration and discovery."},
                        "explanation": "Inquiry-based learning promotes critical thinking, curiosity, and deeper conceptual understanding.",
                    },
                ],
            },
            {
                "course_idx": 4,  # ML
                "title": "Machine Learning Fundamentals Quiz",
                "description": "Check your understanding of supervised learning, classification, and neural networks.",
                "questions": [
                    {
                        "prompt": "Which of the following is an example of supervised learning?",
                        "type": "MCQ",
                        "options": [
                            {"id": "a", "text": "Clustering customer segments"},
                            {"id": "b", "text": "Predicting house prices from labeled data"},
                            {"id": "c", "text": "Reducing dimensions of data"},
                            {"id": "d", "text": "Finding anomalies in network traffic"},
                        ],
                        "correct": {"answer": "b"},
                        "explanation": "Supervised learning uses labeled data. Predicting house prices from labeled examples is a classic regression task.",
                    },
                    {
                        "prompt": "True or False: A neural network with no hidden layers is equivalent to logistic regression.",
                        "type": "TRUE_FALSE",
                        "options": [{"id": "true", "text": "True"}, {"id": "false", "text": "False"}],
                        "correct": {"answer": "true"},
                        "explanation": "A single-layer neural network with a sigmoid activation is mathematically equivalent to logistic regression.",
                    },
                    {
                        "prompt": "What is the difference between classification and regression?",
                        "type": "SHORT_ANSWER",
                        "options": [],
                        "correct": {"answer": "Classification predicts discrete categories; regression predicts continuous numerical values."},
                        "explanation": "Classification outputs discrete labels (e.g., spam/not spam), while regression outputs continuous values (e.g., temperature).",
                    },
                ],
            },
        ]

        for qd in quiz_data:
            course = courses[qd["course_idx"]]
            module = Module.objects.filter(course=course).first()
            due = now + timedelta(days=random.randint(3, 14))

            assignment = Assignment.objects.create(
                tenant=tenant,
                course=course,
                module=module,
                title=qd["title"],
                description=qd["description"],
                due_date=due,
                max_score=Decimal("100"),
                passing_score=Decimal("70"),
            )

            quiz = Quiz.objects.create(tenant=tenant, assignment=assignment)
            for i, q in enumerate(qd["questions"]):
                QuizQuestion.objects.create(
                    tenant=tenant,
                    quiz=quiz,
                    order=i,
                    question_type=q["type"],
                    prompt=q["prompt"],
                    options=q["options"],
                    correct_answer=q["correct"],
                    explanation=q["explanation"],
                    points=random.choice([1, 2]),
                )

            # Priya has submitted 2 of 3 quizzes
            if qd["course_idx"] != 4:
                score = Decimal(str(random.randint(70, 95)))
                QuizSubmission.objects.create(
                    tenant=tenant,
                    quiz=quiz,
                    teacher=priya,
                    answers={"submitted": True},
                    score=score,
                    graded_at=now - timedelta(days=random.randint(1, 5)),
                )

        # One text assignment (no quiz)
        course_comm = courses[3]  # Classroom Communication
        module_comm = Module.objects.filter(course=course_comm).first()
        text_assignment = Assignment.objects.create(
            tenant=tenant,
            course=course_comm,
            module=module_comm,
            title="Reflection: My Communication Style",
            description="Write a 300-word reflection on your primary communication style in the classroom and identify one area for improvement.",
            instructions="Consider both verbal and non-verbal communication. Use specific examples from your recent teaching practice.",
            due_date=now + timedelta(days=7),
            max_score=Decimal("50"),
            passing_score=Decimal("30"),
        )
        AssignmentSubmission.objects.create(
            tenant=tenant,
            assignment=text_assignment,
            teacher=priya,
            submission_text="I tend to use a mix of direct instruction and Socratic questioning in my physics classes. My students respond well to demonstrations followed by guided discussion. One area I want to improve is my use of wait time — I sometimes answer my own questions too quickly instead of giving students space to think. I've noticed that when I pause for 5-7 seconds, the quality of student responses improves dramatically. I plan to practice this deliberately in my next unit on electromagnetic induction.",
            status="GRADED",
            score=Decimal("42"),
            feedback="Excellent reflection, Priya. Your self-awareness about wait time is a valuable insight. Consider also exploring cold-calling strategies to increase participation from quieter students.",
            graded_at=now - timedelta(days=2),
        )

        self.stdout.write(f"  Created {Assignment.objects.filter(tenant=tenant).count()} assignments + quizzes")

    # ── Discussions ──────────────────────────────────────────────────────

    def _seed_discussions(self, tenant, priya, teachers, courses, now):
        if DiscussionThread.objects.filter(tenant=tenant).exists():
            self.stdout.write("  Discussions already exist, skipping.")
            return

        from apps.academics.models import Section, TeachingAssignment

        # Get Priya's assigned sections
        section_ids = TeachingAssignment.objects.filter(
            tenant=tenant, teacher=priya
        ).values_list('sections__id', flat=True).distinct()
        sections = list(Section.objects.filter(id__in=section_ids).select_related('grade'))
        if not sections:
            self.stdout.write("  No sections found for Priya, skipping discussions.")
            return

        # Get students from those sections
        students = list(User.objects.filter(
            tenant=tenant, role='STUDENT', section_fk__in=sections
        )[:15])
        if not students:
            self.stdout.write("  No students in sections, skipping discussions.")
            return

        # Get content items from courses for context
        from apps.courses.models import Content
        contents = list(Content.all_objects.filter(
            module__course__in=courses, module__course__tenant=tenant
        )[:10])

        section_a = sections[0]
        section_b = sections[1] if len(sections) > 1 else sections[0]
        students_a = [s for s in students if s.section_fk_id == section_a.id]
        students_b = [s for s in students if s.section_fk_id == section_b.id]

        def pick_student(section_students, idx=0):
            return section_students[idx % len(section_students)] if section_students else students[0]

        threads_data = [
            {
                "section": section_a,
                "course": courses[0] if courses else None,
                "content": contents[0] if contents else None,
                "title": "Can someone explain electromagnetic induction simply?",
                "body": "I watched the video but I'm confused about Lenz's law. Why does the induced current oppose the change? It seems counterintuitive. Can someone explain it in simple terms?",
                "author": pick_student(students_a, 0),
                "replies": [
                    {"author": pick_student(students_a, 1), "body": "Think of it like Newton's third law but for magnets! When you push a magnet into a coil, the coil creates its own magnetic field that pushes back. It's nature's way of resisting change."},
                    {"author": pick_student(students_a, 2), "body": "The video at 3:45 has a good animation. The key is that if the induced current DIDN'T oppose the change, you'd get infinite energy from nothing, which violates conservation of energy."},
                    {"author": priya, "body": "Great explanations! Think about it this way: if the induced current helped the change instead of opposing it, you'd push a magnet in, get a current that pulls it further in, which creates more current... infinite energy! That can't happen, so the current must oppose."},
                    {"author": pick_student(students_a, 0), "body": "Oh that makes so much sense now! The conservation of energy argument really clicked for me. Thanks everyone!"},
                ],
            },
            {
                "section": section_a,
                "course": courses[0] if courses else None,
                "content": contents[1] if len(contents) > 1 else None,
                "title": "Study group for the waves unit test?",
                "body": "Anyone want to form a study group for the waves test next week? I'm especially struggling with standing waves and harmonics. We could meet during lunch in the library.",
                "author": pick_student(students_a, 3),
                "is_pinned": True,
                "replies": [
                    {"author": pick_student(students_a, 1), "body": "I'm in! I'm good with standing waves but need help with diffraction. We can teach each other."},
                    {"author": pick_student(students_a, 4), "body": "Count me in too. Can we do Tuesday and Thursday lunch? That gives us two sessions before the test."},
                    {"author": pick_student(students_a, 2), "body": "I'll join! I made flashcards for all the wave equations, happy to share them with the group."},
                    {"author": priya, "body": "Love seeing this initiative! I'll reserve the physics lab for your Tuesday session so you can use the wave demonstration equipment. The ripple tank really helps visualize interference patterns."},
                ],
            },
            {
                "section": section_b,
                "course": courses[0] if courses else None,
                "content": contents[2] if len(contents) > 2 else None,
                "title": "Confusion about vector vs scalar quantities",
                "body": "In the lesson, it says speed is scalar but velocity is vector. But aren't they the same thing? When would the distinction actually matter?",
                "author": pick_student(students_b, 0),
                "replies": [
                    {"author": pick_student(students_b, 1), "body": "They're different! Speed is just how fast (like 50 km/h), but velocity includes direction (50 km/h NORTH). If you drive in a circle at 50 km/h, your speed is constant but your velocity keeps changing because direction changes."},
                    {"author": pick_student(students_b, 2), "body": "It matters a lot in real physics! Like, if you throw a ball up and catch it at the same height, the average velocity is ZERO (same start and end point) but the average speed is definitely not zero. Mind blown."},
                    {"author": priya, "body": "Perfect examples from both of you. Here's a fun one: the International Space Station orbits at a constant speed of 27,600 km/h, but its velocity is constantly changing because it's going in a circle. That's why it needs to accelerate even though its speed stays the same!"},
                ],
            },
            {
                "section": section_b,
                "course": courses[0] if courses else None,
                "content": contents[3] if len(contents) > 3 else None,
                "title": "Lab report: How do I write the evaluation section?",
                "body": "I finished my pendulum experiment but I'm stuck on the evaluation. What exactly should I include? The rubric says 'evaluate the procedure' but I'm not sure what that means in practice.",
                "author": pick_student(students_b, 3),
                "replies": [
                    {"author": pick_student(students_b, 1), "body": "You need to discuss what went wrong and how to fix it. Like, was there air resistance? Did the string stretch? Was the angle measurement accurate? Then suggest improvements for each issue."},
                    {"author": priya, "body": "Good start! For Criterion C (Processing and Evaluating), you should: 1) Compare your result to the accepted value of g and calculate % error, 2) Identify at least 3 sources of error (systematic AND random), 3) Suggest realistic improvements for each. The key word is 'realistic' — don't just say 'use better equipment', explain specifically what and why."},
                    {"author": pick_student(students_b, 0), "body": "Thanks Ms. Sharma! Quick question: is human reaction time a systematic or random error? I used a stopwatch to time the oscillations."},
                    {"author": priya, "body": "Great question! Human reaction time is a RANDOM error — sometimes you're a bit early, sometimes a bit late. To reduce it, you timed multiple oscillations (you did 10, right?) and divided by the count. A systematic error would be if your ruler was bent and consistently measured too long."},
                ],
            },
            {
                "section": section_a,
                "course": courses[0] if courses else None,
                "title": "Physics joke thread (for stress relief before exams)",
                "body": "We all need a laugh before exam week. Drop your best physics jokes here! I'll start: Why can't you trust atoms? Because they make up everything.",
                "author": pick_student(students_a, 2),
                "replies": [
                    {"author": pick_student(students_a, 4), "body": "A neutron walks into a bar and asks how much for a drink. The bartender says, 'For you, no charge.'"},
                    {"author": pick_student(students_a, 0), "body": "Schrödinger's cat walks into a bar. And doesn't."},
                    {"author": pick_student(students_a, 1), "body": "What did the physicist say to the other physicist who wanted to fight? 'Let me atom!'"},
                    {"author": priya, "body": "I see the physics humor is strong in this section. Here's mine: Why did the photon refuse to check luggage? Because it was traveling light. Good luck on exams everyone!"},
                ],
            },
        ]

        for td in threads_data:
            last_reply_time = now - timedelta(hours=random.randint(2, 72))
            thread = DiscussionThread.objects.create(
                tenant=tenant,
                section=td["section"],
                course=td.get("course"),
                content=td.get("content"),
                title=td["title"],
                body=td["body"],
                author=td["author"],
                is_pinned=td.get("is_pinned", False),
                reply_count=len(td["replies"]),
                view_count=random.randint(8, 45),
                last_reply_at=last_reply_time,
                last_reply_by=td["replies"][-1]["author"] if td["replies"] else None,
            )

            for rd in td["replies"]:
                reply = DiscussionReply.objects.create(
                    thread=thread,
                    body=rd["body"],
                    author=rd["author"],
                    like_count=random.randint(0, 5),
                )
                if reply.like_count > 0:
                    potential_likers = [s for s in students if s != reply.author][:5]
                    likers = random.sample(potential_likers, min(reply.like_count, len(potential_likers)))
                    for liker in likers:
                        DiscussionLike.objects.get_or_create(reply=reply, user=liker)

        self.stdout.write(f"  Created {DiscussionThread.objects.filter(tenant=tenant).count()} discussion threads")

    # ── Notifications ────────────────────────────────────────────────────

    def _seed_notifications(self, tenant, priya, courses, now):
        if Notification.objects.filter(tenant=tenant, teacher=priya).exists():
            self.stdout.write("  Notifications already exist, skipping.")
            return

        notifs = [
            {"type": "COURSE_ASSIGNED", "title": "New Course Assigned", "message": f"You've been assigned to '{courses[4].title}'. Start learning at your own pace!", "course": courses[4]},
            {"type": "ASSIGNMENT_DUE", "title": "Assignment Due Soon", "message": "Your 'ATL Thinking Skills Quiz' is due in 3 days. Don't forget to submit!", "course": courses[0]},
            {"type": "ANNOUNCEMENT", "title": "Professional Development Week", "message": "PD Week is scheduled for April 21-25. All teachers are expected to complete at least 2 courses by then.", "is_read": True},
            {"type": "SYSTEM", "title": "AI Chatbot Ready", "message": "Your 'IB Physics Assistant' chatbot has finished processing all knowledge sources and is ready for students.", "is_read": True},
            {"type": "ANNOUNCEMENT", "title": "New IB Resources Available", "message": "The IB Programme Resource Centre has been updated with new exemplar materials for Sciences. Check the ATL course for links."},
            {"type": "REMINDER", "title": "Complete Your Profile", "message": "Your teacher profile is 80% complete. Add your qualifications and teaching philosophy to help students learn about you.", "is_read": True},
            {"type": "SYSTEM", "title": "Quiz Graded", "message": "Your '5E Model Assessment' quiz has been auto-graded. You scored 88/100. Review your answers to see detailed feedback."},
            {"type": "COURSE_ASSIGNED", "title": "Course Updated", "message": f"New content has been added to '{courses[3].title}': Digital Communication Tools module.", "course": courses[3]},
            {"type": "ANNOUNCEMENT", "title": "Parent-Teacher Conference Schedule", "message": "The Grade 10 parent-teacher conferences are scheduled for April 28-29. Please update your availability in the calendar."},
            {"type": "SYSTEM", "title": "Discussion Reply", "message": "Anita Desai replied to your discussion 'Best thinking routines for Grade 10 physics?'"},
        ]

        for i, n in enumerate(notifs):
            Notification.objects.create(
                tenant=tenant,
                teacher=priya,
                notification_type=n["type"],
                title=n["title"],
                message=n["message"],
                course=n.get("course"),
                is_read=n.get("is_read", False),
                is_actionable=n["type"] in ("ASSIGNMENT_DUE", "COURSE_ASSIGNED"),
            )

        self.stdout.write(f"  Created {len(notifs)} notifications")

    # ── Reminders (Announcements tab) ────────────────────────────────────

    def _seed_reminders(self, tenant, priya, admin, teachers, courses, now):
        if ReminderCampaign.objects.filter(tenant=tenant).exists():
            self.stdout.write("  Reminders already exist, skipping.")
            return

        all_teachers = [priya] + teachers
        campaigns = [
            {
                "type": "COURSE_DEADLINE",
                "course": courses[0],
                "subject": "ATL Course — Complete by April 20",
                "message": "Please complete the IB Approaches to Learning course by April 20. This is mandatory for all IB teachers.",
                "source": "MANUAL",
                "created_by": admin,
            },
            {
                "type": "CUSTOM",
                "subject": "Professional Development Week Reminder",
                "message": "PD Week starts April 21. Make sure you've completed at least 2 courses. Check your dashboard for progress.",
                "source": "MANUAL",
                "created_by": admin,
            },
            {
                "type": "ASSIGNMENT_DUE",
                "course": courses[2],
                "subject": "5E Model Assessment Due April 18",
                "message": "Your 5E Model Assessment is due on April 18. Please submit before the deadline to avoid penalties.",
                "source": "AUTOMATED",
                "automation_key": "assignment_due_3day",
            },
            {
                "type": "CUSTOM",
                "subject": "Welcome to the New Term!",
                "message": "Welcome back! The new term brings exciting updates to our learning platform. Check out the new AI Chatbot feature for your students.",
                "source": "MANUAL",
                "created_by": admin,
            },
        ]

        for cd in campaigns:
            campaign = ReminderCampaign.objects.create(
                tenant=tenant,
                created_by=cd.get("created_by"),
                reminder_type=cd["type"],
                course=cd.get("course"),
                subject=cd["subject"],
                message=cd["message"],
                source=cd["source"],
                automation_key=cd.get("automation_key", ""),
            )

            # Create deliveries for all teachers
            for t in all_teachers:
                ReminderDelivery.objects.create(
                    campaign=campaign,
                    teacher=t,
                    status="SENT",
                    sent_at=now - timedelta(days=random.randint(1, 10)),
                )

        self.stdout.write(f"  Created {len(campaigns)} reminder campaigns")

    # ── Gamification: Badges, XP, Leaderboard ────────────────────────────

    def _seed_badges_and_xp(self, tenant, priya, teachers, courses, now):
        if BadgeDefinition.objects.filter(tenant=tenant).exists():
            self.stdout.write("  Badges already exist, skipping.")
            return

        badge_defs = [
            {"name": "First Steps", "description": "Complete your first piece of content", "icon": "footprints", "color": "#10B981", "category": "milestone", "criteria_type": "content_completed", "criteria_value": 1, "sort_order": 1},
            {"name": "Quick Learner", "description": "Complete 5 content items", "icon": "zap", "color": "#F59E0B", "category": "milestone", "criteria_type": "content_completed", "criteria_value": 5, "sort_order": 2},
            {"name": "Knowledge Seeker", "description": "Complete 10 content items", "icon": "book-open", "color": "#6366F1", "category": "milestone", "criteria_type": "content_completed", "criteria_value": 10, "sort_order": 3},
            {"name": "Course Champion", "description": "Complete your first course", "icon": "trophy", "color": "#EF4444", "category": "completion", "criteria_type": "courses_completed", "criteria_value": 1, "sort_order": 4},
            {"name": "On Fire", "description": "Maintain a 3-day learning streak", "icon": "flame", "color": "#F97316", "category": "streak", "criteria_type": "streak_days", "criteria_value": 3, "sort_order": 5},
            {"name": "Unstoppable", "description": "Maintain a 7-day learning streak", "icon": "rocket", "color": "#EC4899", "category": "streak", "criteria_type": "streak_days", "criteria_value": 7, "sort_order": 6},
            {"name": "XP Milestone: 50", "description": "Earn 50 total XP", "icon": "star", "color": "#8B5CF6", "category": "milestone", "criteria_type": "xp_threshold", "criteria_value": 50, "sort_order": 7},
            {"name": "XP Milestone: 200", "description": "Earn 200 total XP", "icon": "award", "color": "#06B6D4", "category": "milestone", "criteria_type": "xp_threshold", "criteria_value": 200, "sort_order": 8},
            {"name": "Quiz Ace", "description": "Score above 90% on a quiz", "icon": "check-circle", "color": "#14B8A6", "category": "skill", "criteria_type": "manual", "criteria_value": 0, "sort_order": 9},
            {"name": "Trailblazer", "description": "Be the first teacher to complete a new course", "icon": "compass", "color": "#D946EF", "category": "special", "criteria_type": "manual", "criteria_value": 0, "sort_order": 10},
        ]

        badges = {}
        for bd in badge_defs:
            badges[bd["name"]] = BadgeDefinition.objects.create(tenant=tenant, **bd)

        # Award badges to Priya
        priya_badges = ["First Steps", "Quick Learner", "Knowledge Seeker", "Course Champion", "On Fire", "XP Milestone: 50", "Quiz Ace"]
        for bname in priya_badges:
            TeacherBadge.objects.create(
                tenant=tenant, teacher=priya, badge=badges[bname],
                awarded_reason=f"Automatically awarded for meeting criteria",
            )

        # Update Priya's XP and streak
        xp_summary, _ = TeacherXPSummary.objects.get_or_create(tenant=tenant, teacher=priya)
        xp_summary.total_xp = 175
        xp_summary.level = 3
        xp_summary.level_name = "Senior Educator"
        xp_summary.xp_this_month = 95
        xp_summary.xp_this_week = 40
        xp_summary.last_xp_at = now
        xp_summary.save()

        streak, _ = TeacherStreak.objects.get_or_create(tenant=tenant, teacher=priya)
        streak.current_streak = 5
        streak.longest_streak = 8
        streak.last_activity_date = now.date()
        streak.save()

        # Add more XP transactions for variety
        xp_events = [
            {"xp": 10, "reason": "content_completion", "desc": "Completed: Communication Models in Education", "days_ago": 7},
            {"xp": 10, "reason": "content_completion", "desc": "Completed: Active Listening Techniques", "days_ago": 6},
            {"xp": 50, "reason": "course_completion", "desc": "Completed: Inquiry-Based Science Teaching", "days_ago": 5},
            {"xp": 15, "reason": "quiz_submission", "desc": "Submitted: ATL Thinking Skills Quiz (85%)", "days_ago": 4},
            {"xp": 15, "reason": "assignment_submission", "desc": "Submitted: Communication Style Reflection", "days_ago": 3},
            {"xp": 15, "reason": "quiz_submission", "desc": "Submitted: 5E Model Assessment (88%)", "days_ago": 2},
            {"xp": 10, "reason": "content_completion", "desc": "Completed: Classification vs Regression", "days_ago": 1},
            {"xp": 2, "reason": "streak_bonus", "desc": "5-day learning streak bonus", "days_ago": 0},
            {"xp": 10, "reason": "content_completion", "desc": "Completed: 5E Instructional Model", "days_ago": 8},
            {"xp": 10, "reason": "content_completion", "desc": "Completed: Lab Safety Protocols", "days_ago": 9},
            {"xp": 10, "reason": "content_completion", "desc": "Completed: Types of Student Data", "days_ago": 10},
            {"xp": 10, "reason": "badge_award", "desc": "Earned badge: Course Champion", "days_ago": 5},
        ]
        for evt in xp_events:
            XPTransaction.objects.create(
                tenant=tenant, teacher=priya,
                xp_amount=evt["xp"], reason=evt["reason"],
                description=evt["desc"],
            )

        # Seed other teachers with XP for leaderboard
        all_teachers = [priya] + teachers
        teacher_xps = [175, 220, 140, 95, 60]  # Priya is 2nd
        for i, teacher in enumerate(all_teachers):
            if teacher == priya:
                continue
            xp_val = teacher_xps[i] if i < len(teacher_xps) else random.randint(30, 150)
            summary, _ = TeacherXPSummary.objects.get_or_create(tenant=tenant, teacher=teacher)
            summary.total_xp = xp_val
            summary.level = max(1, xp_val // 50)
            summary.xp_this_month = int(xp_val * 0.4)
            summary.xp_this_week = int(xp_val * 0.15)
            summary.save()

            # Award some badges to other teachers
            if xp_val >= 100:
                for bname in ["First Steps", "Quick Learner"]:
                    TeacherBadge.objects.get_or_create(
                        tenant=tenant, teacher=teacher, badge=badges[bname],
                        defaults={"awarded_reason": "Criteria met"},
                    )

        # Leaderboard snapshots
        today = now.date()
        for period in ["weekly", "monthly", "all_time"]:
            ranked = sorted(all_teachers, key=lambda t: getattr(TeacherXPSummary.objects.filter(teacher=t).first(), 'total_xp', 0), reverse=True)
            for rank, teacher in enumerate(ranked, 1):
                summary = TeacherXPSummary.objects.filter(teacher=teacher).first()
                xp = summary.total_xp if summary else 0
                LeaderboardSnapshot.objects.create(
                    tenant=tenant, teacher=teacher,
                    period=period, rank=rank,
                    xp_total=xp,
                    xp_period=int(xp * (0.15 if period == "weekly" else 0.4 if period == "monthly" else 1)),
                    snapshot_date=today,
                )

        self.stdout.write(f"  Created {len(badge_defs)} badges, {len(priya_badges)} awarded to Priya, leaderboard populated")

    # ── Skills / Competency ──────────────────────────────────────────────

    def _seed_skills(self, tenant, priya, teachers, courses):
        if Skill.objects.filter(tenant=tenant).exists():
            self.stdout.write("  Skills already exist, skipping.")
            return

        skills_data = [
            {"name": "Inquiry-Based Pedagogy", "category": "Teaching Methods", "description": "Ability to design and facilitate inquiry-based learning experiences", "level_required": 3},
            {"name": "Data Literacy", "category": "Assessment", "description": "Competency in collecting, analyzing, and using educational data to inform instruction", "level_required": 2},
            {"name": "Differentiated Instruction", "category": "Teaching Methods", "description": "Skill in adapting teaching strategies to meet diverse learner needs", "level_required": 3},
            {"name": "Technology Integration", "category": "Digital Skills", "description": "Effective use of educational technology tools in the classroom", "level_required": 2},
            {"name": "Assessment Design", "category": "Assessment", "description": "Creating valid, reliable, and fair assessments aligned with learning objectives", "level_required": 3},
            {"name": "IB Curriculum Knowledge", "category": "Curriculum", "description": "Understanding of IB frameworks, ATL skills, and programme requirements", "level_required": 4},
            {"name": "Classroom Management", "category": "Teaching Methods", "description": "Creating and maintaining a positive, productive learning environment", "level_required": 2},
            {"name": "Scientific Communication", "category": "Subject Expertise", "description": "Ability to communicate complex scientific concepts clearly and accurately", "level_required": 3},
            {"name": "AI & EdTech Literacy", "category": "Digital Skills", "description": "Understanding and applying AI tools in educational contexts", "level_required": 2},
            {"name": "Collaborative Learning Design", "category": "Teaching Methods", "description": "Designing group activities that promote meaningful peer learning", "level_required": 2},
        ]

        skills = {}
        for sd in skills_data:
            skills[sd["name"]] = Skill.objects.create(tenant=tenant, **sd)

        # Link skills to courses
        course_skill_map = {
            0: ["IB Curriculum Knowledge", "Inquiry-Based Pedagogy"],  # ATL
            1: ["Data Literacy", "Assessment Design"],  # Data-Driven
            2: ["Inquiry-Based Pedagogy", "Scientific Communication", "Assessment Design"],  # Inquiry Science
            3: ["Classroom Management", "Differentiated Instruction", "Collaborative Learning Design"],  # Communication
            4: ["Technology Integration", "AI & EdTech Literacy"],  # ML
        }
        for idx, skill_names in course_skill_map.items():
            for sn in skill_names:
                CourseSkill.objects.create(
                    course=courses[idx], skill=skills[sn],
                    level_taught=random.randint(1, 3),
                )

        # Priya's skill levels
        priya_skills = {
            "Inquiry-Based Pedagogy": (4, 5),
            "Data Literacy": (2, 3),
            "Differentiated Instruction": (3, 4),
            "Technology Integration": (3, 4),
            "Assessment Design": (3, 4),
            "IB Curriculum Knowledge": (4, 5),
            "Classroom Management": (3, 3),
            "Scientific Communication": (4, 5),
            "AI & EdTech Literacy": (2, 4),
            "Collaborative Learning Design": (3, 4),
        }
        for sn, (current, target) in priya_skills.items():
            TeacherSkill.objects.create(
                teacher=priya, skill=skills[sn], tenant=tenant,
                current_level=current, target_level=target,
            )

        self.stdout.write(f"  Created {len(skills_data)} skills, mapped to courses, Priya's competency set")

    # ── MAIC Classrooms ──────────────────────────────────────────────────

    def _seed_maic_classrooms(self, tenant, priya, courses, now):
        if MAICClassroom.objects.filter(tenant=tenant, creator=priya).exists():
            self.stdout.write("  MAIC Classrooms already exist, skipping.")
            return

        classrooms = [
            {
                "title": "Electromagnetic Induction — Interactive Lesson",
                "description": "Multi-agent AI classroom exploring Faraday's law, Lenz's law, and real-world applications of electromagnetic induction.",
                "topic": "Electromagnetic Induction for IB Physics",
                "status": "READY",
                "course": courses[2],
                "is_public": True,
                "scene_count": 8,
                "estimated_minutes": 25,
                "config": {"agent_count": 3, "style": "socratic", "difficulty": "intermediate"},
            },
            {
                "title": "Newton's Laws — From Concept to Application",
                "description": "AI-guided exploration of Newton's three laws of motion with interactive demos, quizzes, and real-world problem solving.",
                "topic": "Newton's Laws of Motion",
                "status": "READY",
                "course": courses[2],
                "is_public": True,
                "scene_count": 10,
                "estimated_minutes": 30,
                "config": {"agent_count": 3, "style": "exploratory", "difficulty": "beginner"},
            },
            {
                "title": "Wave-Particle Duality",
                "description": "Deep dive into the dual nature of light and matter, from Young's double slit to electron diffraction.",
                "topic": "Wave-Particle Duality in Quantum Physics",
                "status": "DRAFT",
                "is_public": False,
                "scene_count": 0,
                "estimated_minutes": 0,
                "config": {"agent_count": 2, "style": "lecture", "difficulty": "advanced"},
            },
        ]

        for cd in classrooms:
            MAICClassroom.objects.create(
                tenant=tenant, creator=priya,
                title=cd["title"], description=cd["description"],
                topic=cd["topic"], status=cd["status"],
                course=cd.get("course"), is_public=cd["is_public"],
                scene_count=cd["scene_count"],
                estimated_minutes=cd["estimated_minutes"],
                config=cd["config"],
            )

        self.stdout.write(f"  Created {len(classrooms)} MAIC classrooms")
