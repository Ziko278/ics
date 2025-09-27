from django.contrib import admin
from finance.models import InvoiceModel, InvoiceItemModel


admin.site.register(InvoiceModel)
admin.site.register(InvoiceItemModel)
