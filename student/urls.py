from django.urls import path

from student.views import StudentSettingDetailView, StudentSettingUpdateView, StudentSettingCreateView, ParentListView, \
    ParentCreateView, ParentDetailView, ParentUpdateView, ParentDeleteView, StudentListView, StudentCreateView, \
    StudentUpdateView, StudentDeleteView, StudentDetailView, change_student_status, select_class_for_export_view, \
    export_class_list_view, capture_fingerprint, identify_student_by_fingerprint, SelectParentView, ParentSearchView, \
    ClassStudentSelectView, GetClassSectionsView, delete_fingerprint, test_scanner_connection, \
    parent_student_upload_view, import_batch_detail_view, download_parent_credentials, download_all_parent_credentials, \
    ajax_create_parent_view, paste_create_parents_view, paste_create_students_view, ajax_create_student_view, \
    UtilityListView, UtilityUpdateView, UtilityCreateView, UtilityDeleteView, ParentPasswordResetView

urlpatterns = [

    # Student Settings URLs (Singleton)
    path('setting/', StudentSettingDetailView.as_view(), name='setting_detail'),
    path('setting/create/', StudentSettingCreateView.as_view(), name='setting_create'),
    path('setting/edit/', StudentSettingUpdateView.as_view(), name='setting_edit'),

    path('utilities/', UtilityListView.as_view(), name='student_utility_list'),
    path('utilities/create/', UtilityCreateView.as_view(), name='student_utility_create'),
    path('utilities/<int:pk>/update/', UtilityUpdateView.as_view(), name='student_utility_update'),
    path('utilities/<int:pk>/delete/', UtilityDeleteView.as_view(), name='student_utility_delete'),

    # Parent URLs
    path('parents/', ParentListView.as_view(), name='parent_index'),
    path('parents/create/', ParentCreateView.as_view(), name='parent_create'),
path('parent/<int:pk>/reset-password/', ParentPasswordResetView.as_view(), name='parent_password_reset'),
    path('parents/<int:pk>/', ParentDetailView.as_view(), name='parent_detail'),
    path('parents/<int:pk>/edit/', ParentUpdateView.as_view(), name='parent_edit'),
    path('parents/<int:pk>/delete/', ParentDeleteView.as_view(), name='parent_delete'),

    # Student URLs
    path('student/by-class/', ClassStudentSelectView.as_view(), name='student_select_class'),
    path('', StudentListView.as_view(), name='student_index'),
    path('create/for-parent/<int:parent_pk>/', StudentCreateView.as_view(), name='student_create'),
    path('<int:pk>/', StudentDetailView.as_view(), name='student_detail'),
    path('<int:pk>/edit/', StudentUpdateView.as_view(), name='student_edit'),
    path('<int:pk>/delete/', StudentDeleteView.as_view(), name='student_delete'),
    path('student/select-parent/', SelectParentView.as_view(), name='select_parent'),
    path('api/parent/search/', ParentSearchView.as_view(), name='parent_search_api'),
    path('api/get-class-sections/', GetClassSectionsView.as_view(), name='get_class_sections'),
    path('import/parent-student/', parent_student_upload_view, name='import_parent_student'),
    path('import/batch/<str:batch_id>/', import_batch_detail_view, name='import_batch_detail'),
    path('import/batch/<str:batch_id>/download-credentials/', download_parent_credentials, name='download_parent_credentials'),
    path('import/download-all-credentials/', download_all_parent_credentials, name='download_all_parent_credentials'),

    # Student Status Action URL
    path('<int:pk>/change-status/<str:status>/', change_student_status, name='change_student_status'),

    # Class List Export URLs
    path('export/select-class/', select_class_for_export_view, name='select_class_for_export'),
    path('export/class-list/', export_class_list_view, name='export_class_list'),

    # Fingerprint API URLs
    path('api/fingerprint/capture/', capture_fingerprint, name='capture_fingerprint'),
    path('api/fingerprint/identify/', identify_student_by_fingerprint, name='identify_student'),
    path('api/fingerprint/delete/', delete_fingerprint, name='delete_fingerprint'),
    path('api/fingerprint/test-scanner/', test_scanner_connection, name='test_scanner'),

    path(
        'paste-create-parents/',
        paste_create_parents_view,
        name='paste_create_parents'
    ),

    # The URL that the JavaScript will call to create each parent (the AJAX endpoint)
    path(
        'ajax/create-parent/',
        ajax_create_parent_view,
        name='ajax_create_parent'
    ),

path(
        'paste-create-students/',
        paste_create_students_view,
        name='paste_create_students'
    ),
    path(
        'ajax/create-student/',
        ajax_create_student_view,
        name='ajax_create_student'
    ),
]

