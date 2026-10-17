def build_consolidated_learners(reports):
    """
    Combine approved Teacher reports by learner.

    The data comes from the report snapshot so the Principal
    sees the exact grades that were submitted and approved.
    """

    learners = {}

    for report in reports:
        snapshot = report.snapshot or {}

        grade_level = snapshot.get(
            "grade_level",
            report.classroom.grade_level,
        )

        section = snapshot.get(
            "section",
            report.classroom.section,
        )

        grade_section = f"{grade_level} - {section}"

        for learner in snapshot.get("learners", []):
            student_id = learner.get("student_id")

            if not student_id:
                continue

            learner_record = learners.setdefault(
                student_id,
                {
                    "student_id": student_id,
                    "lrn": learner.get("lrn", ""),
                    "name": learner.get("name", "Unknown learner"),
                    "grade_sections": set(),
                    "subjects": [],
                    "average": None,
                },
            )

            learner_record["grade_sections"].add(
                grade_section
            )

            learner_record["subjects"].append({
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
                "term_1": learner.get("term_1"),
                "term_2": learner.get("term_2"),
                "term_3": learner.get("term_3"),
                "final_grade": learner.get("final_grade"),
                "remark": learner.get("remark", ""),
                "report_id": report.pk,
            })

    consolidated = []

    for learner in learners.values():
        learner["grade_sections"] = sorted(
            learner["grade_sections"]
        )

        final_grades = [
            subject["final_grade"]
            for subject in learner["subjects"]
            if subject["final_grade"] is not None
        ]

        if final_grades:
            learner["average"] = round(
                sum(final_grades) / len(final_grades)
            )

        learner["subjects"].sort(
            key=lambda subject: subject["subject"]
        )

        consolidated.append(learner)

    consolidated.sort(
        key=lambda learner: learner["name"]
    )

    return consolidated