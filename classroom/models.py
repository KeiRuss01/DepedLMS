from django.db import models
from django.utils.crypto import get_random_string

from accounts.models import Student, Teacher


def generate_class_code():
    """
    Generates a code such as: A7KM92Q

    Confusing characters such as I, O, 0, and 1 are excluded.
    """
    characters = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return get_random_string(7, characters)


class Classroom(models.Model):
    class Quarter(models.TextChoices):
        FIRST = "1", "First Quarter"
        SECOND = "2", "Second Quarter"
        THIRD = "3", "Third Quarter"
        FOURTH = "4", "Fourth Quarter"

    class_id = models.AutoField(primary_key=True)

    # One class belongs to one Teacher.
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name="created_classes",
        db_column="teacher_id",
    )

    class_name = models.CharField(max_length=100)

    class_code = models.CharField(
        max_length=10,
        unique=True,
        default=generate_class_code,
        editable=False,
    )

    grade_level = models.CharField(max_length=50)
    subject = models.CharField(max_length=100)
    section = models.CharField(max_length=100)
    school_year = models.CharField(max_length=20)
    description = models.TextField(blank=True)

    quarter = models.CharField(
        max_length=1,
        choices=Quarter.choices,
        default=Quarter.FIRST,
    )

    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "class"
        ordering = ["subject", "section"]

    def __str__(self):
        return f"{self.class_name} - {self.section}"


class ClassEnrollment(models.Model):
    class Status(models.TextChoices):
        PENDING_STUDENT = "pending_student", "Waiting for Student"
        PENDING_TEACHER = "pending_teacher", "Waiting for Teacher"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    enrollment_id = models.AutoField(primary_key=True)

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

    requested_at = models.DateTimeField(auto_now_add=True)
    enrolled_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "class_enrollment"

        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "student"],
                name="unique_classroom_student",
            )
        ]

    def __str__(self):
        return (
            f"{self.student} - "
            f"{self.classroom} - "
            f"{self.get_status_display()}"
        )