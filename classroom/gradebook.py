from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from .models import GradeItem, GradeScore, GradebookSettings


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
    settings, _ = GradebookSettings.objects.get_or_create(classroom=classroom)
    items = list(
        GradeItem.objects.filter(classroom=classroom, term=term)
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
        GradeItem.Component.WRITTEN_WORK: Decimal(settings.written_work_weight),
        GradeItem.Component.PERFORMANCE_TASK: Decimal(settings.performance_task_weight),
        GradeItem.Component.ASSESSMENT: Decimal(settings.assessment_weight),
    }
    slots = {
        GradeItem.Component.WRITTEN_WORK: make_slots(grouped[GradeItem.Component.WRITTEN_WORK], 10),
        GradeItem.Component.PERFORMANCE_TASK: make_slots(grouped[GradeItem.Component.PERFORMANCE_TASK], 10),
        GradeItem.Component.ASSESSMENT: make_slots(grouped[GradeItem.Component.ASSESSMENT], 1),
    }
    highest_rows = {
        key: sum((item.highest_possible_score for item in values), ZERO)
        for key, values in grouped.items()
    }

    rows = []
    for student in students:
        components = {}
        initial = ZERO
        has_items = bool(items)
        for component, component_items in grouped.items():
            values = [score_lookup.get((item.pk, student.pk)) for item in component_items]
            total = sum((value for value in values if value is not None), ZERO)
            possible = highest_rows[component]
            ps = percentage(total, possible)
            weighted = (ps * weights[component] / HUNDRED).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            initial += weighted
            components[component] = {
                "values": values,
                "total": total,
                "ps": ps,
                "weighted": weighted,
            }
        initial = initial.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rows.append({
            "student": student,
            "components": components,
            "written": components[GradeItem.Component.WRITTEN_WORK],
            "performance": components[GradeItem.Component.PERFORMANCE_TASK],
            "assessment": components[GradeItem.Component.ASSESSMENT],
            "written_cells": [
                {"slot": slot, "score": score_lookup.get((slot["item"].pk, student.pk)) if slot["item"] else None}
                for slot in slots[GradeItem.Component.WRITTEN_WORK]
            ],
            "performance_cells": [
                {"slot": slot, "score": score_lookup.get((slot["item"].pk, student.pk)) if slot["item"] else None}
                for slot in slots[GradeItem.Component.PERFORMANCE_TASK]
            ],
            "assessment_cells": [
                {"slot": slot, "score": score_lookup.get((slot["item"].pk, student.pk)) if slot["item"] else None}
                for slot in slots[GradeItem.Component.ASSESSMENT]
            ],
            "initial": initial if has_items else None,
            "quarterly": transmute(initial) if has_items else None,
        })

    return {
        "settings": settings,
        "items": items,
        "grouped": grouped,
        "slots": slots,
        "written_slots": slots[GradeItem.Component.WRITTEN_WORK],
        "performance_slots": slots[GradeItem.Component.PERFORMANCE_TASK],
        "assessment_slots": slots[GradeItem.Component.ASSESSMENT],
        "highest": highest_rows,
        "rows": rows,
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
