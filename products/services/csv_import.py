import csv
import io
from django.core.exceptions import ValidationError
from django.db import transaction
from ..models import Product
from .import_helpers import (
    attach_suppliers,
    format_validation_errors,
    validate_row,
)

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


class CSVImportError(Exception):
    def __init__(self, message, **details):
        super().__init__(message)
        self.payload = {"error": message, **details}


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
        text_stream.detach()


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