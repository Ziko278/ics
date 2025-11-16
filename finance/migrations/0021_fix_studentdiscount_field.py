from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0020_discountmodel_discountapplicationmodel_and_more'),  # Update with your actual previous migration
    ]

    operations = [
        # Step 1: Remove the old unique_together constraint first
        migrations.AlterUniqueTogether(
            name='studentdiscountmodel',
            unique_together=set(),
        ),

        # Step 2: Add the new field
        migrations.AddField(
            model_name='studentdiscountmodel',
            name='invoice_item',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='discounts_applied',
                to='finance.invoiceitemmodel',
                null=True  # Temporarily allow null
            ),
        ),

        # Step 3: Remove the old field
        migrations.RemoveField(
            model_name='studentdiscountmodel',
            name='invoice',
        ),

        # Step 4: Add the new unique_together constraint
        migrations.AlterUniqueTogether(
            name='studentdiscountmodel',
            unique_together={('student', 'discount_application', 'invoice_item')},
        ),

        # Step 5: Make invoice_item non-nullable (if no existing data)
        migrations.AlterField(
            model_name='studentdiscountmodel',
            name='invoice_item',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='discounts_applied',
                to='finance.invoiceitemmodel'
            ),
        ),
    ]