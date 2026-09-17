from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import Parent, ParentStudentLink, School, Student, Teacher, User
from classroom.models import (
    Classroom,
    ClassEnrollment,
    Module,
    ModuleAnswerSection,
    ModuleSubmission,
    GradeItem,
    GradeScore,
    AttendanceDay,
    AttendanceRecord,
    Announcement,
    SectionResponse,
    SectionQuestion,
)


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


class ModuleSubmissionFlowTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(school_name="Test School")
        self.teacher_user = User.objects.create_user(
            email="teacher@example.com", password="TestPass123!", role=User.Role.TEACHER
        )
        self.teacher = Teacher.objects.create(
            user=self.teacher_user, school=self.school, employee_id="T-1",
            firstname="Test", lastname="Teacher",
        )
        self.student_user = User.objects.create_user(
            email="learner@example.com", password="TestPass123!", role=User.Role.STUDENT
        )
        self.student = Student.objects.create(
            user=self.student_user, school=self.school, lrn="987654321012",
            firstname="Test", lastname="Learner", gender=Student.Gender.FEMALE,
            birth_date=date(2011, 1, 1), acc_status=Student.AccStatus.APPROVED,
        )
        self.classroom = Classroom.objects.create(
            teacher=self.teacher, class_name="Science 6", grade_level="6",
            subject="Science", section="A", school_year="2026-2027",
        )
        ClassEnrollment.objects.create(
            classroom=self.classroom, student=self.student,
            status=ClassEnrollment.Status.APPROVED,
        )
        self.module = Module.objects.create(
            classroom=self.classroom, title="Module 1", pdf="modules/test.pdf",
            status=Module.Status.PUBLISHED,
        )

    def test_teacher_can_add_sections_to_published_module_before_submission(self):
        self.client.force_login(self.teacher_user)
        response = self.client.get(
            reverse("classroom:module_section_create", args=[self.module.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_section_scores_sum_into_one_written_work_module_score(self):
        first = ModuleAnswerSection.objects.create(
            module=self.module,
            title="What I Know",
            max_score=10,
            answer_method=ModuleAnswerSection.AnswerMethod.STRUCTURED,
        )
        second = ModuleAnswerSection.objects.create(
            module=self.module,
            title="Reflection",
            max_score=20,
            answer_method=ModuleAnswerSection.AnswerMethod.WRITTEN,
            grading_component=ModuleAnswerSection.GradingComponent.PERFORMANCE_TASK,
            include_in_grade=False,
        )
        submission = ModuleSubmission.objects.create(
            module=self.module,
            student=self.student,
            status=ModuleSubmission.Status.SUBMITTED,
        )
        SectionResponse.objects.create(
            submission=submission, section=first, is_complete=True, score=8,
        )
        SectionResponse.objects.create(
            submission=submission, section=second, is_complete=True, score=17,
        )

        submission.update_total_score()
        submission.refresh_from_db()
        second.refresh_from_db()

        self.assertEqual(self.module.total_points, 30)
        self.assertEqual(submission.score, 25)
        self.assertTrue(second.include_in_grade)
        self.assertEqual(
            second.grading_component,
            ModuleAnswerSection.GradingComponent.WRITTEN_WORK,
        )

    def test_objective_section_is_scored_and_submitted_once(self):
        section = ModuleAnswerSection.objects.create(
            module=self.module, title="What I Know", max_score=2,
            answer_method=ModuleAnswerSection.AnswerMethod.STRUCTURED,
        )
        question = SectionQuestion.objects.create(
            section=section, prompt="The Earth is round.",
            question_type=SectionQuestion.QuestionType.TRUE_FALSE,
            correct_answer="True", points=2,
        )
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("classroom:module_section_work", args=[section.pk]),
            {"action": "complete", f"question_{question.pk}": "True"},
        )
        self.assertRedirects(response, reverse("classroom:module_work", args=[self.module.pk]))
        response = self.client.post(reverse("classroom:module_work", args=[self.module.pk]))
        self.assertRedirects(response, reverse("classroom:module_work", args=[self.module.pk]))
        submission = ModuleSubmission.objects.get(module=self.module, student=self.student)
        self.assertEqual(submission.status, ModuleSubmission.Status.GRADED)
        self.assertEqual(submission.score, 2)

        self.client.force_login(self.teacher_user)
        editable_response = self.client.get(
            reverse("classroom:module_section_create", args=[self.module.pk])
        )
        self.assertEqual(editable_response.status_code, 200)

    def test_teacher_manually_grades_essay_against_section_total(self):
        section = ModuleAnswerSection.objects.create(
            module=self.module, title="Reflection", max_score=20,
            answer_method=ModuleAnswerSection.AnswerMethod.WRITTEN,
        )
        self.client.force_login(self.student_user)
        self.client.post(
            reverse("classroom:module_section_work", args=[section.pk]),
            {"action": "complete", "written_answer": "My reflection."},
        )
        self.client.post(reverse("classroom:module_work", args=[self.module.pk]))
        submission = ModuleSubmission.objects.get(module=self.module, student=self.student)
        response = submission.section_responses.get(section=section)
        self.assertEqual(submission.status, ModuleSubmission.Status.SUBMITTED)

        self.client.force_login(self.teacher_user)
        grade_response = self.client.post(
            reverse("classroom:module_review", args=[submission.pk]),
            {
                "response_id": str(response.pk),
                f"grade-{response.pk}-score": "17",
                f"grade-{response.pk}-feedback": "Good explanation.",
            },
        )
        self.assertRedirects(
            grade_response, reverse("classroom:module_review", args=[submission.pk])
        )
        submission.refresh_from_db()
        self.assertEqual(submission.status, ModuleSubmission.Status.GRADED)
        self.assertEqual(submission.score, 17)

    def test_teacher_announcement_and_published_module_appear_in_stream(self):
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("classroom:announcement_create", args=[self.classroom.pk]),
            {
                "title": "Class reminder",
                "content": "Please finish the published Module.",
                "priority": Announcement.Priority.IMPORTANT,
            },
        )
        self.assertEqual(response.status_code, 302)
        announcement = Announcement.objects.get(classroom=self.classroom)
        self.assertEqual(announcement.posted_by, self.teacher_user)

        self.client.force_login(self.student_user)
        stream = self.client.get(
            reverse("classroom:class_page", args=[self.classroom.pk]) + "?tab=stream"
        )
        self.assertEqual(stream.status_code, 200)
        self.assertContains(stream, "Class reminder")
        self.assertContains(stream, self.module.title)

    def test_student_cannot_create_announcement(self):
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("classroom:announcement_create", args=[self.classroom.pk]),
            {"title": "Not allowed", "content": "No", "priority": "normal"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Announcement.objects.filter(title="Not allowed").exists())

    def test_student_dashboard_uses_enrolled_class_content(self):
        Announcement.objects.create(
            classroom=self.classroom,
            posted_by=self.teacher_user,
            title="Dashboard reminder",
            content="Read your Module before answering.",
        )
        self.client.force_login(self.student_user)

        response = self.client.get(reverse("classroom:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["continue_module"], self.module)
        self.assertContains(response, "Dashboard reminder")
        self.assertContains(response, self.module.title)

    def test_teacher_dashboard_shows_submissions_needing_review(self):
        submission = ModuleSubmission.objects.create(
            module=self.module,
            student=self.student,
            status=ModuleSubmission.Status.SUBMITTED,
        )
        self.client.force_login(self.teacher_user)

        response = self.client.get(reverse("classroom:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(submission, response.context["submissions_to_review"])
        self.assertContains(response, "Submitted Module 1")


class GradebookTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            school_name="Test School", region="CAR", division="Test Division"
        )
        self.teacher_user = User.objects.create_user(
            email="grade.teacher@example.com", password="TestPass123!",
            role=User.Role.TEACHER,
        )
        self.teacher = Teacher.objects.create(
            user=self.teacher_user, school=self.school, employee_id="T-2",
            firstname="Grade", lastname="Teacher",
        )
        self.student_user = User.objects.create_user(
            email="grade.student@example.com", password="TestPass123!",
            role=User.Role.STUDENT,
        )
        self.student = Student.objects.create(
            user=self.student_user, school=self.school, lrn="111122223333",
            firstname="Grade", lastname="Learner", gender=Student.Gender.MALE,
            birth_date=date(2011, 1, 1), acc_status=Student.AccStatus.APPROVED,
        )
        self.classroom = Classroom.objects.create(
            teacher=self.teacher, class_name="AP 10", grade_level="10",
            subject="Araling Panlipunan", section="A", school_year="2026-2027",
        )
        ClassEnrollment.objects.create(
            classroom=self.classroom, student=self.student,
            status=ClassEnrollment.Status.APPROVED,
        )

    def test_gradebook_backfills_one_written_work_column_for_module(self):
        module = Module.objects.create(
            classroom=self.classroom, title="Module 1", pdf="modules/test.pdf",
            term=Module.Term.FIRST, status=Module.Status.PUBLISHED,
        )
        ModuleAnswerSection.objects.create(
            module=module, title="Assessment", max_score=20,
            answer_method=ModuleAnswerSection.AnswerMethod.STRUCTURED,
        )
        self.client.force_login(self.teacher_user)
        response = self.client.get(
            reverse("classroom:gradebook", args=[self.classroom.pk])
        )
        self.assertEqual(response.status_code, 200)
        item = GradeItem.objects.get(module=module)
        self.assertEqual(item.component, GradeItem.Component.WRITTEN_WORK)
        self.assertEqual(item.position, 1)
        self.assertEqual(item.highest_possible_score, 20)

    def test_manual_activity_uses_first_empty_slot_and_accepts_score(self):
        GradeItem.objects.create(
            classroom=self.classroom, term="1",
            component=GradeItem.Component.WRITTEN_WORK, title="Activity 1",
            highest_possible_score=10, position=2,
        )
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("classroom:gradebook", args=[self.classroom.pk]) + "?term=1",
            {
                "action": "add_item", "title": "Face-to-face quiz",
                "component": GradeItem.Component.WRITTEN_WORK,
                "highest_possible_score": "20",
            },
        )
        self.assertEqual(response.status_code, 302)
        item = GradeItem.objects.get(title="Face-to-face quiz")
        self.assertEqual(item.position, 1)

        response = self.client.post(
            reverse("classroom:gradebook", args=[self.classroom.pk]) + "?term=1",
            {"action": "save_scores", f"score_{item.pk}_{self.student.pk}": "18"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            GradeScore.objects.get(item=item, student=self.student).score,
            18,
        )

    def test_teacher_can_type_directly_into_an_empty_gradebook_slot(self):
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse("classroom:gradebook", args=[self.classroom.pk]) + "?term=1",
            {
                "action": "save_scores",
                "new_hps_written_work_1": "20",
                f"new_score_written_work_1_{self.student.pk}": "17",
            },
        )
        self.assertEqual(response.status_code, 302)
        item = GradeItem.objects.get(
            classroom=self.classroom,
            term="1",
            component=GradeItem.Component.WRITTEN_WORK,
            position=1,
        )
        self.assertEqual(item.title, "Written Work 1")
        self.assertEqual(item.highest_possible_score, 20)
        self.assertEqual(
            GradeScore.objects.get(item=item, student=self.student).score,
            17,
        )

    def test_student_sees_only_own_scores_and_grade_after_release(self):
        item = GradeItem.objects.create(
            classroom=self.classroom, term="1",
            component=GradeItem.Component.WRITTEN_WORK,
            title="Face-to-face activity", highest_possible_score=20, position=1,
        )
        GradeScore.objects.create(item=item, student=self.student, score=18)

        self.client.force_login(self.student_user)
        response = self.client.get(
            reverse("classroom:gradebook", args=[self.classroom.pk]) + "?term=1"
        )
        self.assertContains(response, "My scores")
        self.assertContains(response, "Not released")
        self.assertNotContains(response, "Learners' Names")

        self.client.force_login(self.teacher_user)
        self.client.post(
            reverse("classroom:gradebook", args=[self.classroom.pk]) + "?term=1",
            {"action": "toggle_release"},
        )
        self.client.force_login(self.student_user)
        response = self.client.get(
            reverse("classroom:gradebook", args=[self.classroom.pk]) + "?term=1"
        )
        self.assertContains(response, "Released by your Teacher")
        self.assertNotContains(response, "Not released")


class AttendanceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(school_name="Attendance School")
        self.teacher_user = User.objects.create_user(
            email="attendance.teacher@example.com", password="TestPass123!",
            role=User.Role.TEACHER,
        )
        self.teacher = Teacher.objects.create(
            user=self.teacher_user, school=self.school, employee_id="AT-1",
            firstname="Attendance", lastname="Teacher",
        )
        self.student_user = User.objects.create_user(
            email="attendance.student@example.com", password="TestPass123!",
            role=User.Role.STUDENT,
        )
        self.student = Student.objects.create(
            user=self.student_user, school=self.school, lrn="444455556666",
            firstname="Daily", lastname="Learner", gender=Student.Gender.FEMALE,
            birth_date=date(2011, 1, 1), acc_status=Student.AccStatus.APPROVED,
        )
        self.classroom = Classroom.objects.create(
            teacher=self.teacher, class_name="English 8", grade_level="8",
            subject="English", section="A", school_year="2026-2027",
        )
        ClassEnrollment.objects.create(
            classroom=self.classroom, student=self.student,
            status=ClassEnrollment.Status.APPROVED,
        )

    def test_teacher_records_daily_attendance(self):
        self.client.force_login(self.teacher_user)
        self.assertEqual(
            self.client.get(
                reverse("classroom:attendance", args=[self.classroom.pk])
            ).status_code,
            200,
        )
        response = self.client.post(
            reverse("classroom:attendance", args=[self.classroom.pk]),
            {
                "action": "save_attendance",
                "date": "2026-09-17",
                "day_type": AttendanceDay.DayType.CLASS_DAY,
                f"status_{self.student.pk}": AttendanceRecord.Status.LATE,
                f"remarks_{self.student.pk}": "Arrived at 8:15 AM",
            },
        )
        self.assertEqual(response.status_code, 302)
        attendance_day = AttendanceDay.objects.get(
            classroom=self.classroom, date="2026-09-17"
        )
        record = AttendanceRecord.objects.get(
            attendance_day=attendance_day, student=self.student
        )
        self.assertEqual(record.status, AttendanceRecord.Status.LATE)
        self.assertEqual(record.remarks, "Arrived at 8:15 AM")
        monthly_response = self.client.get(
            reverse("classroom:attendance", args=[self.classroom.pk])
            + "?view=monthly&month=2026-09"
        )
        self.assertEqual(monthly_response.status_code, 200)
        self.assertContains(monthly_response, "School Form 2")

    def test_holiday_removes_learner_entries_for_that_date(self):
        attendance_day = AttendanceDay.objects.create(
            classroom=self.classroom, date="2026-09-18",
            day_type=AttendanceDay.DayType.CLASS_DAY, recorded_by=self.teacher,
        )
        AttendanceRecord.objects.create(
            attendance_day=attendance_day, student=self.student,
            status=AttendanceRecord.Status.PRESENT,
        )
        self.client.force_login(self.teacher_user)
        self.client.post(
            reverse("classroom:attendance", args=[self.classroom.pk]),
            {
                "action": "save_attendance",
                "date": "2026-09-18",
                "day_type": AttendanceDay.DayType.HOLIDAY,
                "note": "Local holiday",
            },
        )
        attendance_day.refresh_from_db()
        self.assertEqual(attendance_day.day_type, AttendanceDay.DayType.HOLIDAY)
        self.assertEqual(attendance_day.note, "Local holiday")
        self.assertFalse(attendance_day.records.exists())

    def test_student_cannot_open_teacher_attendance_page(self):
        self.client.force_login(self.student_user)
        response = self.client.get(
            reverse("classroom:attendance", args=[self.classroom.pk])
        )
        self.assertEqual(response.status_code, 403)
