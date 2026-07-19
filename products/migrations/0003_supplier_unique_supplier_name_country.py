from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0002_alter_product_currency_alter_product_unit_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="supplier",
            constraint=models.UniqueConstraint(
                fields=("name", "country_code"),
                name="unique_supplier_name_country",
            ),
        ),
    ]
