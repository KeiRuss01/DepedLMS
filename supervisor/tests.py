from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import Principal, School, Student, Teacher, User
from classroom.models import (
    AttendanceDay,
    AttendanceRecord,
    ClassEnrollment,
    Classroom,
)
from supervisor.forms import (
    _available_generated_email,
    _generated_temporary_password,
)


class GeneratedAccountCredentialTests(TestCase):
    def test_full_given_name_and_middle_name(self):
        email = _available_generated_email(
            "Keith Russel",
            "Bagsican",
            "Lacuna",
        )
        self.assertEqual(email, "lacuna.kr.b@gmail.com")

    def test_single_given_name_and_optional_middle_name(self):
        email = _available_generated_email("Keith", "", "Lacuna")
        self.assertEqual(email, "lacuna.k@gmail.com")

    def test_duplicate_email_receives_number(self):
        User.objects.create_user(
            email="lacuna.kr.b@gmail.com",
            password="ExistingPass123!",
            role=User.Role.PRINCIPAL,
        )
        email = _available_generated_email(
            "Keith Russel",
            "Bagsican",
            "Lacuna",
        )
        self.assertEqual(email, "lacuna.kr.b2@gmail.com")

    def test_password_uses_last_name_and_current_year(self):
        password = _generated_temporary_password("Lacuna")
        self.assertRegex(password, r"^Lacuna\d{4}$")


class SchoolAccessTests(TestCase):
    def setUp(self):
        self.supervisor_user = User.objects.create_user(
            email="supervisor@example.com",
            password="TestPass123!",
            role=User.Role.SUPERVISOR,
        )
        self.school_a = School.objects.create(
            school_name="School A",
            created_by=self.supervisor_user,
        )
        self.school_b = School.objects.create(
            school_name="School B",
            created_by=self.supervisor_user,
        )

        self.principal_user = User.objects.create_user(
            email="principal@example.com",
            password="TestPass123!",
            role=User.Role.PRINCIPAL,
        )
        self.principal = Principal.objects.create(
            user=self.principal_user,
            school=self.school_a,
            employee_id="P-001",
            firstname="Sample",
            lastname="Principal",
            designation="School Principal",
        )

        self.teacher_user = User.objects.create_user(
            email="teacher@example.com",
            password="TestPass123!",
            role=User.Role.TEACHER,
        )
        self.teacher = Teacher.objects.create(
            user=self.teacher_user,
            school=self.school_a,
            employee_id="T-001",
            firstname="Sample",
            lastname="Teacher",
        )

        student_user = User.objects.create_user(
            email="student@example.com",
            password="TestPass123!",
            role=User.Role.STUDENT,
        )
        self.student = Student.objects.create(
            user=student_user,
            school=self.school_a,
            lrn="123456789012",
            firstname="Sample",
            lastname="Student",
            gender=Student.Gender.MALE,
            birth_date=date(2010, 1, 1),
        )
        self.classroom = Classroom.objects.create(
            teacher=self.teacher,
            class_name="Science 8",
            grade_level="Grade 8",
            subject="Science",
            section="A",
            school_year="2026-2027",
        )
        self.enrollment = ClassEnrollment.objects.create(
            classroom=self.classroom,
            student=self.student,
            status=ClassEnrollment.Status.APPROVED,
        )

    def test_supervisor_can_view_any_school(self):
        self.client.force_login(self.supervisor_user)
        response = self.client.get(
            reverse("supervisor:school_detail", args=[self.school_b.school_id])
        )
        self.assertEqual(response.status_code, 200)

    def test_principal_can_only_view_assigned_school(self):
        self.client.force_login(self.principal_user)
        allowed = self.client.get(
            reverse("supervisor:school_detail", args=[self.school_a.school_id])
        )
        denied = self.client.get(
            reverse("supervisor:school_detail", args=[self.school_b.school_id])
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertRedirects(denied, reverse("supervisor:principal_dashboard"))

    def test_public_school_detail_shows_organization(self):
        response = self.client.get(
            reverse("school_detail", args=[self.school_a.school_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sample Principal")
        self.assertContains(response, "Sample Teacher")

    def test_school_detail_limits_teachers_to_five_per_page(self):
        for number in range(5):
            teacher_user = User.objects.create_user(
                email=f"teacher{number}@example.com",
                password="TestPass123!",
                role=User.Role.TEACHER,
            )
            Teacher.objects.create(
                user=teacher_user,
                school=self.school_a,
                employee_id=f"T-{number + 2:03d}",
                firstname=f"Teacher{number}",
                lastname="Additional",
            )

        self.client.force_login(self.principal_user)
        url = reverse("supervisor:school_detail", args=[self.school_a.school_id])
        first_page = self.client.get(url)
        second_page = self.client.get(url, {"teacher_page": 2})

        self.assertEqual(len(first_page.context["teachers"]), 5)
        self.assertEqual(len(second_page.context["teachers"]), 1)

    def test_school_detail_searches_teachers(self):
        self.client.force_login(self.principal_user)
        response = self.client.get(
            reverse("supervisor:school_detail", args=[self.school_a.school_id]),
            {"teacher_q": "teacher@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["teachers"]), 1)
        self.assertContains(response, "Sample Teacher")

    def test_principal_can_monitor_own_class_attendance_and_performance(self):
        attendance_day = AttendanceDay.objects.create(
            classroom=self.classroom,
            date=date(2026, 10, 29),
            recorded_by=self.teacher,
        )
        AttendanceRecord.objects.create(
            attendance_day=attendance_day,
            student=self.student,
            status=AttendanceRecord.Status.PRESENT,
        )
        self.client.force_login(self.principal_user)

        class_response = self.client.get(
            reverse(
                "supervisor:principal_class_detail",
                args=[self.classroom.pk],
            )
        )
        daily_response = self.client.get(
            reverse(
                "supervisor:principal_class_attendance",
                args=[self.classroom.pk],
            ),
            {"view": "daily", "date": "2026-10-29"},
        )
        monthly_response = self.client.get(
            reverse(
                "supervisor:principal_class_attendance",
                args=[self.classroom.pk],
            ),
            {"view": "monthly", "month": "2026-10"},
        )
        performance_response = self.client.get(
            reverse(
                "supervisor:principal_student_performance",
                args=[self.classroom.pk, self.student.pk],
            )
        )

        self.assertEqual(class_response.status_code, 200)
        self.assertContains(class_response, "View performance")
        self.assertEqual(daily_response.status_code, 200)
        self.assertContains(daily_response, "Present")
        self.assertEqual(monthly_response.status_code, 200)
        self.assertContains(monthly_response, "School Form 2")
        self.assertEqual(performance_response.status_code, 200)
        self.assertContains(performance_response, "Student Performance Report")

    def test_principal_cannot_monitor_another_schools_class(self):
        other_teacher_user = User.objects.create_user(
            email="other-teacher@example.com",
            password="TestPass123!",
            role=User.Role.TEACHER,
        )
        other_teacher = Teacher.objects.create(
            user=other_teacher_user,
            school=self.school_b,
            employee_id="T-OTHER",
            firstname="Other",
            lastname="Teacher",
        )
        other_classroom = Classroom.objects.create(
            teacher=other_teacher,
            class_name="Other Class",
            grade_level="Grade 8",
            subject="Mathematics",
            section="B",
            school_year="2026-2027",
        )
        self.client.force_login(self.principal_user)

        response = self.client.get(
            reverse(
                "supervisor:principal_class_attendance",
                args=[other_classroom.pk],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_principal_attendance_monitor_is_read_only(self):
        self.client.force_login(self.principal_user)
        response = self.client.post(
            reverse(
                "supervisor:principal_class_attendance",
                args=[self.classroom.pk],
            ),
            {"date": "2026-10-29"},
        )

        self.assertEqual(response.status_code, 405)
