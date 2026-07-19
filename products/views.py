import csv
import io
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product, Supplier
from .serializers import ProductSerializer


REQUIRED_CSV_COLUMNS = {
    "supplier_name",
    "country_code",
    "supplier_sku",
    "product_name",
    "pack_size",
    "unit",
    "currency",
    "price",
}

UNIT_ALIASES = {
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ml": "ml",
    "l": "l",
    "litre": "l",
    "litres": "l",
    "each": "each",
    "ea": "each",
    "piece": "each",
}


class ProductListAPIView(APIView):
    def get(self, request):
        products = Product.objects.all()
        return Response(ProductSerializer(products, many=True).data)


def cell(row, column):
    """Return a trimmed CSV value without failing on an empty cell."""
    return (row.get(column) or "").strip()


def validation_errors(exc):
    """Convert Django validation errors into JSON-friendly values."""
    return {
        field: [str(message) for message in messages]
        for field, messages in exc.message_dict.items()
    }


def is_ascii_alpha_code(value, length):
    """Check fixed-length country and currency codes."""
    return len(value) == length and value.isascii() and value.isalpha()


def validate_row(row):
    """Validate and normalize CSV input before creating model objects."""
    errors = {}

    supplier_name = cell(row, "supplier_name")
    country_code = cell(row, "country_code").upper()
    supplier_sku = cell(row, "supplier_sku")
    product_name = cell(row, "product_name")
    raw_unit = cell(row, "unit").lower()
    currency = cell(row, "currency").upper()

    if not supplier_name:
        errors["supplier_name"] = ["This field is required."]
    elif len(supplier_name) > 300:
        errors["supplier_name"] = ["Must not exceed 300 characters."]

    if not is_ascii_alpha_code(country_code, 2):
        errors["country_code"] = ["Must contain exactly two ASCII letters."]

    if not supplier_sku:
        errors["supplier_sku"] = ["This field is required."]
    elif len(supplier_sku) > 100:
        errors["supplier_sku"] = ["Must not exceed 100 characters."]

    if not product_name:
        errors["product_name"] = ["This field is required."]
    elif len(product_name) > 300:
        errors["product_name"] = ["Must not exceed 300 characters."]

    try:
        pack_size = int(cell(row, "pack_size"))
        if pack_size <= 0:
            errors["pack_size"] = ["Must be greater than zero."]
    except ValueError:
        pack_size = None
        errors["pack_size"] = ["Must be a whole number."]

    unit = UNIT_ALIASES.get(raw_unit)
    if unit is None:
        errors["unit"] = ["Supported units are g, kg, ml, l, and each."]

    if not currency:
        currency = "INR" if country_code == "IN" else "USD"
    elif not is_ascii_alpha_code(currency, 3):
        errors["currency"] = ["Must contain exactly three ASCII letters."]

    try:
        price = Decimal(cell(row, "price"))
        if not price.is_finite():
            errors["price"] = ["Must be a finite number."]
        elif price < 0:
            errors["price"] = ["Cannot be negative."]
        elif price.as_tuple().exponent < -4:
            errors["price"] = ["Must have at most four decimal places."]
        elif price > Decimal("999999.9999"):
            errors["price"] = ["Must not exceed 999999.9999."]
    except InvalidOperation:
        price = None
        errors["price"] = ["Must be a number."]

    if errors:
        raise ValidationError(errors)

    supplier = Supplier(
        name=supplier_name,
        country_code=country_code,
    )

    product = Product(
        supplier=supplier,
        supplier_sku=supplier_sku,
        product_name=product_name,
        pack_size=pack_size,
        unit=unit,
        currency=currency,
        price=price,
    )
    return supplier, product


def attach_suppliers(valid_rows):
    """Create or reuse suppliers and attach them to the valid rows."""
    supplier_cache = {}
    products_with_rows = []

    # Attach supplier object to product object after creating or reusing unique suppliers.
    for row_number, supplier, product in valid_rows:
        key = (supplier.name, supplier.country_code)
        if key not in supplier_cache:
            supplier_cache[key], _ = Supplier.objects.get_or_create(
                name=supplier.name,
                country_code=supplier.country_code,
            )
        product.supplier = supplier_cache[key]
        products_with_rows.append((row_number, product))

    return products_with_rows


def get_existing_keys(products_with_rows):
    """Fetch only the exact supplier/SKU pairs present in the import."""

    # Build a dictionary of supplier IDs to sets of SKUs for valid rows. This allows us to query only the exact pairs that exist in the import.
    skus_by_supplier = {}
    for _, product in products_with_rows:
        skus_by_supplier.setdefault(product.supplier_id, set()).add(
            product.supplier_sku
        )

    if not skus_by_supplier:
        return set()

    # Build a Q object that matches any of the exact supplier/SKU pairs in the import.
    exact_pairs = Q()
    for supplier_id, skus in skus_by_supplier.items():
        exact_pairs |= Q(supplier_id=supplier_id, supplier_sku__in=skus)

    # Return a set of (supplier_id, supplier_sku) tuples for existing products.
    return set(
        Product.objects.filter(exact_pairs).values_list(
            "supplier_id", "supplier_sku"
        )
    )


def filter_duplicates(products_with_rows):
    """Remove existing and repeated supplier/SKU combinations."""
    existing_keys = get_existing_keys(products_with_rows)
    seen_keys = set()
    products = []
    errors = []

    for row_number, product in products_with_rows:
        key = (product.supplier_id, product.supplier_sku)
        if key in existing_keys or key in seen_keys:
            errors.append(
                {
                    "row": row_number,
                    "errors": {
                        "supplier_sku": [
                            "SKU already exists for this supplier."
                        ]
                    },
                }
            )
            continue

        seen_keys.add(key)
        products.append(product)

    return products, errors


class ProductCSVImportAPIView(APIView):

    def post(self, request):
        csv_file = request.FILES.get("file")
        if not csv_file:
            return Response(
                {"error": "CSV file is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            content = csv_file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response(
                {"error": "CSV file must use UTF-8 encoding."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            reader = csv.DictReader(io.StringIO(content), strict=True)
            if not reader.fieldnames:
                return Response(
                    {"error": "CSV file is empty."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            missing = REQUIRED_CSV_COLUMNS - set(reader.fieldnames)
            if missing:
                return Response(
                    {
                        "error": "Required columns are missing.",
                        "missing_columns": sorted(missing),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Reading rows can raise csv.Error for malformed quoting.
            rows = list(reader)
        except csv.Error as exc:
            return Response(
                {"error": f"Invalid CSV format: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Pass 1: validate and normalize every supplier/product field.
        valid_rows = []
        errors = []

        for row_number, row in enumerate(rows, start=2):
            try:
                supplier, product = validate_row(row)
            except ValidationError as exc:
                errors.append(
                    {"row": row_number, "errors": validation_errors(exc)}
                )
                continue

            valid_rows.append((row_number, supplier, product))

        # Insert everything that passed both validation passes
        try:
            with transaction.atomic():
                # Pass 2: resolve suppliers, then reject duplicate supplier/SKU pairs.
                products_with_rows = attach_suppliers(valid_rows)
                valid_products, duplicate_errors = filter_duplicates(products_with_rows)
                errors.extend(duplicate_errors)

                Product.objects.bulk_create(
                    valid_products,
                    batch_size=1000,
                )

            return Response(
                {
                    "total_rows": len(rows),
                    "imported_rows": len(valid_products),
                    "invalid_rows": len(errors),
                    "errors": errors,
                },
                status=status.HTTP_200_OK,
            )
        except IntegrityError as exc:
            return Response(
                {
                    "error": "The import conflicted with data created by another request.",
                    "details": str(exc),
                },
                status=status.HTTP_409_CONFLICT,
            )
