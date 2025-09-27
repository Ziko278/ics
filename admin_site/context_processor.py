from django.db.models import F, ExpressionWrapper

from admin_site.models import SchoolInfoModel, SchoolSettingModel
from django.db.models import F, Q, Case, When, Value, DecimalField
from inventory.models import ItemModel


def school_info(request):
    info = SchoolInfoModel.objects.first()
    academic = SchoolSettingModel.objects.first()
    low_stock_list = ItemModel.objects.annotate(
    total_qty=ExpressionWrapper(
        F('shop_quantity') + F('store_quantity'),
        output_field=DecimalField(max_digits=10, decimal_places=2)
    )
).filter(total_qty__lte=F('reorder_level'))
    return {
        'school_info': info,
        'academic_info': academic,
        'low_stock_list': low_stock_list,
        'low_stock': low_stock_list.count(),
    }
