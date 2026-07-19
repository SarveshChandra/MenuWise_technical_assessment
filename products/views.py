from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product
from .serializers import ProductSerializer
from .services import CSVImportError, import_products_csv

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