from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import Principal, School, Student, Teacher, User
from classroom.models import Classroom


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
        Student.objects.create(
            user=student_user,
            school=self.school_a,
            lrn="123456789012",
            firstname="Sample",
            lastname="Student",
            gender=Student.Gender.MALE,
            birth_date=date(2010, 1, 1),
        )
        Classroom.objects.create(
            teacher=self.teacher,
            class_name="Science 8",
            grade_level="Grade 8",
            subject="Science",
            section="A",
            school_year="2026-2027",
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
