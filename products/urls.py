from django.urls import path
from .views import ProductCSVImportAPIView, ProductListAPIView

urlpatterns = [
    path("products/", ProductListAPIView.as_view(), name="product-list"),
    path(
        "products/import/",
        ProductCSVImportAPIView.as_view(),
        name="product-import",
    ),
]
