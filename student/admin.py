from django.contrib import admin
from student.models import StudentModel, StudentWalletModel, ParentModel, ParentProfileModel


admin.site.register(StudentModel)
admin.site.register(StudentWalletModel)
admin.site.register(ParentModel)
admin.site.register(ParentProfileModel)
