from django.urls import path
# from .views import (
#     ProductDetailView,
#     ProductImportView,
#     ProductListView,
#     SupplierListView,
# )

urlpatterns = [
    path("products/", ProductListView.as_view(), name="product-list"),
    # path(

    #     "products/<int:pk>/",

    #     ProductDetailView.as_view(),

    #     name="product-detail",

    # ),

    # path(

    #     "products/import/",

    #     ProductImportView.as_view(),

    #     name="product-import",

    # ),

    # path("suppliers/", SupplierListView.as_view(), name="supplier-list")
]