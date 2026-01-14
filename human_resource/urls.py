from django.urls import path
from .views import *

urlpatterns = [

    path('department/create', DepartmentCreateView.as_view(), name='department_create'),
    path('department/index', DepartmentListView.as_view(), name='department_index'),
    path('department/<int:pk>/detail', DepartmentDetailView.as_view(), name='department_detail'),
    path('department/<int:pk>/edit', DepartmentUpdateView.as_view(), name='department_edit'),
    path('department/<int:pk>/delete', DepartmentDeleteView.as_view(), name='department_delete'),

    # Staff URLs
    path('staff/', StaffListView.as_view(), name='staff_index'),
    path('staff/create/', StaffCreateView.as_view(), name='staff_create'),
    path('staff/<int:pk>/', StaffDetailView.as_view(), name='staff_detail'),
    path('staff/<int:pk>/edit/', StaffUpdateView.as_view(), name='staff_edit'),
    path('staff/<int:pk>/delete/', StaffDeleteView.as_view(), name='staff_delete'),
    path('staff/upload/', staff_upload_view, name='staff_upload'),
    path('staff/upload/status/<str:task_id>/', staff_upload_status_view, name='staff_upload_status'),
    path('api/task-status/<str:task_id>/', get_task_status_api, name='get_task_status_api'),


    # Staff Account Action URLs
    path('staff/<int:pk>/generate-login/', generate_staff_login, name='staff_generate_login'),
    path('staff/<int:pk>/update-login/', update_staff_login, name='staff_update_login'),
    path('staff/<int:pk>/disable/', disable_staff, name='staff_disable'),
    path('staff/<int:pk>/enable/', enable_staff, name='staff_enable'),
    path('dashboard/', hr_dashboard_view, name='hr_dashboard'),
    path('staff/profile/', staff_profile_view, name='staff_profile'),

    # Group & Permission URLs
    path('groups/', GroupListView.as_view(), name='group_index'),
    path('groups/create/', GroupCreateView.as_view(), name='group_create'),
    path('groups/<int:pk>/edit/', GroupUpdateView.as_view(), name='group_edit'),
    path('groups/<int:pk>/delete/', GroupDeleteView.as_view(), name='group_delete'),
    path('groups/<int:pk>/permissions/', group_permission_view, name='group_permissions'),

    # HR Settings URLs (Singleton Pattern)
    path('settings/', HRSettingDetailView.as_view(), name='hr_setting_detail'),
    path('settings/create/', HRSettingCreateView.as_view(), name='hr_setting_create'),
    path('settings/edit/', HRSettingUpdateView.as_view(), name='hr_setting_edit'),
    path('export/all-staff/', export_all_staff_view, name='export_all_staff'),
]

