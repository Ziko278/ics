from django.urls import path
from admin_site.views import (
    AdminDashboardView, ActivityLogView,

    # Singleton Views
    SchoolInfoDetailView, SchoolInfoCreateView, SchoolInfoUpdateView,
    SchoolSettingDetailView, SchoolSettingCreateView, SchoolSettingUpdateView,

    # Class Section Views (Single Page)
    ClassSectionListView, ClassSectionCreateView, ClassSectionUpdateView, ClassSectionDeleteView,

    # Class Views (Hybrid)
    ClassListView, ClassCreateView, ClassDetailView, ClassUpdateView, ClassDeleteView,

    # Class Roster/Info Views
    ClassSectionInfoDetailView, ClassSectionInfoUpdateView,
    logout_view, login_view,
)

urlpatterns = [
    path('', AdminDashboardView.as_view(), name='admin_dashboard'),
    path('activity-log/', ActivityLogView.as_view(), name='activity_log'),
    path('logout/', logout_view, name='logout'),
    path('login/', login_view, name='login'),

    # Singleton URLs: No PK is needed as there's only one object.
    path('school-info/', SchoolInfoDetailView.as_view(), name='school_info_detail'),
    path('school-info/create/', SchoolInfoCreateView.as_view(), name='school_info_create'),
    path('school-info/update/<int:pk>/', SchoolInfoUpdateView.as_view(), name='school_info_edit'),

    path('school-setting/', SchoolSettingDetailView.as_view(), name='school_setting_detail'),
    path('school-setting/create/', SchoolSettingCreateView.as_view(), name='school_setting_create'),
    path('school-setting/update/<int:pk>/', SchoolSettingUpdateView.as_view(), name='school_setting_edit'),

    # Class Section URLs for the single-page interface
    path('class/section/', ClassSectionListView.as_view(), name='class_section_index'),
    path('class/section/create/', ClassSectionCreateView.as_view(), name='class_section_create'),
    path('class/section/update/<int:pk>/', ClassSectionUpdateView.as_view(), name='class_section_edit'),
    path('class/section/delete/<int:pk>/', ClassSectionDeleteView.as_view(), name='class_section_delete'),

    # Class URLs
    path('class/', ClassListView.as_view(), name='class_index'),
    path('class/create/', ClassCreateView.as_view(), name='class_create'),
    path('class/<int:pk>/', ClassDetailView.as_view(), name='class_detail'),
    path('class/update/<int:pk>/', ClassUpdateView.as_view(), name='class_edit'),
    path('class/delete/<int:pk>/', ClassDeleteView.as_view(), name='class_delete'),


    # Class Roster (Info) URLs
    # The detail view now handles creation, so a separate 'create' URL is not needed.
    path('class/section/info/<int:class_pk>/<int:section_pk>/', ClassSectionInfoDetailView.as_view(),
         name='class_section_info_detail'),
    path('class/section/info/update/<int:pk>/', ClassSectionInfoUpdateView.as_view(), name='class_section_info_edit'),
]

