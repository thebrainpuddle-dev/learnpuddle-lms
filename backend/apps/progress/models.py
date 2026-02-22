# apps/progress/models.py

from django.db import models
import uuid

from utils.soft_delete import SoftDeleteMixin, SoftDeleteManager


class TeacherProgress(models.Model):
    """
    Tracks teacher progress through courses and content.
    """
    STATUS_CHOICES = [
        ('NOT_STARTED', 'Not Started'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Relationships
    teacher = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='progress')
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='progress')
    content = models.ForeignKey('courses.Content', on_delete=models.CASCADE, related_name='progress', null=True, blank=True)
    
    # Progress tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NOT_STARTED')
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(auto_now=True)
    
    # Video-specific tracking
    video_progress_seconds = models.PositiveIntegerField(default=0, help_text="Seconds watched")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'teacher_progress'
        unique_together = [('teacher', 'course', 'content')]
        indexes = [
            models.Index(fields=['teacher', 'course']),
            models.Index(fields=['teacher', 'status']),
            models.Index(fields=['course', 'status']),
            # For dashboard queries
            models.Index(fields=['teacher', 'status', 'completed_at']),
            models.Index(fields=['last_accessed']),
        ]
    
    def __str__(self):
        return f"{self.teacher.email} - {self.course.title} - {self.status}"


class Assignment(SoftDeleteMixin, models.Model):
    """
    Assignments within courses.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='assignments')
    module = models.ForeignKey('courses.Module', on_delete=models.CASCADE, related_name='assignments', null=True, blank=True)

    # Optional link to the content that generated this assignment (e.g. auto-generated from video)
    content = models.ForeignKey(
        'courses.Content',
        on_delete=models.CASCADE,
        related_name='assignments',
        null=True,
        blank=True,
    )
    
    title = models.CharField(max_length=300)
    description = models.TextField()
    instructions = models.TextField(blank=True)
    
    # Due date
    due_date = models.DateTimeField(null=True, blank=True)
    
    # Grading
    max_score = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    passing_score = models.DecimalField(max_digits=5, decimal_places=2, default=70)

    GENERATION_SOURCE_CHOICES = [
        ("MANUAL", "Manual"),
        ("VIDEO_AUTO", "Auto-generated from video"),
    ]
    generation_source = models.CharField(
        max_length=20,
        choices=GENERATION_SOURCE_CHOICES,
        default="MANUAL",
    )
    generation_metadata = models.JSONField(blank=True, default=dict)
    
    is_mandatory = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'assignments'
        ordering = ['course', 'due_date']
        indexes = [
            models.Index(fields=['course', 'is_active']),
            models.Index(fields=['due_date', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Quiz(models.Model):
    """
    Quiz structure associated with an Assignment.
    (Reflection assignments will not have a related Quiz.)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.OneToOneField(Assignment, on_delete=models.CASCADE, related_name="quiz")

    schema_version = models.PositiveSmallIntegerField(default=1)
    is_auto_generated = models.BooleanField(default=False)
    generation_model = models.CharField(max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quizzes"

    def __str__(self):
        return f"Quiz({self.assignment_id})"


class QuizQuestion(models.Model):
    """
    Quiz questions (MCQ and short-answer).
    """

    QUESTION_TYPE_CHOICES = [
        ("MCQ", "Multiple Choice"),
        ("SHORT_ANSWER", "Short Answer"),
        ("TRUE_FALSE", "True/False"),
    ]

    SELECTION_MODE_CHOICES = [
        ("SINGLE", "Single Select"),
        ("MULTIPLE", "Multiple Select"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")

    order = models.PositiveIntegerField(default=0)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES)
    selection_mode = models.CharField(max_length=20, choices=SELECTION_MODE_CHOICES, default="SINGLE")
    prompt = models.TextField()

    # For MCQ: options is a list of strings. For SHORT_ANSWER: typically empty.
    options = models.JSONField(blank=True, default=list)

    # For MCQ: {"option_index": 2}. For SHORT_ANSWER: {"text": "..."} (optional).
    correct_answer = models.JSONField(blank=True, default=dict)
    explanation = models.TextField(blank=True, default="")
    points = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quiz_questions"
        ordering = ["quiz", "order"]
        indexes = [
            models.Index(fields=["quiz", "order"]),
        ]

    def __str__(self):
        return f"QuizQuestion({self.quiz_id}) #{self.order}"


class QuizSubmission(models.Model):
    """
    Teacher submissions for a quiz assignment.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="submissions")
    teacher = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name="quiz_submissions")

    # Answers keyed by question id: {"<question_uuid>": {...}}
    answers = models.JSONField(blank=True, default=dict)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quiz_submissions"
        unique_together = [("quiz", "teacher")]
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["teacher", "submitted_at"]),
        ]

    def __str__(self):
        return f"QuizSubmission({self.teacher_id}, {self.quiz_id})"


class AssignmentSubmission(models.Model):
    """
    Teacher assignment submissions.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SUBMITTED', 'Submitted'),
        ('GRADED', 'Graded'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    teacher = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='submissions')
    
    # Submission
    submission_text = models.TextField(blank=True)
    file_url = models.URLField(blank=True, help_text="S3 URL of uploaded file")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # Grading
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='graded_submissions')
    graded_at = models.DateTimeField(null=True, blank=True)
    
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'assignment_submissions'
        unique_together = [('assignment', 'teacher')]
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['assignment', 'status']),
            models.Index(fields=['teacher', 'status']),
            models.Index(fields=['submitted_at']),
        ]
    
    def __str__(self):
        return f"{self.teacher.email} - {self.assignment.title}"


class TeacherQuestClaim(models.Model):
    """
    Stores per-day quest reward claims to prevent duplicate rewards.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='quest_claims')
    quest_key = models.CharField(max_length=100)
    claim_date = models.DateField()
    points_awarded = models.PositiveIntegerField(default=0)
    claimed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'teacher_quest_claims'
        unique_together = [('teacher', 'quest_key', 'claim_date')]
        ordering = ['-claimed_at']
        indexes = [
            models.Index(fields=['teacher', 'claim_date']),
            models.Index(fields=['teacher', 'quest_key']),
        ]

    def __str__(self):
        return f"{self.teacher_id}::{self.quest_key}::{self.claim_date}"
