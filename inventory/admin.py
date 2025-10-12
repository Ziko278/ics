from django.contrib import admin
from inventory.models import PurchaseOrderItemModel, PurchaseOrderModel, StockInModel, StockInItemModel,InventoryAssignmentModel


admin.site.register(PurchaseOrderItemModel)
admin.site.register(PurchaseOrderModel)
admin.site.register(StockInModel)
admin.site.register(StockInItemModel)
admin.site.register(InventoryAssignmentModel)

