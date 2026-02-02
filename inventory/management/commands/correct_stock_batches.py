from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import uuid
from inventory.models import ItemModel, StockInModel, StockInItemModel
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db.models import DecimalField


class Command(BaseCommand):
    help = 'Creates correction stock-in batches for items with quantity > stock-in batches'

    def handle(self, *args, **options):
        corrected_count = 0

        items = ItemModel.objects.filter(is_active=True)

        for item in items:
            with transaction.atomic():
                # Determine unit cost
                unit_cost = item.last_cost_price
                if unit_cost == Decimal('0.00'):
                    unit_cost = item.current_selling_price

                # Check shop location
                shop_stock_in_total = StockInItemModel.objects.filter(
                    item=item,
                    stock_in__location='shop'
                ).aggregate(
                    total=Coalesce(Sum('quantity_remaining'), Decimal('0.00'))
                )['total']

                shop_deficit = item.shop_quantity - shop_stock_in_total

                if shop_deficit > Decimal('0.00'):
                    stock_in_batch = StockInModel.objects.create(
                        receipt_number=f"ADJ-INIT-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
                        source=StockInModel.Source.ADJUSTMENT,
                        location='shop',
                        date_received=timezone.now().date(),
                        notes="Initial stock adjustment"
                    )

                    # Use skip_inventory_update to prevent double addition
                    stock_in_item = StockInItemModel(
                        stock_in=stock_in_batch,
                        item=item,
                        quantity_received=shop_deficit,
                        unit_cost=unit_cost
                    )
                    stock_in_item.save(skip_inventory_update=True)

                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Created shop correction for {item.name}: {shop_deficit}'
                        )
                    )
                    corrected_count += 1

                # Check store location
                store_stock_in_total = StockInItemModel.objects.filter(
                    item=item,
                    stock_in__location='store'
                ).aggregate(
                    total=Coalesce(Sum('quantity_remaining'), Decimal('0.00'))
                )['total']

                store_deficit = item.store_quantity - store_stock_in_total

                if store_deficit > Decimal('0.00'):
                    stock_in_batch = StockInModel.objects.create(
                        receipt_number=f"ADJ-INIT-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
                        source=StockInModel.Source.ADJUSTMENT,
                        location='store',
                        date_received=timezone.now().date(),
                        notes="Initial stock adjustment"
                    )

                    stock_in_item = StockInItemModel(
                        stock_in=stock_in_batch,
                        item=item,
                        quantity_received=store_deficit,
                        unit_cost=unit_cost
                    )
                    stock_in_item.save(skip_inventory_update=True)

                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Created store correction for {item.name}: {store_deficit}'
                        )
                    )
                    corrected_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully corrected {corrected_count} stock batches'
            )
        )