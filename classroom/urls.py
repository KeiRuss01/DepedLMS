from django.urls import path

from . import views


app_name = "classroom"

urlpatterns = [
    path(
        "",
        views.dashboard_view,
        name="dashboard",
    ),

    path(
        "classes/",
        views.classes_view,
        name="classes",
    ),

    path(
        "classes/create/",
        views.create_class_view,
        name="create_class",
    ),

    path(
        "classes/join/",
        views.join_class_view,
        name="join_class",
    ),

    path(
        "classes/<int:classroom_id>/",
        views.class_detail_view,
        name="class_detail",
    ),

    path(
        "classes/<int:classroom_id>/invite/",
        views.invite_student_view,
        name="invite_student",
    ),

    path(
        "invitations/<int:enrollment_id>/<str:action>/",
        views.respond_to_invitation_view,
        name="respond_to_invitation",
    ),

    path(
        "join-requests/<int:enrollment_id>/<str:action>/",
        views.respond_to_join_request_view,
        name="respond_to_join_request",
    ),

    path(
        "classes/<int:classroom_id>/classroom/",
        views.class_page_view,
        name="class_page",
    ),

    path(
        "family/children/",
        views.parent_children_view,
        name="parent_children",
    ),

    path(
        "family/parent-requests/",
        views.student_parent_requests_view,
        name="student_parent_requests",
    ),

    path(
        "family/parent-requests/<int:link_id>/<str:action>/",
        views.respond_parent_link_view,
        name="respond_parent_link",
    ),

    path(
        "classes/<int:classroom_id>/modules/",
        views.module_list_view,
        name="module_list",
    ),

    path(
        "classes/<int:classroom_id>/modules/create/",
        views.module_create_view,
        name="module_create",
    ),

    path(
        "modules/<int:module_id>/manage/",
        views.module_manage_view,
        name="module_manage",
    ),

    path(
        "modules/<int:module_id>/work/",
        views.module_work_view,
        name="module_work",
    ),

    path(
        "modules/<int:module_id>/submissions/",
        views.module_submissions_view,
        name="module_submissions",
    ),

    path(
        "module-submissions/<int:submission_id>/review/",
        views.module_review_view,
        name="module_review",
    ),

    path(
        "modules/<int:module_id>/pdf/",
        views.module_pdf_view,
        name="module_pdf",
    ),

    path(
        "module-submissions/<int:submission_id>/file/",
        views.module_attachment_view,
        name="module_attachment",
    ),
]
