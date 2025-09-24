from django.urls import path
from .views import *

urlpatterns = [
    # Staff URLs
    path('staff/', StaffListView.as_view(), name='staff_index'),
    path('staff/create/', StaffCreateView.as_view(), name='staff_create'),
    path('staff/<int:pk>/', StaffDetailView.as_view(), name='staff_detail'),
    path('staff/<int:pk>/edit/', StaffUpdateView.as_view(), name='staff_edit'),
    path('staff/<int:pk>/delete/', StaffDeleteView.as_view(), name='staff_delete'),

    # Staff Account Action URLs
    path('staff/<int:pk>/generate-login/', generate_staff_login, name='staff_generate_login'),
    path('staff/<int:pk>/update-login/', update_staff_login, name='staff_update_login'),
    path('staff/<int:pk>/disable/', disable_staff, name='staff_disable'),
    path('staff/<int:pk>/enable/', enable_staff, name='staff_enable'),

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
]

