from django.contrib import admin
from student.models import StudentModel, StudentWalletModel, ParentModel


admin.site.register(StudentModel)
admin.site.register(StudentWalletModel)
admin.site.register(ParentModel)