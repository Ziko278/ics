from django.contrib import admin
from inventory.models import PurchaseOrderItemModel, InventoryCollectionModel, PurchaseOrderModel, StockInModel, StockInItemModel,InventoryAssignmentModel, SaleModel, SaleItemModel


admin.site.register(PurchaseOrderItemModel)
admin.site.register(PurchaseOrderModel)
admin.site.register(StockInModel)
admin.site.register(StockInItemModel)
admin.site.register(InventoryAssignmentModel)
admin.site.register(InventoryCollectionModel)
admin.site.register(SaleItemModel)
admin.site.register(SaleModel)

