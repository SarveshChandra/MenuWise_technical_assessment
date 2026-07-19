from rest_framework import serializers
from .models import Product, Supplier

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id","name","country_code","active","created_at"]

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "supplier", "supplier_sku", "product_name", "pack_size", "unit", "currency", "price", "imported_at"]