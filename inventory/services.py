# In inventory/services.py
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone  # Make sure timezone is imported
from django.db.models import F, Sum
from .models import StockInItemModel, StockOutModel, ItemModel, StockTransferModel, StockInModel, StockTransferItemModel
from decimal import Decimal


def perform_stock_out(item, location, quantity_to_remove, reason, created_by_user, specific_batch_id=None,
                      staff_recipient=None, notes=''):
    """
    Performs a stock-out. If a specific_batch_id is provided, it performs a
    targeted removal. Otherwise, it uses a FIFO strategy.
    This is the single source of truth for reducing stock.
    """

    with transaction.atomic():
        # --- PATH 1: Targeted Stock Out from a specific batch ---
        if specific_batch_id:
            batch_to_reduce = get_object_or_404(StockInItemModel, pk=specific_batch_id)
            if quantity_to_remove > batch_to_reduce.quantity_remaining:
                raise ValidationError(
                    f"Insufficient stock in this specific batch. Only {batch_to_reduce.quantity_remaining} available.")

            # Use a direct update query for reliability
            StockInItemModel.objects.filter(pk=batch_to_reduce.pk).update(
                quantity_remaining=F('quantity_remaining') - quantity_to_remove
            )

        # --- PATH 2: General FIFO Stock Out ---
        else:
            available_batches = StockInItemModel.objects.filter(
                item=item, stock_in__location=location, quantity_remaining__gt=0
            ).order_by('stock_in__date_received', 'stock_in__created_at')

            total_available = available_batches.aggregate(total=Sum('quantity_remaining'))['total'] or Decimal('0.00')
            if quantity_to_remove > total_available:
                raise ValidationError(
                    f"Insufficient stock. Only {total_available} units of '{item.name}' are available in the {location}.")

            remaining_to_deduct = quantity_to_remove
            for batch in available_batches:
                if remaining_to_deduct <= 0:
                    break

                quantity_from_this_batch = min(batch.quantity_remaining, remaining_to_deduct)

                # Use a direct update query for reliability
                StockInItemModel.objects.filter(pk=batch.pk).update(
                    quantity_remaining=F('quantity_remaining') - quantity_from_this_batch
                )
                remaining_to_deduct -= quantity_from_this_batch

        # --- COMMON LOGIC for both paths ---
        # 1. Update the master item's total quantity
        item_to_update = ItemModel.objects.select_for_update().get(pk=item.pk)
        if location == 'shop':
            item_to_update.shop_quantity = F('shop_quantity') - quantity_to_remove
        else:
            item_to_update.store_quantity = F('store_quantity') - quantity_to_remove
        item_to_update.save()

        # 2. Create the audit record
        StockOutModel.objects.create(
            item=item, quantity_removed=quantity_to_remove, reason=reason,
            location=location, staff_recipient=staff_recipient, notes=notes,
            created_by=created_by_user
        )


def perform_stock_transfer(direction, items_data, created_by_user, notes=''):
    """
    Performs an atomic, multi-item stock transfer using FIFO logic.
    'items_data' should be a list of dictionaries: [{'item': item_obj, 'quantity': qty}, ...]
    """
    if direction == 'store_to_shop':
        source_location = 'store'
        destination_location = 'shop'
    else: # shop_to_store
        source_location = 'shop'
        destination_location = 'store'

    with transaction.atomic():
        # 1. Create the parent audit records
        transfer_batch = StockTransferModel.objects.create(
            direction=direction, notes=notes, created_by=created_by_user
        )
        stock_in_batch = StockInModel.objects.create(
            source='transfer', location=destination_location,
            notes=f"From transfer {transfer_batch.receipt_number}",
            created_by=created_by_user
        )

        # 2. Loop through each item in the cart
        for data in items_data:
            item = data['item']
            quantity = data['quantity']

            # Create the transfer line item for the audit trail
            StockTransferItemModel.objects.create(transfer=transfer_batch, item=item, quantity=quantity)

            # 3. Perform the Stock Out from the source location using FIFO
            perform_stock_out(
                item=item,
                location=source_location,
                quantity_to_remove=quantity,
                reason='transfer',
                created_by_user=created_by_user
            )

            # 4. Perform the Stock In to the destination location
            StockInItemModel.objects.create(
                stock_in=stock_in_batch,
                item=item,
                quantity_received=quantity,
                unit_cost=item.last_cost_price # Use last cost for internal valuation
            )