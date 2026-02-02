from inventory.models import StockInModel, StockInItemModel, ItemModel
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import uuid


@receiver(post_save, sender=ItemModel)
def create_initial_stock_in(sender, instance, created, **kwargs):
    """
    Creates initial stock-in batch when a new item is created with quantity > 0
    """
    if not created:
        return

    with transaction.atomic():
        # Determine unit cost (last_cost_price → current_selling_price → 0.00)
        unit_cost = instance.last_cost_price
        if unit_cost == Decimal('0.00'):
            unit_cost = instance.current_selling_price

        # Handle shop quantity
        if instance.shop_quantity > Decimal('0.00'):
            stock_in_batch = StockInModel.objects.create(
                receipt_number=f"ADJ-INIT-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
                source=StockInModel.Source.ADJUSTMENT,
                location='shop',
                date_received=timezone.now().date(),
                notes="Initial stock adjustment",
                created_by=instance.created_by
            )

            stock_in_item = StockInItemModel(
                stock_in=stock_in_batch,
                item=instance,
                quantity_received=instance.shop_quantity,
                unit_cost=unit_cost
            )
            stock_in_item.save(skip_inventory_update=True)

        # Handle store quantity
        if instance.store_quantity > Decimal('0.00'):
            stock_in_batch = StockInModel.objects.create(
                receipt_number=f"ADJ-INIT-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
                source=StockInModel.Source.ADJUSTMENT,
                location='store',
                date_received=timezone.now().date(),
                notes="Initial stock adjustment",
                created_by=instance.created_by
            )

            stock_in_item = StockInItemModel(
                stock_in=stock_in_batch,
                item=instance,
                quantity_received=instance.store_quantity,
                unit_cost=unit_cost
            )
            stock_in_item.save(skip_inventory_update=True)