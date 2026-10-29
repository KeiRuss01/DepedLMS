from django.urls import path

from . import activity_views, messaging_views, views


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
        "calendar/",
        views.calendar_view,
        name="calendar",
    ),

    path(
        "tasks/",
        views.tasks_view,
        name="tasks",
    ),

    path(
        "feedback/",
        views.student_feedback_view,
        name="student_feedback",
    ),
    
    path(
        "messages/",
        messaging_views.message_inbox_view,
        name="message_inbox",
    ),
    path(
        "messages/start/",
        messaging_views.message_conversation_start_view,
        name="message_conversation_start",
    ),
    path(
        "messages/<int:conversation_id>/",
        messaging_views.message_conversation_view,
        name="message_conversation",
    ),
    path(
        "messages/<int:conversation_id>/panel/",
        messaging_views.message_panel_conversation_view,
        name="message_panel_conversation",
    ),
    path(
        "messages/<int:conversation_id>/send/",
        messaging_views.message_send_view,
        name="message_send",
    ),

    path(
        "messages/status/",
        messaging_views.message_status_view,
        name="message_status",
    ),

    path(
        "calendar/events/<int:event_id>/cancel/",
        views.class_calendar_event_cancel_view,
        name="calendar_event_cancel",
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
        "classes/<int:classroom_id>/status/<str:action>/",
        views.class_lifecycle_view,
        name="class_lifecycle",
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
        "enrollments/<int:enrollment_id>/remove/",
        views.remove_student_view,
        name="remove_student",
    ),

    path(
        "classes/<int:classroom_id>/classroom/",
        views.class_page_view,
        name="class_page",
    ),
    path(
        "classes/<int:classroom_id>/activities/create/",
        activity_views.activity_create_view,
        name="activity_create",
    ),
    path(
        "activities/<int:activity_id>/",
        activity_views.activity_detail_view,
        name="activity_detail",
    ),
    path(
        "activities/<int:activity_id>/edit/",
        activity_views.activity_edit_view,
        name="activity_edit",
    ),
    path(
        "activities/<int:activity_id>/status/",
        activity_views.activity_status_view,
        name="activity_status",
    ),
    path(
        "activities/<int:activity_id>/resource/",
        activity_views.activity_resource_view,
        name="activity_resource",
    ),
    path(
        "activities/<int:activity_id>/resource/view/",
        activity_views.activity_resource_reader_view,
        name="activity_resource_reader",
    ),
    path(
        "activity-submissions/<int:submission_id>/review/",
        activity_views.activity_review_view,
        name="activity_review",
    ),
    path(
        "activity-submissions/<int:submission_id>/pdf/",
        activity_views.activity_submission_pdf_view,
        name="activity_submission_pdf",
    ),
    path(
        "activity-submissions/<int:submission_id>/pdf/view/",
        activity_views.activity_submission_pdf_reader_view,
        name="activity_submission_pdf_reader",
    ),
    path(
        "classes/<int:classroom_id>/announcements/create/",
        views.announcement_create_view,
        name="announcement_create",
    ),
    path(
        "announcements/<int:announcement_id>/edit/",
        views.announcement_edit_view,
        name="announcement_edit",
    ),
    path(
        "announcements/<int:announcement_id>/delete/",
        views.announcement_delete_view,
        name="announcement_delete",
    ),
    path(
        "classes/<int:classroom_id>/posts/create/",
        views.class_post_create_view,
        name="class_post_create",
    ),
    path(
        "posts/<int:post_id>/edit/",
        views.class_post_edit_view,
        name="class_post_edit",
    ),
    path(
        "posts/<int:post_id>/delete/",
        views.class_post_delete_view,
        name="class_post_delete",
    ),
    path(
        "posts/<int:post_id>/comments/create/",
        views.comment_create_view,
        name="comment_create",
    ),

    path(
        "comments/<int:comment_id>/delete/",
        views.comment_delete_view,
        name="comment_delete",
    ),
    path(
        "classes/<int:classroom_id>/grades/",
        views.gradebook_view,
        name="gradebook",
    ),
    path(
        "classes/<int:classroom_id>/attendance/",
        views.attendance_view,
        name="attendance",
    ),
    path(
        "classes/<int:classroom_id>/attendance/offline-roster/",
        views.teacher_offline_roster_view,
        name="teacher_offline_roster",
    ),
    path(
        "classes/<int:classroom_id>/grades/offline-data/",
        views.teacher_offline_gradebook_data_view,
        name="teacher_offline_gradebook_data",
    ),
    path(
        "classes/<int:classroom_id>/grades/offline-sync/",
        views.teacher_offline_scores_sync_view,
        name="teacher_offline_scores_sync",
    ),
    path(
        "classes/<int:classroom_id>/grades/offline-create-item/",
        views.teacher_offline_grade_item_create_view,
        name="teacher_offline_grade_item_create",
    ),
    path(
        "classes/<int:classroom_id>/my-attendance/",
        views.student_attendance_view,
        name="student_attendance",
    ),
    path(
        "classes/<int:classroom_id>/students/<int:student_id>/performance/",
        views.student_performance_report_view,
        name="student_performance_report",
    ),
    path(
        "grade-items/<int:item_id>/delete/",
        views.grade_item_delete_view,
        name="grade_item_delete",
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
        "family/progress/",
        views.parent_progress_view,
        name="parent_progress",
    ),

    path(
        "modules/<int:module_id>/offline-data/",
        views.module_offline_data_view,
        name="module_offline_data",
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
        "modules/<int:module_id>/edit/",
        views.module_edit_view,
        name="module_edit",
    ),

    path(
        "modules/<int:module_id>/delete/",
        views.module_delete_view,
        name="module_delete",
    ),

    path(
        "modules/<int:module_id>/work/",
        views.module_work_view,
        name="module_work",
    ),

    path(
        "modules/<int:module_id>/reopen-submission/",
        views.module_reopen_submission_view,
        name="module_reopen_submission",
    ),

    path(
        "modules/<int:module_id>/mobile-draft/",
        views.module_mobile_draft_view,
        name="module_mobile_draft",
    ),

    path(
        "modules/<int:module_id>/offline-submit/",
        views.module_offline_submit_view,
        name="module_offline_submit",
    ),

    path(
        "modules/<int:module_id>/mobile-annotations/save/",
        views.module_mobile_annotations_save_view,
        name="module_mobile_annotations_save",
    ),

    path(
        "modules/<int:module_id>/extra-pages/add/",
        views.module_extra_page_create_view,
        name="module_extra_page_create",
    ),

    path(
        "module-extra-pages/<int:extra_page_id>/update/",
        views.module_extra_page_update_view,
        name="module_extra_page_update",
    ),

    path(
        "module-extra-pages/<int:extra_page_id>/delete/",
        views.module_extra_page_delete_view,
        name="module_extra_page_delete",
    ),

    path(
        "module-extra-pages/<int:extra_page_id>/file/",
        views.module_extra_page_file_view,
        name="module_extra_page_file",
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

    path(
        "module-submissions/<int:submission_id>/answered-pdf/",
        views.submission_pdf_view,
        name="submission_pdf",
    ),
    
    path(
        "classes/<int:classroom_id>/attendance/offline-sync/",
        views.teacher_offline_attendance_sync_view,
        name="teacher_offline_attendance_sync",
    ),

]
