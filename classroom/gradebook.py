from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from django.db.models import Count

from .models import (
    AcademicTerm,
    AttendanceDay,
    AttendanceRecord,
    GradeItem,
    GradeScore,
    GradebookSettings,
)


ZERO = Decimal("0")
HUNDRED = Decimal("100")


def next_item_position(classroom, term, component):
    used = set(GradeItem.objects.filter(
        classroom=classroom,
        term=term,
        component=component,
    ).values_list("position", flat=True))
    position = 1
    while position in used:
        position += 1
    return position


def sync_module_grade_item(module):
    """Keep one Written Work gradebook column for one complete Module."""
    defaults = {
        "classroom": module.classroom,
        "term": module.term,
        "component": GradeItem.Component.WRITTEN_WORK,
        "title": module.title,
        "highest_possible_score": module.total_points,
    }

    try:
        item = module.grade_item
    except GradeItem.DoesNotExist:
        defaults["position"] = next_item_position(
            module.classroom,
            module.term,
            GradeItem.Component.WRITTEN_WORK,
        )
        item = GradeItem.objects.create(module=module, **defaults)
    else:
        changed_group = (
            item.classroom_id != module.classroom_id
            or item.term != module.term
            or item.component != GradeItem.Component.WRITTEN_WORK
        )
        if changed_group:
            item.position = next_item_position(
                module.classroom,
                module.term,
                GradeItem.Component.WRITTEN_WORK,
            )
        for field, value in defaults.items():
            setattr(item, field, value)
        item.save()
    return item


def sync_module_grade_score(submission):
    if submission.score is None:
        return None
    item = sync_module_grade_item(submission.module)
    score = min(Decimal(submission.score), item.highest_possible_score)
    return GradeScore.objects.update_or_create(
        item=item,
        student=submission.student,
        defaults={"score": max(ZERO, score)},
    )[0]


def sync_activity_grade_item(activity):
    """Keep one gradebook column for one published graded Activity."""
    if activity.post_type != activity.PostType.ACTIVITY or activity.score is None:
        return None

    component = activity.grade_component
    defaults = {
        "classroom": activity.classroom,
        "term": activity.term,
        "component": component,
        "title": activity.title,
        "highest_possible_score": activity.score,
    }

    try:
        item = activity.grade_item
    except GradeItem.DoesNotExist:
        defaults["position"] = next_item_position(
            activity.classroom,
            activity.term,
            component,
        )
        item = GradeItem.objects.create(activity=activity, **defaults)
    else:
        changed_group = (
            item.classroom_id != activity.classroom_id
            or item.term != activity.term
            or item.component != component
        )
        if changed_group:
            item.position = next_item_position(
                activity.classroom,
                activity.term,
                component,
            )
        for field, value in defaults.items():
            setattr(item, field, value)
        item.save()
    return item


def sync_activity_grade_score(submission):
    if submission.score is None:
        return None
    item = sync_activity_grade_item(submission.activity)
    if item is None:
        return None
    score = min(Decimal(submission.score), item.highest_possible_score)
    return GradeScore.objects.update_or_create(
        item=item,
        student=submission.student,
        defaults={"score": max(ZERO, score)},
    )[0]


def percentage(score, possible):
    if not possible:
        return ZERO
    return (score / possible * HUNDRED).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def transmute(initial_grade):
    """DepEd transmutation table expressed as its equivalent formula."""
    value = max(ZERO, min(HUNDRED, Decimal(initial_grade)))
    if value >= Decimal("60"):
        grade = ((value - Decimal("60")) / Decimal("1.6") + Decimal("75"))
    else:
        grade = value / Decimal("4") + Decimal("60")
    return grade.quantize(Decimal("1"), rounding=ROUND_DOWN)


def make_slots(items, minimum):
    item_list = list(items)
    by_position = {item.position: item for item in item_list}
    size = max(minimum, max(by_position, default=0))
    return [
        {"number": index + 1, "item": by_position.get(index + 1)}
        for index in range(size)
    ]


def build_term_record(classroom, term, students):
    settings, _ = GradebookSettings.objects.get_or_create(
        classroom=classroom,
    )

    items = list(
        GradeItem.objects.filter(
            classroom=classroom,
            term=term,
        )
        .prefetch_related("scores")
        .order_by("component", "position")
    )

    grouped = {
        GradeItem.Component.WRITTEN_WORK: [],
        GradeItem.Component.PERFORMANCE_TASK: [],
        GradeItem.Component.ASSESSMENT: [],
    }

    for item in items:
        grouped[item.component].append(item)

    score_lookup = {
        (score.item_id, score.student_id): score.score
        for score in GradeScore.objects.filter(item__in=items)
    }

    weights = {
        GradeItem.Component.WRITTEN_WORK: Decimal(
            settings.written_work_weight
        ),
        GradeItem.Component.PERFORMANCE_TASK: Decimal(
            settings.performance_task_weight
        ),
        GradeItem.Component.ASSESSMENT: Decimal(
            settings.assessment_weight
        ),
    }

    slots = {
        GradeItem.Component.WRITTEN_WORK: make_slots(
            grouped[GradeItem.Component.WRITTEN_WORK],
            10,
        ),
        GradeItem.Component.PERFORMANCE_TASK: make_slots(
            grouped[GradeItem.Component.PERFORMANCE_TASK],
            10,
        ),
        GradeItem.Component.ASSESSMENT: make_slots(
            grouped[GradeItem.Component.ASSESSMENT],
            1,
        ),
    }

    highest_rows = {
        component: sum(
            (
                item.highest_possible_score
                for item in component_items
            ),
            ZERO,
        )
        for component, component_items in grouped.items()
    }

    rows = []

    for student in students:
        components = {}
        initial = ZERO
        has_items = bool(items)

        for component, component_items in grouped.items():
            values = [
                score_lookup.get((item.pk, student.pk))
                for item in component_items
            ]

            total = sum(
                (
                    value
                    for value in values
                    if value is not None
                ),
                ZERO,
            )

            possible = highest_rows[component]
            ps = percentage(total, possible)
            weighted = (
                ps * weights[component] / HUNDRED
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            initial += weighted

            components[component] = {
                "values": values,
                "total": total,
                "ps": ps,
                "weighted": weighted,
            }

        initial = initial.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        rows.append({
            "student": student,
            "components": components,
            "written": components[
                GradeItem.Component.WRITTEN_WORK
            ],
            "performance": components[
                GradeItem.Component.PERFORMANCE_TASK
            ],
            "assessment": components[
                GradeItem.Component.ASSESSMENT
            ],
            "written_cells": [
                {
                    "slot": slot,
                    "score": score_lookup.get(
                        (slot["item"].pk, student.pk)
                    ) if slot["item"] else None,
                }
                for slot in slots[
                    GradeItem.Component.WRITTEN_WORK
                ]
            ],
            "performance_cells": [
                {
                    "slot": slot,
                    "score": score_lookup.get(
                        (slot["item"].pk, student.pk)
                    ) if slot["item"] else None,
                }
                for slot in slots[
                    GradeItem.Component.PERFORMANCE_TASK
                ]
            ],
            "assessment_cells": [
                {
                    "slot": slot,
                    "score": score_lookup.get(
                        (slot["item"].pk, student.pk)
                    ) if slot["item"] else None,
                }
                for slot in slots[
                    GradeItem.Component.ASSESSMENT
                ]
            ],
            "initial": initial if has_items else None,
            "quarterly": (
                transmute(initial)
                if has_items
                else None
            ),
        })

    return {
        "settings": settings,
        "items": items,
        "grouped": grouped,
        "slots": slots,
        "written_slots": slots[
            GradeItem.Component.WRITTEN_WORK
        ],
        "performance_slots": slots[
            GradeItem.Component.PERFORMANCE_TASK
        ],
        "assessment_slots": slots[
            GradeItem.Component.ASSESSMENT
        ],
        "highest": highest_rows,
        "rows": rows,
    }


def get_term_configuration(classroom, term):
    return AcademicTerm.objects.filter(
        school_year=classroom.school_year,
        term=term,
    ).first()


def build_term_attendance(classroom, students, term):
    term_configuration = get_term_configuration(
        classroom,
        term,
    )

    if term_configuration is None:
        return {
            "term_configured": False,
            "start_date": None,
            "end_date": None,
            "class_days": 0,
            "recorded_entries": 0,
            "expected_entries": 0,
            "missing_entries": 0,
            "learners": {},
        }

    attendance_days = AttendanceDay.objects.filter(
        classroom=classroom,
        day_type=AttendanceDay.DayType.CLASS_DAY,
        date__range=(
            term_configuration.start_date,
            term_configuration.end_date,
        ),
    )

    class_day_count = attendance_days.count()

    grouped_records = (
        AttendanceRecord.objects
        .filter(
            attendance_day__in=attendance_days,
            student__in=students,
        )
        .values("student_id", "status")
        .annotate(total=Count("attendance_id"))
    )

    attendance_lookup = {}

    for record in grouped_records:
        attendance_lookup.setdefault(
            record["student_id"],
            {},
        )[record["status"]] = record["total"]

    learner_attendance = {}
    recorded_entries = 0

    for student in students:
        counts = attendance_lookup.get(student.pk, {})

        present = counts.get(
            AttendanceRecord.Status.PRESENT,
            0,
        )
        absent = counts.get(
            AttendanceRecord.Status.ABSENT,
            0,
        )
        late = counts.get(
            AttendanceRecord.Status.LATE,
            0,
        )
        excused = counts.get(
            AttendanceRecord.Status.EXCUSED,
            0,
        )

        recorded = present + absent + late + excused
        missing = max(class_day_count - recorded, 0)

        recorded_entries += recorded

        attendance_rate = None

        if class_day_count:
            attendance_rate = round(
                ((present + late) / class_day_count) * 100,
                2,
            )

        learner_attendance[student.pk] = {
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "recorded": recorded,
            "missing": missing,
            "attendance_rate": attendance_rate,
        }

    expected_entries = (
        class_day_count * len(students)
    )

    return {
        "term_configured": True,
        "start_date": term_configuration.start_date,
        "end_date": term_configuration.end_date,
        "class_days": class_day_count,
        "recorded_entries": recorded_entries,
        "expected_entries": expected_entries,
        "missing_entries": max(
            expected_entries - recorded_entries,
            0,
        ),
        "learners": learner_attendance,
    }


def validate_term_report(classroom, students, term):
    errors = []

    if not students:
        return ["This class has no enrolled learners."]

    settings, _ = GradebookSettings.objects.get_or_create(
        classroom=classroom,
    )

    if not getattr(settings, f"term_{term}_released"):
        errors.append(
            f"Release Term {term} grades before submitting "
            "the report."
        )

    grade_items = list(
        GradeItem.objects.filter(
            classroom=classroom,
            term=term,
        )
    )

    if not grade_items:
        errors.append(
            f"Term {term} does not have any grade items."
        )
    else:
        expected_scores = (
            len(students) * len(grade_items)
        )

        recorded_scores = GradeScore.objects.filter(
            item__in=grade_items,
            student__in=students,
        ).count()

        missing_scores = (
            expected_scores - recorded_scores
        )

        if missing_scores:
            errors.append(
                f"{missing_scores} Term {term} score entries "
                "are still missing."
            )

    attendance = build_term_attendance(
        classroom,
        students,
        term,
    )

    if not attendance["term_configured"]:
        errors.append(
            f"Term {term} dates have not been configured "
            "by the District Supervisor."
        )
    elif attendance["class_days"] == 0:
        errors.append(
            f"No class attendance days were recorded for "
            f"Term {term}."
        )
    elif attendance["missing_entries"]:
        errors.append(
            f"{attendance['missing_entries']} attendance "
            "entries are still missing."
        )

    return errors


def build_term_report_snapshot(
    classroom,
    students,
    term,
):
    term_record = build_term_record(
        classroom,
        term,
        students,
    )

    attendance = build_term_attendance(
        classroom,
        students,
        term,
    )

    attendance_by_student = attendance["learners"]

    learners = []

    for row in term_record["rows"]:
        student = row["student"]
        term_grade = row["quarterly"]
        student_attendance = attendance_by_student.get(
            student.pk,
            {
                "present": 0,
                "absent": 0,
                "late": 0,
                "excused": 0,
                "recorded": 0,
                "missing": 0,
                "attendance_rate": None,
            },
        )

        learners.append({
            "student_id": student.pk,
            "lrn": student.lrn,
            "name": (
                f"{student.lastname}, "
                f"{student.firstname}"
            ),
            "gender": student.gender,
            "term_grade": (
                int(term_grade)
                if term_grade is not None
                else None
            ),
            "remark": (
                "Passed"
                if term_grade is not None
                and term_grade >= 75
                else (
                    "Failed"
                    if term_grade is not None
                    else ""
                )
            ),
            "attendance": student_attendance,
        })

    return {
        "classroom_id": classroom.pk,
        "class_name": classroom.class_name,
        "subject": classroom.subject,
        "grade_level": classroom.grade_level,
        "section": classroom.section,
        "school_year": classroom.school_year,
        "term": term,
        "teacher": (
            f"{classroom.teacher.firstname} "
            f"{classroom.teacher.lastname}"
        ),
        "school": classroom.teacher.school.school_name,
        "attendance_summary": {
            "class_days": attendance["class_days"],
            "recorded_entries": attendance["recorded_entries"],
            "expected_entries": attendance["expected_entries"],
            "missing_entries": attendance["missing_entries"],
            "start_date": (
                attendance["start_date"].isoformat()
                if attendance["start_date"]
                else None
            ),
            "end_date": (
                attendance["end_date"].isoformat()
                if attendance["end_date"]
                else None
            ),
        },
        "learners": learners,
    }


def build_summary(classroom, students):
    records = {
        term: build_term_record(classroom, term, students)
        for term in ("1", "2", "3")
    }
    grade_maps = {
        term: {row["student"].pk: row["quarterly"] for row in record["rows"]}
        for term, record in records.items()
    }
    rows = []
    for student in students:
        term_grades = [grade_maps[term].get(student.pk) for term in ("1", "2", "3")]
        available = [grade for grade in term_grades if grade is not None]
        final = None
        if len(available) == 3:
            final = (sum(available, ZERO) / len(available)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        rows.append({
            "student": student,
            "term_grades": term_grades,
            "term_1": term_grades[0],
            "term_2": term_grades[1],
            "term_3": term_grades[2],
            "final": final,
            "remark": "Passed" if final is not None and final >= 75 else (
                "Failed" if final is not None else ""
            ),
        })
    return rows

def validate_final_grade_report(classroom, students):
    """
    Return validation messages that prevent an incomplete
    final report from being submitted.
    """

    errors = []

    if not students:
        errors.append(
            "This class has no enrolled learners."
        )
        return errors

    settings, _ = GradebookSettings.objects.get_or_create(
        classroom=classroom,
    )

    unreleased_terms = [
        term
        for term in ("1", "2", "3")
        if not getattr(settings, f"term_{term}_released")
    ]

    if unreleased_terms:
        term_names = ", ".join(
            f"Term {term}" for term in unreleased_terms
        )
        errors.append(
            f"Release {term_names} before submitting the final report."
        )

    total_missing_scores = 0

    for term in ("1", "2", "3"):
        items = list(
            GradeItem.objects.filter(
                classroom=classroom,
                term=term,
            )
        )

        if not items:
            errors.append(
                f"Term {term} does not have any grade items."
            )
            continue

        expected_scores = len(students) * len(items)

        recorded_scores = GradeScore.objects.filter(
            item__in=items,
            student__in=students,
        ).count()

        total_missing_scores += (
            expected_scores - recorded_scores
        )

    if total_missing_scores:
        errors.append(
            f"{total_missing_scores} learner score entries are still missing."
        )

    summary = build_summary(
        classroom,
        students,
    )

    missing_final_grades = sum(
        1
        for row in summary
        if row["final"] is None
    )

    if missing_final_grades:
        errors.append(
            f"{missing_final_grades} learners do not have a final grade."
        )

    return errors


def build_final_grade_report_snapshot(classroom, students):
    """
    Create an immutable end-of-school-year report containing
    all three term grades, final grades, and annual attendance.
    """

    grade_rows = build_summary(
        classroom,
        students,
    )

    # Collect attendance separately for all three terms.
    attendance_by_term = {
        term: build_term_attendance(
            classroom,
            students,
            term,
        )
        for term in ("1", "2", "3")
    }

    annual_attendance = {}

    for student in students:
        totals = {
            "present": 0,
            "absent": 0,
            "late": 0,
            "excused": 0,
            "recorded": 0,
            "missing": 0,
            "class_days": 0,
            "attendance_rate": None,
        }

        for term in ("1", "2", "3"):
            term_attendance = attendance_by_term[term]

            if term_attendance["term_configured"]:
                totals["class_days"] += (
                    term_attendance["class_days"]
                )

            learner_attendance = (
                term_attendance["learners"].get(
                    student.pk,
                    {},
                )
            )

            totals["present"] += learner_attendance.get(
                "present",
                0,
            )
            totals["absent"] += learner_attendance.get(
                "absent",
                0,
            )
            totals["late"] += learner_attendance.get(
                "late",
                0,
            )
            totals["excused"] += learner_attendance.get(
                "excused",
                0,
            )
            totals["recorded"] += learner_attendance.get(
                "recorded",
                0,
            )
            totals["missing"] += learner_attendance.get(
                "missing",
                0,
            )

        if totals["class_days"] > 0:
            totals["attendance_rate"] = round(
                (
                    (
                        totals["present"]
                        + totals["late"]
                    )
                    / totals["class_days"]
                )
                * 100,
                2,
            )

        annual_attendance[student.pk] = totals

    learners = []

    for row in grade_rows:
        student = row["student"]

        learners.append({
            "student_id": student.pk,
            "lrn": student.lrn,
            "name": (
                f"{student.lastname}, "
                f"{student.firstname}"
            ),
            "gender": student.gender,

            "term_1": (
                int(row["term_1"])
                if row["term_1"] is not None
                else None
            ),
            "term_2": (
                int(row["term_2"])
                if row["term_2"] is not None
                else None
            ),
            "term_3": (
                int(row["term_3"])
                if row["term_3"] is not None
                else None
            ),
            "final_grade": (
                int(row["final"])
                if row["final"] is not None
                else None
            ),

            "remark": row["remark"],
            "attendance": annual_attendance.get(
                student.pk,
                {
                    "present": 0,
                    "absent": 0,
                    "late": 0,
                    "excused": 0,
                    "recorded": 0,
                    "missing": 0,
                    "class_days": 0,
                    "attendance_rate": None,
                },
            ),
        })

    return {
        "classroom_id": classroom.pk,
        "class_name": classroom.class_name,
        "subject": classroom.subject,
        "grade_level": classroom.grade_level,
        "section": classroom.section,
        "school_year": classroom.school_year,
        "report_period": "End-of-School-Year",
        "teacher": (
            f"{classroom.teacher.firstname} "
            f"{classroom.teacher.lastname}"
        ),
        "school": classroom.teacher.school.school_name,

        "attendance_summary": {
            "term_1_class_days": (
                attendance_by_term["1"]["class_days"]
            ),
            "term_2_class_days": (
                attendance_by_term["2"]["class_days"]
            ),
            "term_3_class_days": (
                attendance_by_term["3"]["class_days"]
            ),
            "total_class_days": sum(
                attendance_by_term[term]["class_days"]
                for term in ("1", "2", "3")
            ),
            "missing_entries": sum(
                attendance_by_term[term]["missing_entries"]
                for term in ("1", "2", "3")
            ),
        },

        "learners": learners,
    }

def build_released_student_summary(student, classrooms):
    """
    Build the Parent's three-term grade summary.

    A grade is included only after the Teacher releases
    that term through GradebookSettings.
    """

    rows = []

    for classroom in classrooms:
        settings, _ = GradebookSettings.objects.get_or_create(
            classroom=classroom,
        )

        term_grades = []

        for term in ("1", "2", "3"):
            released = getattr(
                settings,
                f"term_{term}_released",
            )

            grade = None

            if released:
                record = build_term_record(
                    classroom,
                    term,
                    [student],
                )

                if record["rows"]:
                    grade = record["rows"][0]["quarterly"]

            term_grades.append({
                "released": released,
                "grade": grade,
            })

        final_grade = None

        if all(
            term["released"] and term["grade"] is not None
            for term in term_grades
        ):
            final_grade = (
                sum(
                    term["grade"]
                    for term in term_grades
                )
                / Decimal("3")
            ).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )

        rows.append({
            "classroom": classroom,
            "term_1": term_grades[0],
            "term_2": term_grades[1],
            "term_3": term_grades[2],
            "final_grade": final_grade,
            "remark": (
                "Passed"
                if final_grade is not None
                and final_grade >= 75
                else "Failed"
                if final_grade is not None
                else ""
            ),
        })

    return rows
