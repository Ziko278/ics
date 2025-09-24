from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('', include('admin_site.urls')),
    path('admin/student/', include('student.urls')),
    path('admin/cafeteria/', include('cafeteria.urls')),
    path('admin/inventory/', include('inventory.urls')),
    path('admin/finance/', include('finance.urls')),
    path('admin/human-resource/', include('human_resource.urls')),
    path('django-admin/', admin.site.urls),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
