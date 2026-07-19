from django.urls import path
from .views import (
    CSVImportAPIView,
)

urlpatterns = [
    path(
        "products/import/simple/",
        CSVImportAPIView.as_view(),
        name="simple-product-import",
    ),
]
