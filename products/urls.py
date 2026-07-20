from django.urls import path
from .views import (
    CSVImportAPIView,
    ProductDetailAPIView,
    ProductListAPIView,
    SupplierListAPIView,
)

urlpatterns = [
    path("products/", ProductListAPIView.as_view(), name="product-list"),
    path(
        "products/<int:pk>/",
        ProductDetailAPIView.as_view(),
        name="product-detail",
    ),
    path("suppliers/", SupplierListAPIView.as_view(), name="supplier-list"),
    path(
        "products/import/csv/",
        CSVImportAPIView.as_view(),
        name="csv-product-import",
    ),
]
