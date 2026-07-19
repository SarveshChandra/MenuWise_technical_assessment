from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError

# Supplier model
class Supplier(models.Model):
    name=models.CharField(max_length=300)
    country_code=models.CharField(max_length=2)
    active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            # Unique supplier name to country combination to avoid duplicate insertions
            models.UniqueConstraint(
                fields=["name","country_code"],
                name="unique_supplier_name_country"
            )
        ]

# Product model
class Product(models.Model):
    supplier=models.ForeignKey(Supplier,on_delete=models.PROTECT,related_name="products")
    supplier_sku=models.CharField(max_length=100)
    product_name=models.CharField(max_length=300)
    pack_size=models.IntegerField()
    unit=models.CharField(max_length=4)
    currency=models.CharField(max_length=3,blank=True,db_index=True)
    price=models.DecimalField(max_digits=10,decimal_places=4)
    imported_at=models.DateTimeField(auto_now_add=True,db_index=True)

    def __str__(self):
        return self.product_name
    
    class Meta:
        # Field constraints for data validation/integrity
        constraints = [
            # unique sku per supplier
            models.UniqueConstraint(
                fields=["supplier","supplier_sku"],
                name="unique_sku_per_supplier"
            ),
            # pack size must be greater than 0
            models.CheckConstraint(
                condition=Q(pack_size__gt=0),
                name="product_pack_size_gt_zero"
            ),
            # unit must be one of the supported units
            models.CheckConstraint(
                condition=Q(unit__in=['g','kg','ml','l','each']),
                name="product_unit_supported"
            ),
            # price cannot be negative
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="product_price_gte_zero"
            )
        ]