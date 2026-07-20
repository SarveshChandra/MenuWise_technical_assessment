# Engineering Decisions

## Import Strategy

### Batching

Made use of TextIO generator for streaming csv data import and yield one row at a time, so the uploaded file is not loaded complete into in-memory.
Validated rows are collected and written with
`bulk_create()` for both suppliers and products. This keeps
the number of database query executions low.
This approach supports 5000 row import requirements.
Supplier lookups are also split into chunks of 500 names to
avoid exceeding database parameter limits.

I deliberately kept validation separate from the data layer towards the input.
Each input data row is validated/normalized, then valid objects are inserted in bulk.
1 trade-off is that valid model objects are retained in memory until validation finishes.

### Transactions

Supplier resolution/creation and product insertion run inside one
`transaction.atomic()` block. This prevents a database failure during the write
phase from leaving a partially persisted import, such as newly created suppliers
without their products. Row validation happens before the transaction begins,
which keeps the transaction short and avoids holding database locks while the
CSV is parsed.

Invalid business-data rows do not roll back the import. They are rejected before
the transaction, reported to the caller, and the remaining valid rows are saved
together. File-level failures such as missing columns, invalid CSV syntax, or
non-UTF-8 input reject the request before any database writes occur.

### Duplicate Handling

A product is identified by `(supplier, supplier_sku)`. That rule is enforced by
a database `UniqueConstraint`, making the database the final authority even if
two imports run concurrently. Suppliers are similarly unique by normalized
`(name, country_code)`.

Both supplier and product bulk inserts use `ignore_conflicts=True`. Therefore a
SKU already stored for a supplier, or repeated within the same uploaded file, is
skipped rather than inserted or used to overwrite existing data. This makes the
import idempotent for duplicate keys and preserves the previously stored product.
It is intentionally an insert-only policy; price catalogue updates would require
an explicit upsert/versioning policy rather than silently changing records.

### Validation Flow

Validation is performed independently for every data row:

1. The file is decoded as UTF-8 (including UTF-8 BOM support), parsed in strict
   CSV mode, and checked for all required headers.
2. Text values are trimmed and appropriate codes are normalized to lowercase or
   uppercase. Supported unit aliases such as `kilograms` are converted to the
   canonical values `g`, `kg`, `ml`, `l`, or `each`.
3. Required fields and length limits are checked; `pack_size` must be a positive
   whole number; and `price` must be finite, non-negative, within the database
   range, and have no more than four decimal places.
4. Country and currency codes are checked against the supported sets. A missing
   currency defaults to INR for an Indian supplier and USD otherwise.
5. A row with any errors is excluded and returned with its original CSV line
   number and field-specific messages. Other rows continue through validation.
6. Valid rows are linked to existing or newly bulk-created suppliers and then
   bulk-inserted. Model check constraints and uniqueness constraints provide a
   second layer of protection at the database boundary.

This flow gives clients actionable feedback for every invalid row in one request
while safely importing all independently valid data.

---

## Query Optimization

Explain:
- select_related / prefetch_related usage
- pagination approach
- filtering strategy

---

## Scalability Considerations

Explain:
- how you would support larger imports
- async/background jobs
- retry handling

---

## Improvements With More Time

Explain:
- additional validation
- monitoring/logging
- deployment improvements
- testing improvements
