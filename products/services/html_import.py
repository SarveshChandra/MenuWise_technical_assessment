from django.core.exceptions import ValidationError
from django.db import transaction
import requests
from bs4 import BeautifulSoup
from ..models import Product
from .import_helpers import (
    attach_suppliers,
    format_validation_errors,
    validate_row,
)

REQUIRED_TABLE_COLUMNS = {"item", "sku", "pack", "unit", "price"}


class HTMLImportError(Exception):
    pass


def fetch_html(url):
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTMLImportError(f"Could not fetch supplier page: {exc}") from exc
    return response.text


def parse_price_table(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise HTMLImportError("Supplier page does not contain a table.")

    table_rows = table.find_all("tr")
    if not table_rows:
        raise HTMLImportError("Supplier table is empty.")

    headers = [
        cell.get_text(strip=True).lower()
        for cell in table_rows[0].find_all(["th", "td"])
    ]
    missing = REQUIRED_TABLE_COLUMNS - set(headers)
    if missing:
        raise HTMLImportError(
            f"Supplier table is missing columns: {', '.join(sorted(missing))}."
        )

    parsed_rows = []
    for row_number, table_row in enumerate(table_rows[1:], start=2):
        values = [
            cell.get_text(strip=True)
            for cell in table_row.find_all(["th", "td"])
        ]
        if not values:
            continue

        parsed_rows.append((row_number, dict(zip(headers, values))))

    return parsed_rows


def import_products_html(url, supplier_name, country_code, currency=""):
    table_rows = parse_price_table(fetch_html(url))
    valid_rows = []
    errors = []

    for row_number, table_row in table_rows:
        row = {
            "supplier_name": supplier_name,
            "country_code": country_code,
            "supplier_sku": table_row.get("sku", ""),
            "product_name": table_row.get("item", ""),
            "pack_size": table_row.get("pack", ""),
            "unit": table_row.get("unit", ""),
            "currency": currency,
            "price": table_row.get("price", ""),
        }

        try:
            supplier, product = validate_row(row)
            valid_rows.append((row_number, supplier, product))
        except ValidationError as exc:
            errors.append(
                {"row": row_number, "errors": format_validation_errors(exc)}
            )

    with transaction.atomic():
        products = attach_suppliers(valid_rows)
        Product.objects.bulk_create(
            products,
            batch_size=1000,
            ignore_conflicts=True,
        )

    return {
        "total_rows": len(table_rows),
        "accepted_rows": len(products),
        "invalid_rows": len(errors),
        "validation_errors": errors,
        "message": "Duplicate supplier/SKU rows were skipped.",
    }