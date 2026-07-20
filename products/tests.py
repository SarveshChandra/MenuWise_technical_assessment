from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Product, Supplier


class ProductTests(APITestCase):
    def test_model_validation(self):
        supplier = Supplier.objects.create(name="Supplier", country_code="IN")
        product = Product(
            supplier=supplier,
            supplier_sku="BAD-1",
            product_name="Invalid product",
            pack_size=0,
            unit="oz",
            currency="INR",
            price=-1,
        )

        with self.assertRaises(ValidationError) as error:
            product.full_clean()

        messages = " ".join(error.exception.messages)
        self.assertIn("product_pack_size_gt_zero", messages)
        self.assertIn("product_unit_supported", messages)
        self.assertIn("product_price_gte_zero", messages)

    def test_csv_import(self):
        file = SimpleUploadedFile(
            "products.csv",
            (
                "supplier_name,country_code,supplier_sku,product_name,"
                "pack_size,unit,currency,price\n"
                "India Fresh,IN,RICE-1,Rice,5,kilograms,,100\n"
                "India Fresh,IN,BAD-1,Bad Product,-1,kg,INR,-10\n"
            ).encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("csv-product-import"),
            {"file": file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_rows"], 2)
        self.assertEqual(response.data["accepted_rows"], 1)
        self.assertEqual(response.data["invalid_rows"], 1)
        self.assertEqual(response.data["validation_errors"][0]["row"], 3)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(Supplier.objects.count(), 1)
        product = Product.objects.get()
        self.assertEqual(product.supplier.name, "India Fresh")
        self.assertEqual(product.unit, "kg")
        self.assertEqual(product.currency, "INR")

    def test_api_filtering(self):
        active_supplier = Supplier.objects.create(
            name="Active Supplier",
            country_code="IN",
            active=True,
        )
        inactive_supplier = Supplier.objects.create(
            name="Inactive Supplier",
            country_code="US",
            active=False,
        )
        expected = Product.objects.create(
            supplier=active_supplier,
            supplier_sku="RICE-1",
            product_name="Rice",
            pack_size=1,
            unit="kg",
            currency="INR",
            price=100,
        )
        Product.objects.create(
            supplier=inactive_supplier,
            supplier_sku="MILK-1",
            product_name="Milk",
            pack_size=1,
            unit="l",
            currency="USD",
            price=5,
        )

        response = self.client.get(
            reverse("product-list"),
            {
                "supplier": active_supplier.id,
                "currency": "inr",
                "active": "true",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], expected.id)
        self.assertNotEqual(
            response.data["results"][0]["supplier"],
            inactive_supplier.id,
        )

    def test_api_search(self):
        supplier = Supplier.objects.create(name="Supplier", country_code="IN")
        Product.objects.create(
            supplier=supplier,
            supplier_sku="CHICKEN-1",
            product_name="Chicken Breast",
            pack_size=1,
            unit="kg",
            currency="INR",
            price=250,
        )
        Product.objects.create(
            supplier=supplier,
            supplier_sku="RICE-1",
            product_name="Rice",
            pack_size=1,
            unit="kg",
            currency="INR",
            price=100,
        )

        response = self.client.get(
            reverse("product-list"),
            {"search": "chicken"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["product_name"],
            "Chicken Breast",
        )

    def test_duplicate_handling(self):
        supplier = Supplier.objects.create(name="India Fresh", country_code="IN")
        Product.objects.create(
            supplier=supplier,
            supplier_sku="EXISTING",
            product_name="Original product",
            pack_size=1,
            unit="kg",
            currency="INR",
            price=100,
        )
        file = SimpleUploadedFile(
            "products.csv",
            (
                "supplier_name,country_code,supplier_sku,product_name,"
                "pack_size,unit,currency,price\n"
                "India Fresh,IN,EXISTING,Duplicate existing,1,kg,INR,100\n"
                "India Fresh,IN,NEW-1,New product,1,kg,INR,200\n"
                "India Fresh,IN,NEW-1,Duplicate in file,1,kg,INR,200\n"
            ).encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("csv-product-import"),
            {"file": file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_rows"], 3)
        self.assertEqual(response.data["invalid_rows"], 0)
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(Product.objects.filter(supplier_sku="NEW-1").count(), 1)
        self.assertEqual(Supplier.objects.count(), 1)

        existing = Product.objects.get(supplier_sku="EXISTING")
        self.assertEqual(existing.product_name, "Original product")
