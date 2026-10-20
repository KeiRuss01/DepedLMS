def build_consolidated_learners(reports):
    """
    Consolidate approved Teacher term reports by learner
    and subject.
    """

    learners = {}

    for report in reports:
        snapshot = report.snapshot or {}

        term = str(
            snapshot.get("term", report.term)
        )

        grade_level = snapshot.get(
            "grade_level",
            report.classroom.grade_level,
        )

        section = snapshot.get(
            "section",
            report.classroom.section,
        )

        grade_section = (
            f"{grade_level} - {section}"
        )

        for learner in snapshot.get("learners", []):
            student_id = learner.get("student_id")

            if not student_id:
                continue

            learner_record = learners.setdefault(
                student_id,
                {
                    "student_id": student_id,
                    "lrn": learner.get("lrn", ""),
                    "name": learner.get(
                        "name",
                        "Unknown learner",
                    ),
                    "grade_sections": set(),
                    "subject_map": {},
                    "subjects": [],
                    "average": None,
                },
            )

            learner_record["grade_sections"].add(
                grade_section
            )

            subject_key = (
                report.classroom_id,
                snapshot.get(
                    "subject",
                    report.classroom.subject,
                ),
            )

            subject_record = (
                learner_record["subject_map"]
                .setdefault(
                    subject_key,
                    {
                        "subject": snapshot.get(
                            "subject",
                            report.classroom.subject,
                        ),
                        "class_name": snapshot.get(
                            "class_name",
                            report.classroom.class_name,
                        ),
                        "teacher": snapshot.get(
                            "teacher",
                            str(report.classroom.teacher),
                        ),
                        "term_1": None,
                        "term_2": None,
                        "term_3": None,
                        "final_grade": None,
                        "remark": "",
                        "present": 0,
                        "absent": 0,
                        "late": 0,
                        "excused": 0,
                        "report_id": report.pk,
                    },
                )
            )

            subject_record[f"term_{term}"] = (
                learner.get("term_grade")
            )

            attendance = learner.get(
                "attendance",
                {},
            )

            subject_record["present"] += (
                attendance.get("present", 0)
            )
            subject_record["absent"] += (
                attendance.get("absent", 0)
            )
            subject_record["late"] += (
                attendance.get("late", 0)
            )
            subject_record["excused"] += (
                attendance.get("excused", 0)
            )

            subject_record["report_id"] = report.pk

    consolidated = []

    for learner in learners.values():
        learner["grade_sections"] = sorted(
            learner["grade_sections"]
        )

        subjects = list(
            learner.pop("subject_map").values()
        )

        for subject in subjects:
            term_grades = [
                subject["term_1"],
                subject["term_2"],
                subject["term_3"],
            ]

            if all(
                grade is not None
                for grade in term_grades
            ):
                subject["final_grade"] = round(
                    sum(term_grades) / 3
                )

                subject["remark"] = (
                    "Passed"
                    if subject["final_grade"] >= 75
                    else "Failed"
                )

        final_grades = [
            subject["final_grade"]
            for subject in subjects
            if subject["final_grade"] is not None
        ]

        if final_grades:
            learner["average"] = round(
                sum(final_grades)
                / len(final_grades)
            )

        subjects.sort(
            key=lambda subject: subject["subject"]
        )

        learner["subjects"] = subjects
        consolidated.append(learner)

    consolidated.sort(
        key=lambda learner: learner["name"]
    )

    return consolidated