from django.urls import path
from cafeteria.views import (
    MealListView, MealCreateView, MealUpdateView, MealDeleteView,
    CafeteriaSettingDetailView, CafeteriaSettingCreateView, CafeteriaSettingUpdateView,
    MealCollectionLiveView, MealCollectionHistoryView, StudentSearchForMealAjaxView, RecordMealAjaxView,
)

urlpatterns = [
    # --- Meal Type URLs ---
    path('cafeteria/meals/', MealListView.as_view(), name='cafeteria_meal_list'),
    path('cafeteria/meals/create/', MealCreateView.as_view(), name='cafeteria_meal_create'),
    path('cafeteria/meals/<int:pk>/update/', MealUpdateView.as_view(), name='cafeteria_meal_update'),
    path('cafeteria/meals/<int:pk>/delete/', MealDeleteView.as_view(), name='cafeteria_meal_delete'),

    path('cafeteria/settings/', CafeteriaSettingDetailView.as_view(), name='cafeteria_settings_detail'),
    path('cafeteria/settings/create/', CafeteriaSettingCreateView.as_view(), name='cafeteria_settings_create'),
    path('cafeteria/settings/update/', CafeteriaSettingUpdateView.as_view(), name='cafeteria_settings_update'),

    path('cafeteria/collection/live/', MealCollectionLiveView.as_view(), name='cafeteria_collection_live'),
    # The historical log of all collections
    path('cafeteria/collection/history/', MealCollectionHistoryView.as_view(), name='cafeteria_collection_history'),

    # --- AJAX URLs for the Live Collection Page ---
    path('cafeteria/ajax/search-student/', StudentSearchForMealAjaxView.as_view(),
         name='cafeteria_ajax_search_student'),
    path('cafeteria/ajax/record-meal/', RecordMealAjaxView.as_view(), name='cafeteria_ajax_record_meal'),

]
