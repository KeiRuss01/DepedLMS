"""
accounts app
============
This app is the single source of truth for authentication and for every
role's "personal info" profile (Principal, Teacher, Student, Parent,
Supervisor). It intentionally does NOT contain any views/templates for the
public marketing site (that stays in `landing`) or for the supervisor
dashboard (that lives in its own `supervisor` app) -- it only holds the
models + admin registration that every other app will import from.

Design notes (please read before running migrations):

1. `User` is a CUSTOM Django auth user model (settings.AUTH_USER_MODEL =
   "accounts.User"). This is what lets someone actually "log in" -- Django's
   session/auth machinery, password hashing, `login()`/`logout()`, and the
   `@login_required` decorator all work against this table. It matches
   Table 3.1 (email, password, role, phone_number, status, created_at,
   updated_at) with two small, necessary differences:
     - `password` is 128 chars, not 100. Django's password hashers (PBKDF2/
       Argon2) produce strings longer than 100 chars, so 100 would truncate
       and silently break login. Keep it at 128.
     - `is_staff` / `is_superuser` / `last_login` are added because
       PermissionsMixin/Django admin require them. They don't appear in your
       ERD but are effectively "free" plumbing columns.

2. `Table 3.2 (School)` wasn't included in what you sent me (only Users,
   Principal, Teacher, Student, Parent were). Principal/Teacher/Student all
   have a `school_id` FK though, so I added a minimal `School` model here as
   a placeholder so the foreign keys have somewhere to point. Swap in your
   real Table 3.2 columns whenever you're ready -- just don't rename the
   table (`db_table = "school"`) and the FKs elsewhere won't need to change.

3. `Supervisor` isn't in your table images either, but you asked for
   "supervisor for their personal info" and a supervisor login, so I added
   Table-3.x-style Supervisor profile modeled the same way as Principal
   (employee_id, name parts, designation) plus a `district` field since the
   district supervisor is the head of the whole system, not tied to one
   school. Adjust freely.

4. Student <-> Parent circular reference: your Table 3.5 has
   `student.parent_id -> parent`, and your Table 3.6 has
   `parent.student_id -> student` (the doc says "referencing School table"
   but that's almost certainly a typo for "Student table"). That's a genuine
   circular foreign key. I implemented both exactly as documented, but made
   both sides nullable so Django/MySQL can create the tables without a
   chicken-and-egg error, and so you can create a Parent first, then a
   Student, then link them. In practice one parent usually has more than one
   child, so `Student.parent` (many students -> one parent) is the
   relationship you'll actually use day-to-day; `Parent.student` is kept
   only because your spec lists it. If you don't need it, it's safe to drop
   later.
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import FileExtensionValidator
from django.db import models


# ---------------------------------------------------------------------------
# Table 3.1 - Users (this is the AUTH_USER_MODEL)
# ---------------------------------------------------------------------------
class UserManager(BaseUserManager):
    """Manager for the custom User model. Users log in with email, not a
    separate 'username' field."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.SUPERVISOR)
        extra_fields.setdefault("status", User.Status.ACTIVE)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Table 3.1 - Users. Main account table shared by every role."""

    class Role(models.TextChoices):
        SUPERVISOR = "supervisor", "District Supervisor"
        PRINCIPAL = "principal", "Principal"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"
        PARENT = "parent", "Parent"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        SUSPENDED = "suspended", "Suspended"

    user_id = models.AutoField(primary_key=True)
    email = models.EmailField("email address", max_length=100, unique=True)
    # NOTE: `password` field (max_length=128) is provided by AbstractBaseUser.
    role = models.CharField(max_length=20, choices=Role.choices)
    phone_number = models.CharField(max_length=11, blank=True, null=True)
    profile_picture = models.ImageField(
        upload_to="profile_pictures/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "webp"])
        ],
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Required by Django's auth/admin machinery.
    is_staff = models.BooleanField(
        default=False, help_text="Can access the Django admin site."
    )
    # `is_superuser` and all group/permission fields come from PermissionsMixin.

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["role"]

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"

    @property
    def is_active(self):
        """Django's auth backend checks `is_active` to decide whether login
        is allowed. We derive it from the business-facing `status` enum
        instead of keeping two separate booleans in sync by hand."""
        return self.status == self.Status.ACTIVE

    @is_active.setter
    def is_active(self, value):
        self.status = self.Status.ACTIVE if value else self.Status.INACTIVE

    @property
    def full_name(self):
        profile = (
            getattr(self, "supervisor_profile", None)
            or getattr(self, "principal_profile", None)
            or getattr(self, "teacher_profile", None)
            or getattr(self, "student_profile", None)
            or getattr(self, "parent_profile", None)
        )
        if not profile:
            return self.email
        parts = [
            getattr(profile, "firstname", ""),
            getattr(profile, "middlename", ""),
            getattr(profile, "lastname", ""),
            getattr(profile, "suffix", ""),
        ]
        return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Table 3.2 (placeholder) - School
# Referenced as school_id by Principal / Teacher / Student. Replace with your
# real column set whenever that table's spec is ready.
# ---------------------------------------------------------------------------
class School(models.Model):
    school_id = models.AutoField(primary_key=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_schools",
    )
    school_name = models.CharField(max_length=150)
    logo = models.FileField(
        upload_to="school_logos/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"])],
    )
    school_id_number = models.CharField(
        "DepEd School ID", max_length=20, blank=True, null=True
    )
    region = models.CharField(max_length=100, blank=True, null=True)
    division = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "school"
        verbose_name = "School"
        verbose_name_plural = "Schools"

    def __str__(self):
        return self.school_name


# ---------------------------------------------------------------------------
# Table 3.3 - Principal
# ---------------------------------------------------------------------------
class Principal(models.Model):
    principal_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="principal_profile",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        db_column="school_id",
        related_name="principals",
    )
    employee_id = models.CharField("DepEd Employee ID", max_length=50)
    firstname = models.CharField(max_length=100)
    middlename = models.CharField(max_length=100, blank=True, null=True)
    lastname = models.CharField(max_length=100)
    suffix = models.CharField(max_length=20, blank=True, null=True)
    designation = models.CharField(max_length=150, blank=True, null=True)

    class Meta:
        db_table = "principal"
        verbose_name = "Principal"
        verbose_name_plural = "Principals"
        constraints = [
            models.UniqueConstraint(
                fields=["school"],
                name="unique_principal_per_school",
            )
        ]

    def __str__(self):
        return f"{self.firstname} {self.lastname}"


# ---------------------------------------------------------------------------
# Table 3.4 - Teacher
# ---------------------------------------------------------------------------
class Teacher(models.Model):
    teacher_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="teacher_profile",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        db_column="school_id",
        related_name="teachers",
    )
    employee_id = models.CharField("DepEd Employee ID", max_length=50)
    firstname = models.CharField(max_length=100)
    middlename = models.CharField(max_length=100, blank=True, null=True)
    lastname = models.CharField(max_length=100)
    suffix = models.CharField(max_length=20, blank=True, null=True)
    specialization = models.CharField(max_length=100, blank=True, null=True)
    designation = models.CharField(
        max_length=100,
        blank=True,
        default="Teacher",
    )

    class Meta:
        db_table = "teacher"
        verbose_name = "Teacher"
        verbose_name_plural = "Teachers"

    def __str__(self):
        return f"{self.firstname} {self.lastname}"


# ---------------------------------------------------------------------------
# Table 3.6 - Parent  (defined before Student so Student can FK to it)
# ---------------------------------------------------------------------------
class Parent(models.Model):
    class Relationship(models.TextChoices):
        MOTHER = "mother", "Mother"
        FATHER = "father", "Father"
        GUARDIAN = "guardian", "Guardian"
        OTHER = "other", "Other"

    parent_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="parent_profile",
    )
    # Per Table 3.6. Kept nullable to break the Student<->Parent circular FK
    # (see module docstring). Most lookups should go through
    # `student.parent` / `parent.children` instead of this field.
    student = models.ForeignKey(
        "Student",
        on_delete=models.SET_NULL,
        db_column="student_id",
        related_name="parent_table_links",
        blank=True,
        null=True,
    )
    firstname = models.CharField(max_length=100)
    middlename = models.CharField(max_length=100, blank=True, null=True)
    lastname = models.CharField(max_length=100)
    relationship = models.CharField(max_length=20, choices=Relationship.choices)

    class Meta:
        db_table = "parent"
        verbose_name = "Parent"
        verbose_name_plural = "Parents"

    def __str__(self):
        return f"{self.firstname} {self.lastname}"


# ---------------------------------------------------------------------------
# Table 3.5 - Student
# ---------------------------------------------------------------------------
class Student(models.Model):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"

    class AccStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    student_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="student_profile",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        db_column="school_id",
        related_name="students",
    )
    parent = models.ForeignKey(
        Parent,
        on_delete=models.SET_NULL,
        db_column="parent_id",
        related_name="children",
        blank=True,
        null=True,
    )
    lrn = models.CharField("Learner Reference Number", max_length=20, unique=True)
    firstname = models.CharField(max_length=100)
    middlename = models.CharField(max_length=100, blank=True, null=True)
    lastname = models.CharField(max_length=100)
    suffix = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    birth_date = models.DateField()
    address = models.TextField(blank=True, null=True)
    acc_status = models.CharField(
        max_length=20, choices=AccStatus.choices, default=AccStatus.PENDING
    )
    approved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "student"
        verbose_name = "Student"
        verbose_name_plural = "Students"

    def __str__(self):
        return f"{self.firstname} {self.lastname} ({self.lrn})"


# ---------------------------------------------------------------------------
# Parent and Student connection
# A Parent sends a request using the learner's LRN. The Student decides
# whether to approve or reject the connection.
# ---------------------------------------------------------------------------
class ParentStudentLink(models.Model):
    class Relationship(models.TextChoices):
        MOTHER = "mother", "Mother"
        FATHER = "father", "Father"
        GUARDIAN = "guardian", "Guardian"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for Student"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        REVOKED = "revoked", "Revoked"

    link_id = models.AutoField(primary_key=True)
    parent = models.ForeignKey(
        Parent,
        on_delete=models.CASCADE,
        related_name="student_links",
        db_column="parent_id",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="parent_links",
        db_column="student_id",
    )
    relationship = models.CharField(
        max_length=20,
        choices=Relationship.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "parent_student_link"
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student"],
                name="unique_parent_student_link",
            )
        ]

    def __str__(self):
        return (
            f"{self.parent} - {self.student} - "
            f"{self.get_status_display()}"
        )


# ---------------------------------------------------------------------------
# Supervisor (not in the tables you sent, added per your request)
# The district supervisor is the head of the whole system, so this profile
# is not tied to a single school.
# ---------------------------------------------------------------------------
class Supervisor(models.Model):
    supervisor_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="supervisor_profile",
    )
    employee_id = models.CharField("DepEd Employee ID", max_length=50)
    firstname = models.CharField(max_length=100)
    middlename = models.CharField(max_length=100, blank=True, null=True)
    lastname = models.CharField(max_length=100)
    suffix = models.CharField(max_length=20, blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)
    designation = models.CharField(
        max_length=150, default="District Supervisor", blank=True
    )

    class Meta:
        db_table = "supervisor"
        verbose_name = "Supervisor"
        verbose_name_plural = "Supervisors"

    def __str__(self):
        return f"{self.firstname} {self.lastname}"

# ---------------------------------------------------------------------------
# User interface and notification preferences
# ---------------------------------------------------------------------------
class UserPreference(models.Model):
    class Theme(models.TextChoices):
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    class TextSize(models.TextChoices):
        SMALL = "small", "Small"
        DEFAULT = "default", "Default"
        LARGE = "large", "Large"
    
    class DefaultTerm(models.TextChoices):
        FIRST = "1", "Term 1"
        SECOND = "2", "Term 2"
        THIRD = "3", "Term 3"

    class DefaultGradingComponent(models.TextChoices):
        WRITTEN_WORK = "written_work", "Written Works"
        PERFORMANCE_TASK = "performance_task", "Performance Tasks"
        ASSESSMENT = "assessment", "Quarterly Assessment"

    preference_id = models.AutoField(primary_key=True)

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="preferences",
        db_column="user_id",
    )

    theme = models.CharField(
        max_length=10,
        choices=Theme.choices,
        default=Theme.LIGHT,
    )

    text_size = models.CharField(
        max_length=10,
        choices=TextSize.choices,
        default=TextSize.DEFAULT,
    )

    # Optional device/interface preferences
    sound_enabled = models.BooleanField(default=True)
    vibration_enabled = models.BooleanField(default=True)

    # Optional Teacher in-app notifications
    new_submission_alerts = models.BooleanField(default=True)
    pending_join_request_alerts = models.BooleanField(default=True)
    deadline_reminder_alerts = models.BooleanField(default=True)

    default_term = models.CharField(
        max_length=1,
        choices=DefaultTerm.choices,
        default=DefaultTerm.FIRST,
    )

    default_grading_component = models.CharField(
        max_length=30,
        choices=DefaultGradingComponent.choices,
        default=DefaultGradingComponent.WRITTEN_WORK,
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_preference"

    def __str__(self):
        return f"Preferences of {self.user.email}"

# ---------------------------------------------------------------------------
# Notifications displayed through the notification bell
# ---------------------------------------------------------------------------
class Notification(models.Model):
    class Type(models.TextChoices):
        MODULE = "module", "New Module"
        DEADLINE = "deadline", "Deadline Reminder"
        CLASS_ANNOUNCEMENT = (
            "class_announcement",
            "Class Announcement",
        )
        SCHOOL_ANNOUNCEMENT = (
            "school_announcement",
            "School Announcement",
        )
        SUBMISSION = "submission", "New Submission"
        JOIN_REQUEST = "join_request", "Join Request"
        GENERAL = "general", "General"

    notification_id = models.AutoField(primary_key=True)

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_column="recipient_id",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=Type.choices,
        default=Type.GENERAL,
    )

    title = models.CharField(max_length=150)
    message = models.TextField()

    # Internal page opened when the notification is selected.
    # Example: /classroom/modules/12/
    target_url = models.CharField(
        max_length=500,
        blank=True,
    )

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "notification"
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["recipient", "is_read", "created_at"],
                name="notification_lookup_idx",
            ),
        ]

    def __str__(self):
        return f"{self.title} — {self.recipient.email}"
