from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APITestCase
from unittest.mock import patch

from .models import Product, Supplier
from .services.html_import import import_products_html


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
            reverse("csv-product-import"),
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
            reverse("csv-product-import"),
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
            reverse("csv-product-import"),
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
            reverse("csv-product-import"),
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
            reverse("csv-product-import"),
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
            reverse("csv-product-import"),
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("missing_columns", response.data)


class ProductReadAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.active_supplier = Supplier.objects.create(
            name="Active Supplier",
            country_code="IN",
            active=True,
        )
        cls.inactive_supplier = Supplier.objects.create(
            name="Inactive Supplier",
            country_code="US",
            active=False,
        )
        cls.chicken = Product.objects.create(
            supplier=cls.active_supplier,
            supplier_sku="CHICKEN-1",
            product_name="Chicken Breast",
            pack_size=1,
            unit="kg",
            currency="INR",
            price=250,
        )
        cls.milk = Product.objects.create(
            supplier=cls.inactive_supplier,
            supplier_sku="MILK-1",
            product_name="Whole Milk",
            pack_size=2,
            unit="l",
            currency="USD",
            price=5,
        )

    def test_product_list_is_paginated(self):
        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 2)

    def test_product_filters_and_search(self):
        response = self.client.get(
            reverse("product-list"),
            {
                "supplier": self.active_supplier.id,
                "currency": "inr",
                "active": "true",
                "search": "chicken",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.chicken.id)

    def test_product_detail(self):
        response = self.client.get(
            reverse("product-detail", kwargs={"pk": self.milk.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["supplier_sku"], "MILK-1")

    def test_supplier_list(self):
        response = self.client.get(reverse("supplier-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)


class SupplierHTMLImportTests(APITestCase):
    @patch("products.views.import_products_html")
    def test_html_import_endpoint(self, mock_import):
        mock_import.return_value = {
            "total_rows": 1,
            "accepted_rows": 1,
            "invalid_rows": 0,
            "validation_errors": [],
        }

        response = self.client.post(
            reverse("html-product-import"),
            {
                "url": "https://supplier.example/prices",
                "supplier_name": "Example Supplier",
                "country_code": "IN",
                "currency": "INR",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        mock_import.assert_called_once_with(
            url="https://supplier.example/prices",
            supplier_name="Example Supplier",
            country_code="IN",
            currency="INR",
        )

    def test_html_import_endpoint_requires_source_and_supplier(self):
        response = self.client.post(
            reverse("html-product-import"),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["missing_fields"],
            ["country_code", "supplier_name", "url"],
        )

    @patch("products.services.html_import.requests.get")
    def test_parses_normalizes_validates_and_stores_table_rows(self, mock_get):
        mock_get.return_value.text = """
        <table>
          <tr><th>Item</th><th>SKU</th><th>Pack</th><th>Unit</th><th>Price</th></tr>
          <tr><td>Rice</td><td>R-1</td><td>5</td><td>kilograms</td><td>100</td></tr>
          <tr><td>Bad Rice</td><td>R-2</td><td>-1</td><td>kg</td><td>50</td></tr>
        </table>
        """

        result = import_products_html(
            url="https://supplier.example/prices",
            supplier_name="Example Supplier",
            country_code="IN",
        )

        mock_get.assert_called_once_with(
            "https://supplier.example/prices",
            timeout=15,
        )
        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(result["invalid_rows"], 1)
        product = Product.objects.get()
        self.assertEqual(product.unit, "kg")
        self.assertEqual(product.currency, "INR")
