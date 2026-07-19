import csv
import io
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from ..models import Product, Supplier


REQUIRED_COLUMNS = {
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

SUPPLIER_QUERY_CHUNK_SIZE = 500

SUPPORTED_COUNTRY_CODES = frozenset({"NZ", "AU", "IN", "US"})
SUPPORTED_CURRENCY_CODES = frozenset({"NZD", "AUD", "INR", "USD"})


class CSVImportError(Exception):
    def __init__(self, message, **details):
        super().__init__(message)
        self.payload = {"error": message, **details}


def cell(row, column):
    return (row.get(column) or "").strip()


def format_validation_errors(exc):
    return {
        field: [str(message) for message in messages]
        for field, messages in exc.message_dict.items()
    }


def iter_csv_rows(csv_file):
    """Yield CSV rows without loading the complete upload into memory."""
    text_stream = io.TextIOWrapper(
        csv_file.file,
        encoding="utf-8-sig",
        newline="",
    )

    try:
        reader = csv.DictReader(text_stream, strict=True)
        if not reader.fieldnames:
            raise CSVImportError("CSV file is empty.")

        missing = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing:
            raise CSVImportError(
                "Required columns are missing.",
                missing_columns=sorted(missing),
            )

        yield from reader
    except UnicodeDecodeError as exc:
        raise CSVImportError("CSV file must use UTF-8 encoding.") from exc
    except csv.Error as exc:
        raise CSVImportError(f"Invalid CSV format: {exc}") from exc
    finally:
        # Do not let TextIOWrapper close Django's uploaded file.
        text_stream.detach()


def validate_row(row):
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

    if country_code not in SUPPORTED_COUNTRY_CODES:
        errors["country_code"] = [
            "Supported country codes are NZ, AU, IN, and US."
        ]

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
    elif currency not in SUPPORTED_CURRENCY_CODES:
        errors["currency"] = [
            "Supported currency codes are NZD, AUD, INR, and USD."
        ]

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

    supplier = Supplier(name=supplier_name, country_code=country_code)
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


def supplier_key(supplier):
    return supplier.name, supplier.country_code


def fetch_suppliers(keys):
    names_by_country = {}
    for name, country_code in keys:
        names_by_country.setdefault(country_code, set()).add(name)

    suppliers = {}
    for country_code, names in names_by_country.items():
        names = list(names)
        for start in range(0, len(names), SUPPLIER_QUERY_CHUNK_SIZE):
            name_chunk = names[start : start + SUPPLIER_QUERY_CHUNK_SIZE]
            for supplier in Supplier.objects.filter(
                country_code=country_code,
                name__in=name_chunk,
            ):
                suppliers[supplier_key(supplier)] = supplier

    return suppliers


def attach_suppliers(valid_rows):
    # Keep one supplier candidate for each unique name/country pair.
    candidates = {
        (supplier.name, supplier.country_code): supplier
        for _, supplier, _ in valid_rows
    }

    # Find suppliers that already exist.
    existing_suppliers = fetch_suppliers(candidates.keys())

    # Select only suppliers missing from the database.
    missing_suppliers = [
        supplier
        for key, supplier in candidates.items()
        if key not in existing_suppliers
    ]

    # Insert all missing suppliers together.
    if missing_suppliers:
        Supplier.objects.bulk_create(
            missing_suppliers,
            batch_size=1000,
            ignore_conflicts=True,
        )

        # Reload suppliers to obtain IDs and handle concurrent inserts.
        saved_suppliers = fetch_suppliers(candidates.keys())
    else:
        saved_suppliers = existing_suppliers

    # Attach saved suppliers to their products.
    products = []
    for _, supplier, product in valid_rows:
        key = (supplier.name, supplier.country_code)
        product.supplier = saved_suppliers[key]
        products.append(product)

    return products


def import_products_csv(csv_file):
    valid_rows = []
    errors = []
    total_rows = 0

    for row_number, row in enumerate(iter_csv_rows(csv_file), start=2):
        total_rows += 1
        try:
            supplier, product = validate_row(row)
            valid_rows.append((row_number, supplier, product))
        except ValidationError as exc:
            errors.append(
                {"row": row_number, "errors": format_validation_errors(exc)}
            )

    with transaction.atomic():
        # Insert suppliers and attach them to products.
        products = attach_suppliers(valid_rows)
        Product.objects.bulk_create(
            products,
            batch_size=1000,
            ignore_conflicts=True,
        )

    return {
        "total_rows": total_rows,
        "accepted_rows": len(products),
        "invalid_rows": len(errors),
        "validation_errors": errors,
        "message": "Duplicate supplier/SKU rows were skipped.",
    }
