from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import Parent, ParentStudentLink, School, Student, User


class ParentStudentConnectionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(school_name="Test School")

        self.student_user = User.objects.create_user(
            email="student@example.com",
            password="TestPass123!",
            role=User.Role.STUDENT,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            school=self.school,
            lrn="123456789012",
            firstname="Sample",
            lastname="Student",
            gender=Student.Gender.MALE,
            birth_date=date(2010, 1, 1),
            # A Student can approve their Parent connection even while the
            # school-side profile review is still pending.
            acc_status=Student.AccStatus.PENDING,
        )

        self.parent_user = User.objects.create_user(
            email="parent@example.com",
            password="TestPass123!",
            role=User.Role.PARENT,
        )
        self.parent = Parent.objects.create(
            user=self.parent_user,
            firstname="Sample",
            lastname="Parent",
            relationship=Parent.Relationship.GUARDIAN,
        )

    def test_parent_request_is_approved_by_student(self):
        self.client.force_login(self.parent_user)
        response = self.client.post(
            reverse("classroom:parent_children"),
            {
                "lrn": self.student.lrn,
                "relationship": ParentStudentLink.Relationship.GUARDIAN,
            },
        )

        self.assertRedirects(response, reverse("classroom:parent_children"))
        link = ParentStudentLink.objects.get(
            parent=self.parent,
            student=self.student,
        )
        self.assertEqual(link.status, ParentStudentLink.Status.PENDING)

        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse(
                "classroom:respond_parent_link",
                args=[link.link_id, "accept"],
            )
        )

        self.assertRedirects(
            response,
            reverse("classroom:student_parent_requests"),
        )
        link.refresh_from_db()
        self.assertEqual(link.status, ParentStudentLink.Status.APPROVED)

        self.client.force_login(self.parent_user)
        self.assertEqual(
            self.client.get(reverse("classroom:dashboard")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("classroom:classes")).status_code,
            200,
        )
