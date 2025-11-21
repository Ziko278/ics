from django.contrib import admin
from finance.models import InvoiceModel, ExpenseModel, DiscountModel, DiscountApplicationModel, StudentDiscountModel, InvoiceItemModel,SalaryRecord, StaffFundingModel, StudentFundingModel, FeePaymentModel


admin.site.register(InvoiceModel)
admin.site.register(InvoiceItemModel)
admin.site.register(SalaryRecord)
admin.site.register(StaffFundingModel)
admin.site.register(StudentFundingModel)
admin.site.register(FeePaymentModel)
admin.site.register(StudentDiscountModel)
admin.site.register(DiscountModel)
admin.site.register(DiscountApplicationModel)
admin.site.register(ExpenseModel)
