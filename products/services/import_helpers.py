from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from ..models import Product, Supplier

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

SUPPORTED_COUNTRY_CODES = frozenset({"NZ", "AU", "IN", "US"})
SUPPORTED_CURRENCY_CODES = frozenset({"NZD", "AUD", "INR", "USD"})
SUPPLIER_QUERY_CHUNK_SIZE = 500


def cell(row, column):
    return (row.get(column) or "").strip()


def format_validation_errors(exc):
    return {
        field: [str(message) for message in messages]
        for field, messages in exc.message_dict.items()
    }


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

    # Fetch suppliers in chunks to avoid hitting database query limits
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
    candidates = {
        (supplier.name, supplier.country_code): supplier
        for _, supplier, _ in valid_rows
    }
    existing_suppliers = fetch_suppliers(candidates.keys())
    missing_suppliers = [
        supplier
        for key, supplier in candidates.items()
        if key not in existing_suppliers
    ]

    if missing_suppliers:
        Supplier.objects.bulk_create(
            missing_suppliers,
            batch_size=1000,
            ignore_conflicts=True,
        )
        saved_suppliers = fetch_suppliers(candidates.keys())
    else:
        saved_suppliers = existing_suppliers

    products = []
    for _, supplier, product in valid_rows:
        product.supplier = saved_suppliers[supplier_key(supplier)]
        products.append(product)

    return products
