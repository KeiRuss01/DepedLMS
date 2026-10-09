import calendar
from datetime import date

from .models import AttendanceDay, AttendanceRecord


def parse_month(month_value):
    """Convert YYYY-MM into the first day of that month."""

    try:
        return date.fromisoformat(f"{month_value}-01")
    except (TypeError, ValueError):
        today = date.today()
        return date(today.year, today.month, 1)


def shift_month(selected_month, amount):
    """Move backward or forward by one month."""

    month_index = (
        selected_month.year * 12
        + selected_month.month
        - 1
        + amount
    )

    year, month = divmod(month_index, 12)

    return date(year, month + 1, 1)


def build_parent_attendance(
    student,
    classroom,
    selected_month,
):
    attendance_days = {
        attendance_day.date: attendance_day
        for attendance_day in AttendanceDay.objects.filter(
            classroom=classroom,
            date__year=selected_month.year,
            date__month=selected_month.month,
        )
    }

    records = {
        record.attendance_day.date: record
        for record in AttendanceRecord.objects.filter(
            student=student,
            attendance_day__classroom=classroom,
            attendance_day__date__year=selected_month.year,
            attendance_day__date__month=selected_month.month,
        ).select_related(
            "attendance_day",
        )
    }

    totals = {
        "present": 0,
        "absent": 0,
        "late": 0,
        "holiday": 0,
        "no_class": 0,
        "excused": 0,
    }

    details = []
    weeks = []

    month_calendar = calendar.Calendar(
        firstweekday=6,
    )

    for calendar_week in month_calendar.monthdatescalendar(
        selected_month.year,
        selected_month.month,
    ):
        week = []

        for calendar_date in calendar_week:
            in_month = (
                calendar_date.month
                == selected_month.month
            )

            cell = {
                "date": calendar_date,
                "in_month": in_month,
                "status": "",
                "label": "",
                "note": "",
            }

            if not in_month:
                week.append(cell)
                continue

            attendance_day = attendance_days.get(
                calendar_date
            )

            record = records.get(calendar_date)

            # Saturday and Sunday are default no-class days.
            if calendar_date.weekday() >= 5:
                cell["status"] = "weekend"
                cell["label"] = "No class"
                totals["no_class"] += 1

            elif (
                attendance_day
                and attendance_day.day_type
                == AttendanceDay.DayType.HOLIDAY
            ):
                cell["status"] = "holiday"
                cell["label"] = "Holiday"
                cell["note"] = attendance_day.note
                totals["holiday"] += 1

            elif (
                attendance_day
                and attendance_day.day_type
                == AttendanceDay.DayType.NO_CLASS
            ):
                cell["status"] = "no-class"
                cell["label"] = "No class"
                cell["note"] = attendance_day.note
                totals["no_class"] += 1

            elif record:
                status_labels = {
                    AttendanceRecord.Status.PRESENT: "Present",
                    AttendanceRecord.Status.ABSENT: "Absent",
                    AttendanceRecord.Status.LATE: "Tardy",
                    AttendanceRecord.Status.EXCUSED: "Excused",
                }

                cell["status"] = record.status
                cell["label"] = status_labels[record.status]
                cell["note"] = record.remarks

                if record.status == AttendanceRecord.Status.PRESENT:
                    totals["present"] += 1

                elif record.status == AttendanceRecord.Status.ABSENT:
                    totals["absent"] += 1

                elif record.status == AttendanceRecord.Status.LATE:
                    totals["late"] += 1

                elif record.status == AttendanceRecord.Status.EXCUSED:
                    totals["excused"] += 1

            else:
                cell["status"] = "unrecorded"
                cell["label"] = "Not recorded"

            if cell["status"] in {
                "absent",
                "late",
                "excused",
                "holiday",
                "no-class",
            }:
                details.append(cell)

            week.append(cell)

        weeks.append(week)

    previous_month = shift_month(
        selected_month,
        -1,
    )

    next_month = shift_month(
        selected_month,
        1,
    )

    return {
        "weeks": weeks,
        "totals": totals,
        "details": details,
        "selected_month": selected_month,
        "month_value": selected_month.strftime("%Y-%m"),
        "month_label": selected_month.strftime("%B %Y"),
        "previous_month": previous_month.strftime("%Y-%m"),
        "next_month": next_month.strftime("%Y-%m"),
    }