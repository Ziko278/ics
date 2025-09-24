from django.contrib import admin
from inventory.models import PurchaseOrderItemModel, PurchaseOrderModel, StockInModel, StockInItemModel


admin.site.register(PurchaseOrderItemModel)
admin.site.register(PurchaseOrderModel)
admin.site.register(StockInModel)
admin.site.register(StockInItemModel)