from django.contrib import admin
from human_resource.models import StaffProfileModel, StaffModel, StaffWalletModel


admin.site.register(StaffProfileModel)
admin.site.register(StaffModel)
admin.site.register(StaffWalletModel)
