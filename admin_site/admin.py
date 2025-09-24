from django.contrib import admin
from admin_site.models import SessionModel, SchoolSettingModel, ClassesModel, TermModel


admin.site.register(SessionModel)
admin.site.register(TermModel)
admin.site.register(SchoolSettingModel)
admin.site.register(ClassesModel)