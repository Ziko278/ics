from django.contrib import admin
from finance.models import InvoiceModel, InvoiceItemModel,SalaryRecord


admin.site.register(InvoiceModel)
admin.site.register(InvoiceItemModel)
admin.site.register(SalaryRecord)
