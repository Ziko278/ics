from django.contrib import admin
from student.models import StudentModel, StudentWalletModel


admin.site.register(StudentModel)
admin.site.register(StudentWalletModel)