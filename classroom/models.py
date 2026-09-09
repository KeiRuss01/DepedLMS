from django.db import models
from django.utils.crypto import get_random_string
from django.core.validators import MinValueValidator, MaxValueValidator

from accounts.models import Student, Teacher

from .module_storage import (
    learning_storage,
    module_pdf_path,
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
        return f"{self.student} — {self.module}"


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
        return f"{self.submission_id} — {self.item}"