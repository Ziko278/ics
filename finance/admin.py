from django.contrib import admin
from finance.models import InvoiceModel, InvoiceItemModel,SalaryRecord, StaffFundingModel, StudentFundingModel, FeePaymentModel


admin.site.register(InvoiceModel)
admin.site.register(InvoiceItemModel)
admin.site.register(SalaryRecord)
admin.site.register(StaffFundingModel)
admin.site.register(StaffFundingModel)
admin.site.register(FeePaymentModel)
