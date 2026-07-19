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
    
    def clean(self):
        super().clean()
        errors={}
        # validate country_code field
        if self.country_code:
            self.country_code=self.country_code.strip().upper()
            if len(self.country_code)!=2 or not self.country_code.isalpha():
                errors["country_code"]="Country code must be a 2-letter alphabetic text."
        if errors:
            raise ValidationError(errors)

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
    
    # Field constraints for data validation/integrity
    class Meta:
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
    
    def clean(self):
        super().clean()
        errors={}
        # normalize/validate currency field
        if not self.currency and self.supplier_id:
            if self.supplier.country_code=="IN":
                self.currency="INR"
            else:
                self.currency="USD"
        elif self.currency:
            self.currency=self.currency.strip().upper()
            if len(self.currency)!=3 or not self.currency.isalpha():
                errors["currency"]="Currency must be a 3-letter alphabetic text."
        # normalize and validate unit field
        unit_map={
            "g":"g",
            "gram":"g",
            "grams":"g",
            "kg":"kg",
            "kilogram":"kg",
            "kilograms":"kg",
            "ml":"ml",
            "l":"l",
            "litre":"l",
            "litres":"l",
            "each":"each",
            "ea":"each",
            "piece":"each",
            "peace":"each"
        }
        if self.unit:
            clean_unit=self.unit.strip().lower()
            if clean_unit not in unit_map:
                errors["unit"]="Supported units are g,kg,ml,l,each."
            else:
                self.unit=unit_map[clean_unit]
        # validate price field
        if self.price is not None:
            if self.price < 0:
                errors["price"]="Price cannot be negative."
        # validate pack_size field
        if self.pack_size is not None:
            if self.pack_size <= 0:
                errors["pack_size"]="Pack size must be greater than 0."
        # Raise validation error if any errors were found
        if errors:
            raise ValidationError(errors)