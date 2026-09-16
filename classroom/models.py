from django.db import models
from django.utils.crypto import get_random_string
from django.core.validators import MinValueValidator, MaxValueValidator

from accounts.models import Student, Teacher

from .module_storage import (
    learning_storage,
    module_pdf_path,
    student_module_pdf_path,
    submission_file_path,
)


# =========================================================
# CLASS CODE GENERATOR
# =========================================================

def generate_class_code():
    """
    Generates a code such as: A7KM92Q

    Confusing characters such as I, O, 0, and 1 are excluded.
    """
    characters = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return get_random_string(7, characters)


# =========================================================
# CLASSROOM
# =========================================================

class Classroom(models.Model):

    class Quarter(models.TextChoices):
        FIRST = "1", "First Quarter"
        SECOND = "2", "Second Quarter"
        THIRD = "3", "Third Quarter"
        FOURTH = "4", "Fourth Quarter"

    class_id = models.AutoField(
        primary_key=True
    )

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name="created_classes",
        db_column="teacher_id",
    )

    class_name = models.CharField(
        max_length=100
    )

    class_code = models.CharField(
        max_length=10,
        unique=True,
        default=generate_class_code,
        editable=False,
    )

    grade_level = models.CharField(
        max_length=50
    )

    subject = models.CharField(
        max_length=100
    )

    section = models.CharField(
        max_length=100
    )

    school_year = models.CharField(
        max_length=20
    )

    description = models.TextField(
        blank=True
    )

    quarter = models.CharField(
        max_length=1,
        choices=Quarter.choices,
        default=Quarter.FIRST,
    )

    is_archived = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        db_table = "class"
        ordering = ["subject", "section"]

    def __str__(self):
        return f"{self.class_name} - {self.section}"


# =========================================================
# CLASS ENROLLMENT
# =========================================================

class ClassEnrollment(models.Model):

    class Status(models.TextChoices):
        PENDING_STUDENT = (
            "pending_student",
            "Waiting for Student"
        )

        PENDING_TEACHER = (
            "pending_teacher",
            "Waiting for Teacher"
        )

        APPROVED = (
            "approved",
            "Approved"
        )

        REJECTED = (
            "rejected",
            "Rejected"
        )

    enrollment_id = models.AutoField(
        primary_key=True
    )

    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="enrollments",
        db_column="class_id",
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="class_enrollments",
        db_column="student_id",
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
    )

    requested_at = models.DateTimeField(
        auto_now_add=True
    )

    enrolled_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "class_enrollment"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "classroom",
                    "student",
                ],
                name="unique_classroom_student",
            )
        ]

    def __str__(self):
        return (
            f"{self.student} - "
            f"{self.classroom} - "
            f"{self.get_status_display()}"
        )


# =========================================================
# MODULE
# =========================================================

class Module(models.Model):

    class Term(models.TextChoices):
        FIRST = "1", "Term 1"
        SECOND = "2", "Term 2"
        THIRD = "3", "Term 3"

    class AnswerMode(models.TextChoices):
        STRUCTURED = (
            "structured",
            "Numbered answer sheet"
        )

        WRITTEN = (
            "written",
            "Written response"
        )

        FILE = (
            "file",
            "Answer file"
        )

    class Status(models.TextChoices):
        DRAFT = (
            "draft",
            "Draft"
        )

        PUBLISHED = (
            "published",
            "Published"
        )

    module_id = models.AutoField(
        primary_key=True
    )

    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="modules",
    )

    title = models.CharField(
        max_length=150
    )

    instructions = models.TextField(
        blank=True
    )

    pdf = models.FileField(
        upload_to=module_pdf_path,
        storage=learning_storage,
    )

    student_pdf = models.FileField(
        upload_to=student_module_pdf_path,
        storage=learning_storage,
        blank=True,
    )

    hidden_pages = models.CharField(
        max_length=250,
        blank=True,
        help_text="Teacher-only PDF pages, for example: 18, 20-22",
    )

    week = models.CharField(
        max_length=50,
        blank=True,
    )

    term = models.CharField(
        max_length=1,
        choices=Term.choices,
        default=Term.FIRST,
    )

    answer_mode = models.CharField(
        max_length=20,
        choices=AnswerMode.choices,
        default=AnswerMode.STRUCTURED,
    )

    max_score = models.PositiveIntegerField(
        default=10,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(10000),
        ],
    )

    due_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    allow_late = models.BooleanField(
        default=False
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    published_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "learning_module"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def grading_component(self):
        return "Written Work"

    @property
    def total_points(self):
        return sum(
            section.max_score
            for section in self.answer_sections.all()
            if section.include_in_grade
        )


# =========================================================
# MODULE ANSWER SECTION
# =========================================================

class ModuleAnswerSection(models.Model):

    class AnswerMethod(models.TextChoices):
        STRUCTURED = "structured", "Structured answer sheet"
        WRITTEN = "written", "Written workspace"
        FILE = "file", "File or photo submission"
        NONE = "none", "No answer required"

    class GradingComponent(models.TextChoices):
        WRITTEN_WORK = "written_work", "Written Work"
        PERFORMANCE_TASK = "performance_task", "Performance Task"
        ASSESSMENT = "assessment", "Assessment"
        NOT_GRADED = "not_graded", "Not graded"

    section_id = models.AutoField(primary_key=True)
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="answer_sections",
    )
    title = models.CharField(max_length=150)
    instructions = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=1)
    page_start = models.PositiveIntegerField(blank=True, null=True)
    page_end = models.PositiveIntegerField(blank=True, null=True)
    answer_method = models.CharField(
        max_length=20,
        choices=AnswerMethod.choices,
        default=AnswerMethod.STRUCTURED,
    )
    required = models.BooleanField(default=True)
    max_score = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(0), MaxValueValidator(10000)],
    )
    include_in_grade = models.BooleanField(default=True)
    grading_component = models.CharField(
        max_length=30,
        choices=GradingComponent.choices,
        default=GradingComponent.WRITTEN_WORK,
    )
    max_files = models.PositiveSmallIntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )

    class Meta:
        db_table = "module_answer_section"
        ordering = ["position", "section_id"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # A Module is one complete Written Work item. Its answerable
        # sections contribute to the Module total; they are not separate
        # gradebook components.
        if self.answer_method == self.AnswerMethod.NONE:
            self.max_score = 0
            self.include_in_grade = False
            self.grading_component = self.GradingComponent.NOT_GRADED
        else:
            self.include_in_grade = True
            self.grading_component = self.GradingComponent.WRITTEN_WORK
        super().save(*args, **kwargs)

    @property
    def needs_manual_grading(self):
        if self.answer_method in [self.AnswerMethod.WRITTEN, self.AnswerMethod.FILE]:
            return True
        return self.questions.filter(
            question_type__in=[
                SectionQuestion.QuestionType.SHORT,
                SectionQuestion.QuestionType.LONG,
            ]
        ).exists()


class SectionQuestion(models.Model):

    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "multiple_choice", "Multiple choice"
        TRUE_FALSE = "true_false", "True or false"
        IDENTIFICATION = "identification", "Identification"
        NUMBER = "number", "Number"
        SHORT = "short", "Short answer"
        LONG = "long", "Essay / long answer"

    question_id = models.AutoField(primary_key=True)
    section = models.ForeignKey(
        ModuleAnswerSection,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    position = models.PositiveIntegerField(default=1)
    prompt = models.TextField()
    question_type = models.CharField(
        max_length=25,
        choices=QuestionType.choices,
        default=QuestionType.SHORT,
    )
    choices_text = models.TextField(
        blank=True,
        help_text="Enter one choice per line.",
    )
    correct_answer = models.TextField(
        blank=True,
        help_text="Leave blank when the Teacher will check the answer.",
    )
    points = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0)],
    )
    required = models.BooleanField(default=True)

    class Meta:
        db_table = "module_section_question"
        ordering = ["position", "question_id"]

    def __str__(self):
        return self.prompt[:80]

    @property
    def choices(self):
        return [line.strip() for line in self.choices_text.splitlines() if line.strip()]


# =========================================================
# MODULE ITEM
# =========================================================

class ModuleItem(models.Model):

    class AnswerType(models.TextChoices):
        SHORT = (
            "short",
            "Short answer"
        )

        CHOICE = (
            "choice",
            "Multiple choice: A-D"
        )

        LONG = (
            "long",
            "Long answer"
        )

    item_id = models.AutoField(
        primary_key=True
    )

    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="items",
    )

    position = models.PositiveIntegerField()

    # Example:
    # Activity A, page 4, item 1
    #
    # The actual question can remain inside the PDF.
    label = models.CharField(
        max_length=250
    )

    answer_type = models.CharField(
        max_length=20,
        choices=AnswerType.choices,
        default=AnswerType.SHORT,
    )

    class Meta:
        db_table = "module_item"
        ordering = ["position"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "module",
                    "position",
                ],
                name="unique_module_item_position",
            )
        ]

    def __str__(self):
        return self.label


# =========================================================
# MODULE SUBMISSION
# =========================================================

class ModuleSubmission(models.Model):

    class Status(models.TextChoices):
        DRAFT = (
            "draft",
            "Draft"
        )

        SUBMITTED = (
            "submitted",
            "Submitted"
        )

        GRADED = (
            "graded",
            "Graded"
        )

        RETURNED = (
            "returned",
            "Returned for revision"
        )

    submission_id = models.AutoField(
        primary_key=True
    )

    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="submissions",
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name="module_submissions",
    )

    # Used when:
    # Module.answer_mode == "written"
    written_answer = models.TextField(
        blank=True
    )

    # Used when:
    # Module.answer_mode == "file"
    answer_file = models.FileField(
        upload_to=submission_file_path,
        storage=learning_storage,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    submitted_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    score = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        blank=True,
        null=True,
    )

    feedback = models.TextField(
        blank=True
    )

    graded_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        db_table = "module_submission"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "module",
                    "student",
                ],
                name="unique_module_student_submission",
            )
        ]

    @property
    def is_late(self):
        return bool(
            self.submitted_at
            and self.module.due_at
            and self.submitted_at > self.module.due_at
        )

    def __str__(self):
        return f"{self.student} - {self.module}"

    def update_total_score(self):
        graded_responses = self.section_responses.filter(
            section__include_in_grade=True,
            score__isnull=False,
        )
        self.score = sum(response.score for response in graded_responses)
        self.save(update_fields=["score", "updated_at"])


class SectionResponse(models.Model):
    response_id = models.AutoField(primary_key=True)
    submission = models.ForeignKey(
        ModuleSubmission,
        on_delete=models.CASCADE,
        related_name="section_responses",
    )
    section = models.ForeignKey(
        ModuleAnswerSection,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    written_answer = models.TextField(blank=True)
    is_complete = models.BooleanField(default=False)
    auto_score = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
    )
    score = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        blank=True,
        null=True,
    )
    feedback = models.TextField(blank=True)
    graded_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "module_section_response"
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "section"],
                name="unique_submission_section_response",
            )
        ]

    def __str__(self):
        return f"{self.submission} - {self.section}"


class SectionAnswer(models.Model):
    answer_id = models.AutoField(primary_key=True)
    response = models.ForeignKey(
        SectionResponse,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        SectionQuestion,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    answer_text = models.TextField(blank=True)
    is_correct = models.BooleanField(blank=True, null=True)
    awarded_points = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
    )

    class Meta:
        db_table = "module_section_answer"
        constraints = [
            models.UniqueConstraint(
                fields=["response", "question"],
                name="unique_response_question_answer",
            )
        ]


class SubmissionAttachment(models.Model):
    attachment_id = models.AutoField(primary_key=True)
    response = models.ForeignKey(
        SectionResponse,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(
        upload_to=submission_file_path,
        storage=learning_storage,
    )
    original_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "module_submission_attachment"


# =========================================================
# MODULE ANSWER
# =========================================================

class ModuleAnswer(models.Model):

    answer_id = models.AutoField(
        primary_key=True
    )

    submission = models.ForeignKey(
        ModuleSubmission,
        on_delete=models.CASCADE,
        related_name="answers",
    )

    item = models.ForeignKey(
        ModuleItem,
        on_delete=models.CASCADE,
        related_name="answers",
    )

    answer_text = models.TextField(
        blank=True
    )

    class Meta:
        db_table = "module_answer"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "submission",
                    "item",
                ],
                name="unique_submission_item_answer",
            )
        ]

    def __str__(self):
        return f"{self.submission_id} - {self.item}"


# =========================================================
# CLASS GRADEBOOK
# =========================================================

class GradebookSettings(models.Model):
    """Component weights used by one class record."""

    classroom = models.OneToOneField(
        Classroom,
        on_delete=models.CASCADE,
        related_name="gradebook_settings",
    )
    written_work_weight = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    performance_task_weight = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    assessment_weight = models.PositiveSmallIntegerField(
        default=20,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    term_1_released = models.BooleanField(default=False)
    term_2_released = models.BooleanField(default=False)
    term_3_released = models.BooleanField(default=False)

    class Meta:
        db_table = "gradebook_settings"

    def __str__(self):
        return f"Gradebook settings - {self.classroom}"


class GradeItem(models.Model):
    """One column in a term class record."""

    class Component(models.TextChoices):
        WRITTEN_WORK = "written_work", "Written Work"
        PERFORMANCE_TASK = "performance_task", "Performance Task"
        ASSESSMENT = "assessment", "Quarterly Assessment"

    item_id = models.AutoField(primary_key=True)
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.CASCADE,
        related_name="grade_items",
    )
    module = models.OneToOneField(
        Module,
        on_delete=models.CASCADE,
        related_name="grade_item",
        blank=True,
        null=True,
    )
    term = models.CharField(max_length=1, choices=Module.Term.choices)
    component = models.CharField(max_length=30, choices=Component.choices)
    title = models.CharField(max_length=150)
    highest_possible_score = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    position = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "grade_item"
        ordering = ["term", "component", "position", "item_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "term", "component", "position"],
                name="unique_grade_item_position",
            )
        ]

    @property
    def is_module(self):
        return self.module_id is not None

    def __str__(self):
        return f"{self.classroom} - {self.title}"


class GradeScore(models.Model):
    score_id = models.AutoField(primary_key=True)
    item = models.ForeignKey(
        GradeItem,
        on_delete=models.CASCADE,
        related_name="scores",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="grade_scores",
    )
    score = models.DecimalField(max_digits=8, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "grade_score"
        constraints = [
            models.UniqueConstraint(
                fields=["item", "student"],
                name="unique_grade_item_student_score",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.item}: {self.score}"
