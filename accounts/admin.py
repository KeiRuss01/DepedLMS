from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Parent,
    ParentStudentLink,
    Principal,
    School,
    Student,
    Supervisor,
    Teacher,
    User,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the custom auth user. Field layout is based on Django's
    built-in UserAdmin but swapped to our email/role/status columns."""

    ordering = ("email",)
    list_display = ("email", "role", "status", "is_staff", "created_at")
    list_filter = ("role", "status", "is_staff")
    search_fields = ("email",)
    readonly_fields = ("created_at", "updated_at", "last_login")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Role & status", {"fields": ("role", "status", "phone_number")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "role", "password1", "password2"),
            },
        ),
    )


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("school_id", "school_name", "district")
    search_fields = ("school_name", "district")


@admin.register(Principal)
class PrincipalAdmin(admin.ModelAdmin):
    list_display = ("principal_id", "firstname", "lastname", "school", "designation")
    search_fields = ("firstname", "lastname", "employee_id")


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ("teacher_id", "firstname", "lastname", "school", "specialization")
    search_fields = ("firstname", "lastname", "employee_id")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_id", "lrn", "firstname", "lastname", "school", "acc_status")
    list_filter = ("acc_status", "gender", "school")
    search_fields = ("firstname", "lastname", "lrn")


@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = ("parent_id", "firstname", "lastname", "relationship")
    search_fields = ("firstname", "lastname")


@admin.register(ParentStudentLink)
class ParentStudentLinkAdmin(admin.ModelAdmin):
    list_display = ("link_id", "parent", "student", "relationship", "status")
    list_filter = ("relationship", "status")
    search_fields = (
        "parent__firstname",
        "parent__lastname",
        "student__firstname",
        "student__lastname",
        "student__lrn",
    )


@admin.register(Supervisor)
class SupervisorAdmin(admin.ModelAdmin):
    list_display = ("supervisor_id", "firstname", "lastname", "district", "designation")
    search_fields = ("firstname", "lastname", "employee_id")
