from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Product, Supplier
from .views import get_existing_keys


class ProductCSVImportTests(APITestCase):
    def test_rejects_malformed_csv(self):
        csv_content = """supplier_name,country_code,supplier_sku,product_name,pack_size,unit,currency,price
Supplier,IN,"UNFINISHED
"""
        upload = SimpleUploadedFile(
            "products.csv",
            csv_content.encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("product-import"),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid CSV format", response.data["error"])

    def test_rejects_non_ascii_country_and_currency_codes(self):
        csv_content = """supplier_name,country_code,supplier_sku,product_name,pack_size,unit,currency,price
Supplier,ÅB,SKU-1,Product,1,each,UŚD,10
"""
        upload = SimpleUploadedFile(
            "products.csv",
            csv_content.encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("product-import"),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["imported_rows"], 0)
        row_errors = response.data["errors"][0]["errors"]
        self.assertIn("country_code", row_errors)
        self.assertIn("currency", row_errors)

    def test_existing_key_query_uses_exact_supplier_sku_pairs(self):
        supplier_one = Supplier.objects.create(name="One", country_code="IN")
        supplier_two = Supplier.objects.create(name="Two", country_code="US")

        Product.objects.create(
            supplier=supplier_one,
            supplier_sku="B",
            product_name="Cross combination",
            pack_size=1,
            unit="each",
            currency="INR",
            price=1,
        )
        Product.objects.create(
            supplier=supplier_two,
            supplier_sku="B",
            product_name="Exact combination",
            pack_size=1,
            unit="each",
            currency="USD",
            price=1,
        )

        candidates = [
            (2, Product(supplier=supplier_one, supplier_sku="A")),
            (3, Product(supplier=supplier_two, supplier_sku="B")),
        ]

        self.assertEqual(
            get_existing_keys(candidates),
            {(supplier_two.id, "B")},
        )

    def test_imports_valid_rows_and_reports_invalid_and_duplicate_rows(self):
        csv_content = """supplier_name,country_code,supplier_sku,product_name,pack_size,unit,currency,price
India Fresh,IN,CHA-001,Chicken Breast,1,kilograms,,250
India Fresh,IN,CHA-001,Duplicate,1,kg,INR,250
Fresh Foods,US,ERR-001,Bad Product,-1,kg,USD,-50
"""
        upload = SimpleUploadedFile(
            "products.csv",
            csv_content.encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("product-import"),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["imported_rows"], 1)
        self.assertEqual(response.data["invalid_rows"], 2)
        product = Product.objects.get()
        self.assertEqual(product.unit, "kg")
        self.assertEqual(product.currency, "INR")

    def test_requires_expected_columns(self):
        upload = SimpleUploadedFile(
            "products.csv",
            b"supplier_name,product_name\nSupplier,Product\n",
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("product-import"),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("missing_columns", response.data)
