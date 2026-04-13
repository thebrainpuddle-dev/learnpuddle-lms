# apps/courses/management/commands/seed_maic_data.py
#
# Seeds comprehensive dummy data across admin, teacher, and student roles
# to validate the full MAIC + LMS schema end-to-end.
#
# Usage:
#   python manage.py seed_maic_data                    # Seeds keystone tenant
#   python manage.py seed_maic_data --tenant=demo      # Seeds demo tenant
#   python manage.py seed_maic_data --reset            # Clears seed data first

import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course, Module, Content
from apps.courses.maic_models import MAICClassroom, TenantAIConfig
from apps.courses.chatbot_models import AIChatbot, AIChatbotKnowledge, AIChatbotConversation
from apps.progress.models import TeacherProgress


# ─── Seed Data Definitions ────────────────────────────────────────────────

TEACHERS = [
    {
        "email": "priya.sharma@keystoneeducation.in",
        "first_name": "Priya",
        "last_name": "Sharma",
        "department": "Mathematics",
        "designation": "Senior Teacher",
        "subjects": ["Mathematics", "Statistics"],
    },
    {
        "email": "raj.patel@keystoneeducation.in",
        "first_name": "Raj",
        "last_name": "Patel",
        "department": "Science",
        "designation": "Head of Department",
        "subjects": ["Physics", "General Science"],
    },
    {
        "email": "anita.desai@keystoneeducation.in",
        "first_name": "Anita",
        "last_name": "Desai",
        "department": "English",
        "designation": "Teacher",
        "subjects": ["English Literature", "Creative Writing"],
    },
    {
        "email": "vikram.singh@keystoneeducation.in",
        "first_name": "Vikram",
        "last_name": "Singh",
        "department": "Computer Science",
        "designation": "Teacher",
        "subjects": ["Computer Science", "AI & ML"],
    },
]

STUDENTS = [
    {
        "email": "aarav.mehta@keystoneeducation.in",
        "first_name": "Aarav",
        "last_name": "Mehta",
        "grade_level": "Grade 10",
        "section": "A",
        "student_id": "KIS-S001",
    },
    {
        "email": "diya.kapoor@keystoneeducation.in",
        "first_name": "Diya",
        "last_name": "Kapoor",
        "grade_level": "Grade 10",
        "section": "A",
        "student_id": "KIS-S002",
    },
    {
        "email": "arjun.reddy@keystoneeducation.in",
        "first_name": "Arjun",
        "last_name": "Reddy",
        "grade_level": "Grade 11",
        "section": "B",
        "student_id": "KIS-S003",
    },
    {
        "email": "neha.iyer@keystoneeducation.in",
        "first_name": "Neha",
        "last_name": "Iyer",
        "grade_level": "Grade 11",
        "section": "A",
        "student_id": "KIS-S004",
    },
    {
        "email": "rohan.gupta@keystoneeducation.in",
        "first_name": "Rohan",
        "last_name": "Gupta",
        "grade_level": "Grade 12",
        "section": "A",
        "student_id": "KIS-S005",
    },
]

COURSES = [
    {
        "title": "Introduction to Machine Learning",
        "description": "A comprehensive course covering the fundamentals of machine learning, including supervised and unsupervised learning, neural networks, and practical applications in education.",
        "is_mandatory": True,
        "is_published": True,
        "estimated_hours": Decimal("12.0"),
        "course_type": "PD",
        "modules": [
            {
                "title": "What is Machine Learning?",
                "description": "Overview of ML concepts, history, and applications",
                "contents": [
                    {"title": "Introduction to ML — Lecture Notes", "content_type": "TEXT", "text_content": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed.\n\n## Key Concepts\n- Supervised Learning\n- Unsupervised Learning\n- Reinforcement Learning\n\n## Why ML in Education?\nMachine learning can personalize learning paths, automate grading, and identify at-risk students early."},
                    {"title": "History of AI — Timeline", "content_type": "DOCUMENT"},
                    {"title": "ML in Everyday Life — Discussion", "content_type": "TEXT", "text_content": "Think about the ML-powered tools you use daily: recommendation systems, voice assistants, spam filters. How could these technologies transform classroom teaching?"},
                ],
            },
            {
                "title": "Supervised Learning",
                "description": "Classification, regression, and model evaluation",
                "contents": [
                    {"title": "Classification vs Regression", "content_type": "TEXT", "text_content": "Supervised learning uses labeled data to train models.\n\n## Classification\nPredicts categories: spam/not spam, pass/fail\n\n## Regression\nPredicts continuous values: test scores, attendance rates"},
                    {"title": "Hands-on: Train Your First Model", "content_type": "TEXT", "text_content": "In this activity, you will use a simple dataset to train a classification model that predicts student outcomes based on engagement metrics."},
                ],
            },
            {
                "title": "Neural Networks & Deep Learning",
                "description": "Understanding how neural networks work",
                "contents": [
                    {"title": "How Neural Networks Learn", "content_type": "TEXT", "text_content": "Neural networks are inspired by the human brain. They consist of layers of interconnected nodes (neurons) that process information.\n\n## Architecture\n- Input Layer\n- Hidden Layers\n- Output Layer\n\n## Training Process\nForward propagation → Loss calculation → Backpropagation → Weight update"},
                    {"title": "Deep Learning Applications in EdTech", "content_type": "TEXT", "text_content": "Natural Language Processing for essay grading, Computer Vision for proctoring, Speech Recognition for language learning."},
                ],
            },
        ],
    },
    {
        "title": "Effective Classroom Communication",
        "description": "Develop skills for clear, engaging communication in diverse classroom settings. Covers verbal, non-verbal, and digital communication strategies.",
        "is_mandatory": False,
        "is_published": True,
        "estimated_hours": Decimal("8.0"),
        "course_type": "PD",
        "modules": [
            {
                "title": "Foundations of Classroom Communication",
                "description": "Core principles of effective teacher-student communication",
                "contents": [
                    {"title": "Communication Models in Education", "content_type": "TEXT", "text_content": "Effective classroom communication involves encoding, transmitting, receiving, and decoding messages. Teachers must consider noise (physical, psychological, semantic) that can interfere with learning."},
                    {"title": "Active Listening Techniques", "content_type": "TEXT", "text_content": "Active listening involves:\n1. Maintaining eye contact\n2. Nodding and using verbal cues\n3. Paraphrasing student responses\n4. Asking clarifying questions\n5. Withholding judgment"},
                ],
            },
            {
                "title": "Non-Verbal Communication",
                "description": "Body language, facial expressions, and classroom presence",
                "contents": [
                    {"title": "Reading Student Body Language", "content_type": "TEXT", "text_content": "Students communicate engagement and confusion through posture, eye movement, and facial expressions. Learn to read these signals to adjust instruction in real-time."},
                    {"title": "Teacher Presence — Self Assessment", "content_type": "DOCUMENT"},
                ],
            },
            {
                "title": "Digital Communication Tools",
                "description": "Effective use of LMS, email, and messaging with students and parents",
                "contents": [
                    {"title": "Professional Digital Communication", "content_type": "TEXT", "text_content": "Guidelines for professional communication via LMS messaging, email to parents, and virtual classroom etiquette."},
                ],
            },
        ],
    },
    {
        "title": "Inquiry-Based Science Teaching",
        "description": "Learn to design and facilitate inquiry-based science lessons that develop critical thinking and scientific reasoning skills in students.",
        "is_mandatory": False,
        "is_published": True,
        "estimated_hours": Decimal("10.0"),
        "course_type": "PD",
        "modules": [
            {
                "title": "The Inquiry Cycle",
                "description": "Ask, Investigate, Create, Discuss, Reflect",
                "contents": [
                    {"title": "5E Instructional Model", "content_type": "TEXT", "text_content": "The 5E model structures inquiry-based lessons:\n\n1. **Engage** — Hook students with a phenomenon\n2. **Explore** — Hands-on investigation\n3. **Explain** — Develop scientific explanations\n4. **Elaborate** — Apply knowledge to new situations\n5. **Evaluate** — Assess understanding"},
                ],
            },
            {
                "title": "Designing Lab Activities",
                "description": "Creating safe, effective hands-on experiments",
                "contents": [
                    {"title": "Lab Safety Protocols", "content_type": "DOCUMENT"},
                    {"title": "Sample Lab: Photosynthesis Rate", "content_type": "TEXT", "text_content": "Design an experiment to measure how light intensity affects photosynthesis rate using aquatic plants and dissolved oxygen sensors."},
                ],
            },
        ],
    },
    {
        "title": "Data-Driven Decision Making for Educators",
        "description": "Use student data to inform teaching strategies, identify learning gaps, and track progress across academic terms.",
        "is_mandatory": True,
        "is_published": True,
        "estimated_hours": Decimal("6.0"),
        "course_type": "PD",
        "modules": [
            {
                "title": "Understanding Educational Data",
                "description": "Types of data, collection methods, and ethical considerations",
                "contents": [
                    {"title": "Types of Student Data", "content_type": "TEXT", "text_content": "Formative assessments, summative assessments, attendance records, engagement metrics, behavioral observations — each provides a different lens into student performance."},
                ],
            },
            {
                "title": "Data Visualization & Analysis",
                "description": "Creating meaningful visualizations from student data",
                "contents": [
                    {"title": "Creating Effective Data Dashboards", "content_type": "TEXT", "text_content": "Learn to create dashboards that highlight key metrics: class average trends, individual student trajectories, and comparative performance across sections."},
                    {"title": "Spreadsheet Templates", "content_type": "DOCUMENT"},
                ],
            },
        ],
    },
    {
        "title": "IB Approaches to Learning (ATL)",
        "description": "Explore the five ATL skill categories in the International Baccalaureate framework and how to integrate them across subjects.",
        "is_mandatory": False,
        "is_published": True,
        "estimated_hours": Decimal("15.0"),
        "course_type": "ACADEMIC",
        "modules": [
            {
                "title": "Thinking Skills",
                "description": "Critical thinking, creative thinking, and transfer",
                "contents": [
                    {"title": "Bloom's Taxonomy in IB Context", "content_type": "TEXT", "text_content": "Bloom's revised taxonomy aligns with IB ATL thinking skills. Higher-order thinking (analyze, evaluate, create) should be explicitly taught and assessed."},
                    {"title": "Thinking Routines Toolkit", "content_type": "TEXT", "text_content": "See-Think-Wonder, Think-Pair-Share, Claim-Support-Question — these routines make thinking visible and can be used across all subject areas."},
                ],
            },
            {
                "title": "Communication Skills",
                "description": "Reading, writing, speaking, listening, and digital communication",
                "contents": [
                    {"title": "Academic Literacy Across Subjects", "content_type": "TEXT", "text_content": "Every teacher is a language teacher. Subject-specific vocabulary, reading strategies, and writing conventions must be explicitly taught in each discipline."},
                ],
            },
            {
                "title": "Research Skills",
                "description": "Information literacy, media literacy, and ethical use of information",
                "contents": [
                    {"title": "Teaching Research Skills", "content_type": "TEXT", "text_content": "The CRAAP test (Currency, Relevance, Authority, Accuracy, Purpose) helps students evaluate sources critically. Model the research process with guided inquiry projects."},
                ],
            },
        ],
    },
]

MAIC_CLASSROOMS = [
    {
        "title": "Introduction to Neural Networks",
        "description": "An interactive AI classroom exploring how neural networks learn, with visual explanations of forward propagation and backpropagation.",
        "topic": "Neural Networks and Deep Learning Basics",
        "language": "en",
        "status": "READY",
        "is_public": True,
        "scene_count": 6,
        "estimated_minutes": 25,
        "config": {
            "agents": [
                {"id": "prof-neural", "name": "Dr. Sarah Chen", "role": "professor", "personality": "Patient and thorough, uses visual analogies", "expertise": "Deep Learning"},
                {"id": "ta-neural", "name": "Alex Rivera", "role": "teaching_assistant", "personality": "Enthusiastic, asks probing questions", "expertise": "Neural Network Implementation"},
                {"id": "student-neural", "name": "Priya Kumar", "role": "student_rep", "personality": "Curious, represents common student misconceptions", "expertise": "Beginner ML Student"},
            ],
            "language": "en",
        },
    },
    {
        "title": "Photosynthesis Deep Dive",
        "description": "Multi-agent classroom exploring the light and dark reactions of photosynthesis with interactive diagrams and quiz.",
        "topic": "Photosynthesis: Light Reactions and Calvin Cycle",
        "language": "en",
        "status": "READY",
        "is_public": True,
        "scene_count": 5,
        "estimated_minutes": 20,
        "config": {
            "agents": [
                {"id": "prof-bio", "name": "Dr. James Morton", "role": "professor", "personality": "Passionate about biology, uses real-world examples", "expertise": "Plant Biology"},
                {"id": "ta-bio", "name": "Maria Santos", "role": "teaching_assistant", "personality": "Detail-oriented, great at explaining complex processes", "expertise": "Biochemistry"},
            ],
            "language": "en",
        },
    },
    {
        "title": "Shakespeare's Hamlet — Act 3 Analysis",
        "description": "Literary analysis of Hamlet's 'To be or not to be' soliloquy with multi-perspective discussion.",
        "topic": "Shakespeare Hamlet Act 3 Scene 1 Analysis",
        "language": "en",
        "status": "READY",
        "is_public": True,
        "scene_count": 4,
        "estimated_minutes": 18,
        "config": {
            "agents": [
                {"id": "prof-lit", "name": "Prof. Elizabeth Ward", "role": "professor", "personality": "Dramatic and engaging, loves textual close-reading", "expertise": "Shakespearean Literature"},
                {"id": "ta-lit", "name": "David Park", "role": "teaching_assistant", "personality": "Contextual historian, connects literature to its era", "expertise": "Renaissance History"},
                {"id": "student-lit", "name": "Sophie Chen", "role": "student_rep", "personality": "Thoughtful reader, offers modern interpretations", "expertise": "English Literature Student"},
            ],
            "language": "en",
        },
    },
    {
        "title": "Climate Change: Causes and Impacts",
        "description": "Multi-agent discussion on greenhouse effect, global warming data, and mitigation strategies.",
        "topic": "Climate Change Science and Solutions",
        "language": "en",
        "status": "READY",
        "is_public": True,
        "scene_count": 7,
        "estimated_minutes": 30,
        "config": {
            "agents": [
                {"id": "prof-climate", "name": "Dr. Anika Patel", "role": "professor", "personality": "Data-driven, uses IPCC reports", "expertise": "Environmental Science"},
                {"id": "ta-climate", "name": "Marcus Johnson", "role": "teaching_assistant", "personality": "Solutions-oriented, focuses on actionable steps", "expertise": "Sustainable Development"},
            ],
            "language": "en",
        },
    },
    {
        "title": "Quadratic Equations Masterclass",
        "description": "Step-by-step exploration of quadratic equations, factoring, completing the square, and the quadratic formula.",
        "topic": "Solving Quadratic Equations — All Methods",
        "language": "en",
        "status": "READY",
        "is_public": False,
        "scene_count": 5,
        "estimated_minutes": 22,
        "config": {
            "agents": [
                {"id": "prof-math", "name": "Prof. Rajesh Nair", "role": "professor", "personality": "Methodical, builds intuition before formulas", "expertise": "Algebra and Number Theory"},
                {"id": "student-math", "name": "Tom Wilson", "role": "student_rep", "personality": "Struggles with abstract concepts, needs concrete examples", "expertise": "Grade 10 Math Student"},
            ],
            "language": "en",
        },
    },
    {
        "title": "World War II — The Eastern Front",
        "description": "AI classroom on Operation Barbarossa, the siege of Stalingrad, and the turning of the tide.",
        "topic": "World War II Eastern Front 1941-1945",
        "language": "en",
        "status": "GENERATING",
        "is_public": False,
        "scene_count": 0,
        "estimated_minutes": 0,
        "config": {},
    },
    {
        "title": "Introduction to Python Programming",
        "description": "Learn Python basics with interactive coding examples and quizzes.",
        "topic": "Python Programming for Beginners",
        "language": "en",
        "status": "DRAFT",
        "is_public": False,
        "scene_count": 0,
        "estimated_minutes": 0,
        "config": {},
    },
    {
        "title": "Failed Generation Test",
        "description": "This classroom failed during generation — kept for debugging.",
        "topic": "Quantum Computing Basics",
        "language": "en",
        "status": "FAILED",
        "is_public": False,
        "scene_count": 0,
        "estimated_minutes": 0,
        "error_message": "LLM rate limit exceeded. Please try again later.",
        "config": {},
    },
    {
        "title": "Ancient Greek Philosophy",
        "description": "Archived classroom on Socrates, Plato, and Aristotle.",
        "topic": "Greek Philosophy: Socrates to Aristotle",
        "language": "en",
        "status": "ARCHIVED",
        "is_public": False,
        "scene_count": 4,
        "estimated_minutes": 15,
        "config": {
            "agents": [
                {"id": "prof-phil", "name": "Dr. Helena Stavros", "role": "professor", "personality": "Socratic method enthusiast", "expertise": "Ancient Philosophy"},
            ],
            "language": "en",
        },
    },
]


CHATBOTS = [
    {
        "name": "Math Tutor",
        "persona_preset": "tutor",
        "persona_description": "I guide students through math problems step by step using the Socratic method. I never give direct answers — instead I ask leading questions to help students discover solutions themselves.",
        "custom_rules": "Only discuss mathematics topics.\nAlways show your reasoning.\nEncourage students to try before asking for help.",
        "block_off_topic": True,
        "welcome_message": "Hi! I'm your Math Tutor. Share a problem you're working on and I'll help you think through it step by step.",
    },
    {
        "name": "Science Lab Assistant",
        "persona_preset": "reference",
        "persona_description": "I answer factual questions about biology, chemistry, and physics experiments. I reference uploaded lab protocols and safety guidelines.",
        "custom_rules": "Always mention safety precautions when discussing lab procedures.\nCite specific sections from uploaded documents when possible.",
        "block_off_topic": True,
        "welcome_message": "Hello! I'm your Science Lab Assistant. Ask me about any experiment, procedure, or concept from your lab materials.",
    },
    {
        "name": "History Discussion Guide",
        "persona_preset": "open",
        "persona_description": "I facilitate open-ended discussions about historical events, encouraging students to consider multiple perspectives and form their own arguments.",
        "custom_rules": "Present multiple historical perspectives.\nEncourage evidence-based arguments.\nConnect historical events to modern parallels when relevant.",
        "block_off_topic": False,
        "welcome_message": "Welcome! Let's explore history together. What event or period would you like to discuss?",
    },
    {
        "name": "English Writing Coach",
        "persona_preset": "tutor",
        "persona_description": "I help students improve their writing by providing constructive feedback on structure, grammar, and style. I ask questions to help them revise independently.",
        "custom_rules": "Focus on one aspect of writing at a time.\nPraise strengths before suggesting improvements.\nNever rewrite entire paragraphs — suggest specific edits.",
        "block_off_topic": True,
        "welcome_message": "Hi there! I'm your Writing Coach. Paste a paragraph or essay and I'll help you strengthen your writing.",
        "is_active": False,  # Inactive chatbot for testing
    },
]

CHATBOT_KNOWLEDGE = [
    {
        "chatbot_index": 0,  # Math Tutor
        "sources": [
            {"title": "Algebra Fundamentals", "source_type": "text", "raw_text": "Quadratic equations can be solved using factoring, completing the square, or the quadratic formula. The discriminant b²-4ac determines the nature of roots.", "embedding_status": "ready", "chunk_count": 1, "total_token_count": 42},
            {"title": "Geometry Theorems", "source_type": "text", "raw_text": "Pythagorean theorem: In a right triangle, a² + b² = c². Thales' theorem: Any angle inscribed in a semicircle is a right angle.", "embedding_status": "ready", "chunk_count": 1, "total_token_count": 38},
        ],
    },
    {
        "chatbot_index": 1,  # Science Lab Assistant
        "sources": [
            {"title": "Lab Safety Manual", "source_type": "pdf", "filename": "lab-safety-manual.pdf", "embedding_status": "ready", "chunk_count": 8, "total_token_count": 2400},
            {"title": "Photosynthesis Lab Protocol", "source_type": "text", "raw_text": "Objective: Measure the rate of photosynthesis using Elodea plants. Materials: Elodea, test tubes, sodium bicarbonate, light source, timer. Procedure: 1) Cut Elodea stems at an angle. 2) Place inverted in test tube with NaHCO3 solution. 3) Count oxygen bubbles per minute at different light intensities.", "embedding_status": "ready", "chunk_count": 2, "total_token_count": 95},
            {"title": "Chemistry Equations Reference", "source_type": "document", "filename": "chem-equations.pdf", "embedding_status": "pending", "chunk_count": 0, "total_token_count": 0},
        ],
    },
    {
        "chatbot_index": 2,  # History Discussion Guide
        "sources": [
            {"title": "World War II Key Events", "source_type": "text", "raw_text": "1939: Germany invades Poland. 1941: Pearl Harbor attack. 1942: Battle of Stalingrad begins. 1944: D-Day invasion. 1945: Germany and Japan surrender.", "embedding_status": "ready", "chunk_count": 1, "total_token_count": 52},
        ],
    },
]

CHATBOT_CONVERSATIONS = [
    {
        "chatbot_index": 0,  # Math Tutor
        "messages": [
            {"role": "user", "content": "How do I solve x² + 5x + 6 = 0?"},
            {"role": "assistant", "content": "Great question! Let's think about this step by step. This is a quadratic equation. What methods do you know for solving quadratic equations?"},
            {"role": "user", "content": "I know factoring and the quadratic formula"},
            {"role": "assistant", "content": "Let's try factoring first — it's often the quickest approach. For x² + 5x + 6, we need two numbers that multiply to 6 and add to 5. Can you think of which two numbers those would be?"},
            {"role": "user", "content": "2 and 3!"},
            {"role": "assistant", "content": "Exactly! So we can write x² + 5x + 6 = (x + 2)(x + 3) = 0. Now, what values of x make each factor equal to zero?"},
        ],
    },
    {
        "chatbot_index": 1,  # Science Lab Assistant
        "messages": [
            {"role": "user", "content": "What safety equipment do I need for the acid-base titration lab?"},
            {"role": "assistant", "content": "For the acid-base titration lab, you'll need: safety goggles (mandatory), lab coat, nitrile gloves, and closed-toe shoes. According to the Lab Safety Manual, Section 3.2, you should also ensure the fume hood is operational if working with concentrated acids. Do you have any specific questions about the procedure?"},
        ],
    },
]


class Command(BaseCommand):
    help = "Seed comprehensive dummy data for admin, teacher, and student roles to validate MAIC + LMS schema"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            type=str,
            default="keystone",
            help="Tenant subdomain to seed (default: keystone)",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Remove previously seeded data before re-seeding",
        )

    def handle(self, *args, **options):
        subdomain = options["tenant"]
        reset = options["reset"]

        try:
            tenant = Tenant.objects.get(subdomain=subdomain)
        except Tenant.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Tenant '{subdomain}' not found."))
            return

        self.stdout.write(f"\nSeeding data for tenant: {tenant.name} ({subdomain})")
        self.stdout.write("=" * 60)

        if reset:
            self._reset(tenant)

        # 1. Ensure tenant features
        self._ensure_tenant_features(tenant)

        # 2. Ensure AI config
        self._ensure_ai_config(tenant)

        # 3. Create teachers
        teachers = self._create_teachers(tenant)

        # 4. Create students
        students = self._create_students(tenant)

        # 5. Create courses with modules and content
        courses = self._create_courses(tenant, teachers)

        # 6. Assign students to courses
        self._assign_students(courses, students)

        # 7. Create MAIC classrooms
        classrooms = self._create_maic_classrooms(tenant, teachers, courses)

        # 8. Create AI chatbots with knowledge and conversations
        chatbots = self._create_chatbots(tenant, teachers, students)

        # 9. Create progress records
        self._create_progress(tenant, teachers, students, courses)

        # 10. Make existing classrooms public
        self._update_existing_classrooms(tenant)

        self._print_summary(tenant, teachers, students, courses, classrooms, chatbots)

    def _reset(self, tenant):
        """Remove seeded data (identified by seeded email patterns)."""
        seeded_emails = [t["email"] for t in TEACHERS] + [s["email"] for s in STUDENTS]
        seeded_users = User.objects.filter(email__in=seeded_emails, tenant=tenant)

        # Delete chatbots by seeded names
        seeded_chatbot_names = [c["name"] for c in CHATBOTS]
        AIChatbot.objects.all_tenants().filter(
            tenant=tenant, name__in=seeded_chatbot_names
        ).delete()

        # Delete MAIC classrooms by seeded titles
        seeded_titles = [c["title"] for c in MAIC_CLASSROOMS]
        MAICClassroom.objects.all_tenants().filter(
            tenant=tenant, title__in=seeded_titles
        ).delete()

        # Delete courses by seeded titles
        seeded_course_titles = [c["title"] for c in COURSES]
        Course.objects.all_tenants().filter(
            tenant=tenant, title__in=seeded_course_titles
        ).delete()

        # Delete progress for seeded users
        TeacherProgress.objects.all_tenants().filter(
            tenant=tenant, teacher__in=seeded_users
        ).delete()

        # Delete seeded users
        count = seeded_users.count()
        seeded_users.delete()

        self.stdout.write(self.style.WARNING(f"  Reset: removed {count} seeded users and related data"))

    def _ensure_tenant_features(self, tenant):
        changed = []
        if not tenant.feature_maic:
            tenant.feature_maic = True
            changed.append("feature_maic")
        if not tenant.feature_students:
            tenant.feature_students = True
            changed.append("feature_students")
        if not tenant.feature_ai_studio:
            tenant.feature_ai_studio = True
            changed.append("feature_ai_studio")
        if not tenant.feature_teacher_authoring:
            tenant.feature_teacher_authoring = True
            changed.append("feature_teacher_authoring")
        if changed:
            tenant.save()
            self.stdout.write(f"  Enabled features: {', '.join(changed)}")
        else:
            self.stdout.write("  Features: all required features already enabled")

    def _ensure_ai_config(self, tenant):
        config, created = TenantAIConfig.objects.get_or_create(
            tenant=tenant,
            defaults={
                "llm_provider": "openrouter",
                "llm_model": "openai/gpt-4o-mini",
                "tts_provider": "disabled",
                "maic_enabled": True,
            },
        )
        if created:
            self.stdout.write("  Created TenantAIConfig (llm=openrouter/gpt-4o-mini)")
        else:
            if not config.maic_enabled:
                config.maic_enabled = True
                config.save(update_fields=["maic_enabled"])
            self.stdout.write(f"  AI Config: {config.llm_provider}/{config.llm_model} | tts={config.tts_provider}")

    def _create_teachers(self, tenant):
        teachers = []
        for data in TEACHERS:
            user, created = User.objects.get_or_create(
                email=data["email"],
                defaults={
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "role": "TEACHER",
                    "tenant": tenant,
                    "is_active": True,
                    "department": data.get("department", ""),
                    "designation": data.get("designation", ""),
                    "subjects": data.get("subjects", []),
                },
            )
            if created:
                user.set_password("Teacher@123")
                user.save()
            teachers.append(user)

        # Also include existing tenant teacher
        existing = User.objects.filter(tenant=tenant, role="TEACHER").exclude(
            email__in=[t["email"] for t in TEACHERS]
        )
        teachers.extend(list(existing))

        self.stdout.write(f"  Teachers: {len(teachers)} total ({len(TEACHERS)} seeded)")
        return teachers

    def _create_students(self, tenant):
        students = []
        for data in STUDENTS:
            user, created = User.objects.get_or_create(
                email=data["email"],
                defaults={
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "role": "STUDENT",
                    "tenant": tenant,
                    "is_active": True,
                    "grade_level": data.get("grade_level", ""),
                    "section": data.get("section", ""),
                    "student_id": data.get("student_id", ""),
                },
            )
            if created:
                user.set_password("Student@123")
                user.save()
            students.append(user)

        # Include existing tenant student
        existing = User.objects.filter(tenant=tenant, role="STUDENT").exclude(
            email__in=[s["email"] for s in STUDENTS]
        )
        students.extend(list(existing))

        self.stdout.write(f"  Students: {len(students)} total ({len(STUDENTS)} seeded)")
        return students

    def _create_courses(self, tenant, teachers):
        admin = User.objects.filter(tenant=tenant, role="SCHOOL_ADMIN").first()
        courses = []

        for i, course_data in enumerate(COURSES):
            course, created = Course.objects.all_tenants().get_or_create(
                tenant=tenant,
                title=course_data["title"],
                defaults={
                    "description": course_data["description"],
                    "slug": course_data["title"].lower().replace(" ", "-").replace("(", "").replace(")", "")[:200],
                    "is_mandatory": course_data.get("is_mandatory", False),
                    "is_published": course_data.get("is_published", True),
                    "estimated_hours": course_data.get("estimated_hours", Decimal("5.0")),
                    "course_type": course_data.get("course_type", "PD"),
                    "is_active": True,
                    "created_by": admin or (teachers[0] if teachers else None),
                },
            )

            if created:
                # Assign 2-3 teachers to each course
                assigned = teachers[i % len(teachers) : i % len(teachers) + 2]
                if len(assigned) < 2 and len(teachers) > 1:
                    assigned.append(teachers[(i + 1) % len(teachers)])
                course.assigned_teachers.set(assigned)

                # Create modules and content
                for m_order, mod_data in enumerate(course_data.get("modules", [])):
                    module = Module.objects.create(
                        course=course,
                        title=mod_data["title"],
                        description=mod_data.get("description", ""),
                        order=m_order,
                        is_active=True,
                    )
                    for c_order, content_data in enumerate(mod_data.get("contents", [])):
                        Content.objects.create(
                            module=module,
                            title=content_data["title"],
                            content_type=content_data.get("content_type", "TEXT"),
                            text_content=content_data.get("text_content", ""),
                            order=c_order,
                            is_mandatory=True,
                            is_active=True,
                        )

            courses.append(course)

        self.stdout.write(f"  Courses: {len(courses)} total")
        return courses

    def _assign_students(self, courses, students):
        if not students:
            return

        for i, course in enumerate(courses):
            if course.is_published:
                # Assign a subset of students to each published course
                start = i % len(students)
                assigned = students[start:] + students[:start]
                # Take 3-5 students
                subset = assigned[: min(5, len(assigned))]
                course.assigned_students.add(*subset)

        self.stdout.write(f"  Assigned students to {sum(1 for c in courses if c.is_published)} published courses")

    def _create_maic_classrooms(self, tenant, teachers, courses):
        # Determine creators — rotate through available teachers + admin
        admin = User.objects.filter(tenant=tenant, role="SCHOOL_ADMIN").first()
        creators = teachers[:3] if len(teachers) >= 3 else teachers[:]
        if admin:
            creators.append(admin)
        if not creators:
            self.stderr.write("  No creators available for MAIC classrooms")
            return []

        classrooms = []
        for i, data in enumerate(MAIC_CLASSROOMS):
            creator = creators[i % len(creators)]

            # Link first 2 classrooms to courses if available
            linked_course = courses[i] if i < len(courses) else None

            classroom, created = MAICClassroom.objects.all_tenants().get_or_create(
                tenant=tenant,
                title=data["title"],
                creator=creator,
                defaults={
                    "description": data["description"],
                    "topic": data["topic"],
                    "language": data.get("language", "en"),
                    "status": data["status"],
                    "is_public": data.get("is_public", False),
                    "scene_count": data.get("scene_count", 0),
                    "estimated_minutes": data.get("estimated_minutes", 0),
                    "config": data.get("config", {}),
                    "error_message": data.get("error_message", ""),
                    "course": linked_course if i < 2 else None,
                },
            )
            classrooms.append(classroom)

        self.stdout.write(f"  MAIC Classrooms: {len(classrooms)} seeded")
        return classrooms

    def _create_chatbots(self, tenant, teachers, students):
        creators = teachers[:3] if len(teachers) >= 3 else teachers[:]
        if not creators:
            self.stderr.write("  No creators available for chatbots")
            return []

        chatbots = []
        for i, data in enumerate(CHATBOTS):
            creator = creators[i % len(creators)]
            chatbot, created = AIChatbot.objects.all_tenants().get_or_create(
                tenant=tenant,
                name=data["name"],
                creator=creator,
                defaults={
                    "persona_preset": data["persona_preset"],
                    "persona_description": data.get("persona_description", ""),
                    "custom_rules": data.get("custom_rules", ""),
                    "block_off_topic": data.get("block_off_topic", True),
                    "welcome_message": data.get("welcome_message", ""),
                    "is_active": data.get("is_active", True),
                },
            )
            chatbots.append(chatbot)

        # Add knowledge sources
        for kdata in CHATBOT_KNOWLEDGE:
            chatbot = chatbots[kdata["chatbot_index"]]
            for src in kdata["sources"]:
                AIChatbotKnowledge.objects.get_or_create(
                    chatbot=chatbot,
                    title=src["title"],
                    defaults={
                        "tenant": tenant,
                        "source_type": src["source_type"],
                        "filename": src.get("filename", ""),
                        "raw_text": src.get("raw_text", ""),
                        "embedding_status": src.get("embedding_status", "pending"),
                        "chunk_count": src.get("chunk_count", 0),
                        "total_token_count": src.get("total_token_count", 0),
                    },
                )

        # Add sample conversations
        if students:
            for cdata in CHATBOT_CONVERSATIONS:
                chatbot = chatbots[cdata["chatbot_index"]]
                student = students[cdata["chatbot_index"] % len(students)]
                AIChatbotConversation.objects.get_or_create(
                    chatbot=chatbot,
                    student=student,
                    tenant=tenant,
                    defaults={
                        "title": f"Chat with {chatbot.name}",
                        "messages": cdata["messages"],
                        "message_count": len(cdata["messages"]),
                    },
                )

        self.stdout.write(f"  Chatbots: {len(chatbots)} seeded with knowledge and conversations")
        return chatbots

    def _create_progress(self, tenant, teachers, students, courses):
        now = timezone.now()
        progress_count = 0

        all_learners = teachers + students
        for learner in all_learners:
            for i, course in enumerate(courses):
                if not course.is_published:
                    continue

                # Vary progress status based on user + course combination
                combo = hash(f"{learner.id}-{course.id}") % 10

                if combo < 3:
                    status = "COMPLETED"
                    pct = Decimal("100.00")
                    started = now - timedelta(days=30 + combo * 5)
                    completed = now - timedelta(days=combo * 2)
                elif combo < 7:
                    status = "IN_PROGRESS"
                    pct = Decimal(str(20 + combo * 10))
                    started = now - timedelta(days=15 + combo * 3)
                    completed = None
                else:
                    status = "NOT_STARTED"
                    pct = Decimal("0.00")
                    started = None
                    completed = None

                _, created = TeacherProgress.objects.all_tenants().get_or_create(
                    tenant=tenant,
                    teacher=learner,
                    course=course,
                    content=None,
                    defaults={
                        "status": status,
                        "progress_percentage": pct,
                        "started_at": started,
                        "completed_at": completed,
                    },
                )
                if created:
                    progress_count += 1

        self.stdout.write(f"  Progress records: {progress_count} created")

    def _update_existing_classrooms(self, tenant):
        """Make some existing READY classrooms public so students can browse them."""
        updated = MAICClassroom.objects.all_tenants().filter(
            tenant=tenant,
            status="READY",
            is_public=False,
        ).exclude(
            title__in=[c["title"] for c in MAIC_CLASSROOMS],
        ).update(is_public=True)

        if updated:
            self.stdout.write(f"  Made {updated} existing READY classrooms public")

    def _print_summary(self, tenant, teachers, students, courses, classrooms, chatbots=None):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS(f"  Seed Complete — {tenant.name}"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        self.stdout.write(f"\n  Login URL: http://{tenant.subdomain}.localhost:3000/login\n")

        # Admin credentials
        admin = User.objects.filter(tenant=tenant, role="SCHOOL_ADMIN").first()
        if admin:
            self.stdout.write(f"  {'Role':<15} {'Email':<45} {'Password'}")
            self.stdout.write(f"  {'-'*15} {'-'*45} {'-'*12}")
            self.stdout.write(f"  {'SCHOOL_ADMIN':<15} {admin.email:<45} Admin@123")

        # Teacher credentials
        for t in TEACHERS:
            self.stdout.write(f"  {'TEACHER':<15} {t['email']:<45} Teacher@123")

        # Student credentials
        for s in STUDENTS:
            self.stdout.write(f"  {'STUDENT':<15} {s['email']:<45} Student@123")

        # Stats
        ready_count = sum(1 for c in classrooms if c.status == "READY")
        public_count = sum(1 for c in classrooms if c.is_public)
        total_maic = MAICClassroom.objects.all_tenants().filter(tenant=tenant).count()

        self.stdout.write(f"\n  Data Summary:")
        self.stdout.write(f"    Teachers:        {len(teachers)}")
        self.stdout.write(f"    Students:        {len(students)}")
        self.stdout.write(f"    Courses:         {len(courses)} ({sum(1 for c in courses if c.is_published)} published)")
        self.stdout.write(f"    MAIC Classrooms: {total_maic} total ({ready_count} ready, {public_count} public)")
        if chatbots:
            active_bots = sum(1 for b in chatbots if b.is_active)
            self.stdout.write(f"    AI Chatbots:     {len(chatbots)} total ({active_bots} active)")
        self.stdout.write(f"    AI Config:       {tenant.subdomain} — MAIC enabled")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write("")
