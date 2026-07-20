from django_filters import rest_framework as filters

from .models import Product


class ProductFilter(filters.FilterSet):
    supplier = filters.NumberFilter(field_name="supplier_id")
    currency = filters.CharFilter(
        field_name="currency",
        lookup_expr="iexact",
    )
    active = filters.BooleanFilter(field_name="supplier__active")

    class Meta:
        model = Product
        fields = ["supplier", "currency", "active"]
