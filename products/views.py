from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import ProductFilter
from .models import Product, Supplier
from .serializers import ProductSerializer, SupplierSerializer
from .services import CSVImportError, import_products_csv


class ProductListAPIView(generics.ListAPIView):
    queryset = Product.objects.select_related("supplier").order_by("id")
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ["product_name"]


class ProductDetailAPIView(generics.RetrieveAPIView):
    queryset = Product.objects.select_related("supplier")
    serializer_class = ProductSerializer


class SupplierListAPIView(generics.ListAPIView):
    queryset = Supplier.objects.order_by("id")
    serializer_class = SupplierSerializer


class CSVImportAPIView(APIView):
    def post(self, request):
        csv_file = request.FILES.get("file")
        if not csv_file:
            return Response(
                {"error": "CSV file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = import_products_csv(csv_file)
        except CSVImportError as exc:
            return Response(
                exc.payload,
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(result, status=status.HTTP_200_OK)
