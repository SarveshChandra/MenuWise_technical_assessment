from django.contrib import admin
from django.db.models import Count

from .models import Product, Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "country_code",
        "active",
        "product_count",
        "created_at",
    )
    list_filter = ("active", "country_code", "created_at")
    search_fields = ("name", "country_code")
    readonly_fields = ("created_at",)
    ordering = ("name", "country_code")
    list_per_page = 100

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_product_count=Count("products"))

    @admin.display(ordering="_product_count", description="Products")
    def product_count(self, supplier):
        return supplier._product_count


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "product_name",
        "supplier",
        "supplier_sku",
        "pack_size",
        "unit",
        "currency",
        "price",
        "imported_at",
    )
    list_filter = (
        "supplier",
        "supplier__active",
        "currency",
        "unit",
        "imported_at",
    )
    search_fields = (
        "product_name",
        "supplier_sku",
        "supplier__name",
    )
    autocomplete_fields = ("supplier",)
    readonly_fields = ("imported_at",)
    list_select_related = ("supplier",)
    ordering = ("-imported_at",)
    date_hierarchy = "imported_at"
    list_per_page = 100
