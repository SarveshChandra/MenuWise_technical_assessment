from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Product, Supplier


class ProductCSVImportTests(APITestCase):
    def test_rejects_unsupported_iso_country_and_currency_codes(self):
        csv_content = """supplier_name,country_code,supplier_sku,product_name,pack_size,unit,currency,price
Supplier,GB,SKU-1,Product,1,each,EUR,10
"""
        upload = SimpleUploadedFile(
            "products.csv",
            csv_content.encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("simple-product-import"),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        row_errors = response.data["validation_errors"][0]["errors"]
        self.assertIn("country_code", row_errors)
        self.assertIn("currency", row_errors)

    def test_simple_import_silently_skips_duplicate_skus(self):
        supplier = Supplier.objects.create(
            name="India Fresh",
            country_code="IN",
        )
        Product.objects.create(
            supplier=supplier,
            supplier_sku="EXISTING",
            product_name="Existing product",
            pack_size=1,
            unit="kg",
            currency="INR",
            price=100,
        )
        csv_content = """supplier_name,country_code,supplier_sku,product_name,pack_size,unit,currency,price
India Fresh,IN,EXISTING,Duplicate existing,1,kg,INR,100
India Fresh,IN,NEW,New product,1,kg,INR,200
India Fresh,IN,NEW,Duplicate in file,1,kg,INR,200
"""
        upload = SimpleUploadedFile(
            "products.csv",
            csv_content.encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("simple-product-import"),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_rows"], 3)
        self.assertEqual(Product.objects.count(), 2)

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
            reverse("simple-product-import"),
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
            reverse("simple-product-import"),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["invalid_rows"], 1)
        row_errors = response.data["validation_errors"][0]["errors"]
        self.assertIn("country_code", row_errors)
        self.assertIn("currency", row_errors)

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
            reverse("simple-product-import"),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_rows"], 3)
        self.assertEqual(response.data["invalid_rows"], 1)
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
            reverse("simple-product-import"),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("missing_columns", response.data)
