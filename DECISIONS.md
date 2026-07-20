# Engineering Decisions

## Import Strategy

Request validation -> data constraints validation/normalization to get valid rows ->bulk create new/missing linked suppliers -> attach all suppliers to valid products -> bulk create all valid products -> duplicate/existing products skipped (idempotency)

### Batching

I made use of TextIO as generator for streaming csv data and yield one row at a time, so the uploaded file is not loaded completely into memory.
I validated each row, then inserted in bulk with `bulk_create()` for both suppliers and products. This keeps the number of database query executions low.
This approach supports the import requirements of 5000 rows.
Also splitted supplier lookups into chunks of 500 names to avoid exceeding database parameter limits.

I deliberately kept validation towards the input, separate from the data layer.
Each input data row is validated/normalized, then valid objects are prepared and then inserted in bulk.
1 trade-off is that valid model objects are retained in memory until validation finishes.

### Transactions

I used one transaction for both supplier and product inserts, using `transaction.atomic()`. It ensures database changes from that transaction are rolled back in case of any database error, for example rolling back newly created suppliers, without their products inserted.

Row validation happens before the transaction begins, which keeps the transaction short and avoids holding database locks while the CSV is being parsed.

I have kept request level validation such as file-level failures, missing request fields, invalid CSV syntax, or non-UTF-8 input reject before any further data validation/normalization or database inserts.

### Duplicate Handling

I applied database constraint `UniqueConstraint` on `(supplier, supplier_sku)` to identify unique products with no repeated SKU per supplier. It will ensure data consistency, data integrity. Even if two imports run concurrently, database constraint will ensure this.

Similarly, I have applied database constraint `UniqueConstraint` on `(name, country_code)` to identify unique suppliers.

Both supplier and product bulk inserts use `ignore_conflicts=True`. Therefore a SKU already stored for a supplier, or repeated within the same uploaded file, is skipped rather than inserted or used to overwrite existing data. This makes the import idempotent for duplicate keys and preserves the previously stored product.

### Validation Flow

Validation is performed independently for every data row:

1. The file is decoded as UTF-8, parsed in strict CSV mode, and checked for all required headers.
2. Text values are trimmed and appropriate codes are normalized to lowercase or uppercase. Supported unit aliases such as `kilograms` are converted to the canonical values `g`, `kg`, `ml`, `l`, or `each`.
3. Required fields and length limits are checked; `pack_size` must be a positive whole number; and `price` must be non-negative, within the database range, and have no more than four decimal places.
4. Country and currency codes are checked against the supported sets. A missing currency defaults to INR for an Indian supplier and USD otherwise.
5. A row with any errors is excluded and returned with its original CSV line number and field-specific messages. Other rows continue through validation.
6. Valid rows are linked to existing or newly bulk-created suppliers and then bulk-inserted. Model check constraints and uniqueness constraints provide a second layer of protection at the database level.

---

## Query Optimization

### `select_related` / `prefetch_related` Usage

I used `select_related("supplier")` on the product list and product detail querysets because `Product.supplier` is a single-valued foreign-key relation. `select_related` retrieves the product and its supplier with one SQL join and prevents an N+1 query pattern if supplier fields are accessed while serializing products. The current serializer exposes the supplier ID, which Django can read directly from `supplier_id`, so the join is not strictly required for the current response shape. I kept it on the queryset so supplier data can be exposed later without accidentally introducing per-product queries.

I did not use `prefetch_related` because no endpoint currently serializes a multi-valued reverse or many-to-many relationship. For example, if the supplier list later included its products, `prefetch_related("products")` would be the appropriate choice because it would fetch the products in a second query and join them in Python rather than multiplying supplier rows in SQL.

### Pagination Approach

I configured Django REST Framework's `PageNumberPagination` globally with a page size of 50. This kept list responses and serializer work bounded instead of loading the complete product or supplier table into one response.

Both list querysets use `order_by("id")` to provide deterministic ordering. This is important because offset/page-number pagination can otherwise return unstable or repeated results when the database does not guarantee row order.

### Filtering Strategy

I used `django-filter` with an explicit `ProductFilter` so supported filters are controlled and translated into database-level `WHERE` clauses before pagination:

- `supplier` filters directly on `supplier_id`, avoiding an unnecessary join for this condition and using the foreign-key index created by Django.
- `currency` uses a case-insensitive exact match so values such as `inr` and `INR` behave consistently. The field also has `db_index=True`.
- `active` filters through `supplier__active`, allowing clients to include only products belonging to active or inactive suppliers.
- Product-name search uses DRF's `SearchFilter` with `product_name`, which maps to a case-insensitive containment search.

---

## Scalability Considerations

### Supporting Larger Imports

For significantly larger files, I would process rows in bounded chunks so memory usage remains predictable regardless of file size.

I would store the upload in durable object storage and import it progressively. Some scheduled worker would read and validate a fixed number of rows at a time, resolve suppliers in bulk, and write products in batches. Validation errors would be written incrementally to a separate CSV or table rather than accumulated in the application memory.

### Async / Background Jobs

Large imports should not run for very long time out of an HTTP request because they can exceed web-server timeouts. I would move import execution to a background queue such as Celery or RQ.

If imports are scheduled or recurring, with multiple stages to incoming data, and require monitoring and audit history, Apache Airflow can also be used to run imports asynchronously.

### Retry Handling

I would use retries for transient failures such as temporary database connection issues, object storage service downtime. I can use exponential backoff, or maximum attempt count. I would use retry decorators to endpoints.

I would ensure critical database operations are idempotent, so that retries are safe.

Each batch would use its own short atomic transaction. This would help in executing long-running imports.

---

## Improvements With More Time

### Additional Validation

I would strengthen validation at both the request and data layers:

- Enforce an upload size limit and a maximum row count before allowing an import
  to consume excessive memory, CPU, or database capacity.
- Validate the file's declared content type and detect empty rows, unexpected columns, and
  duplicate headers explicitly.
- Define business rules for supplier-name matching so logically identical keys cannot be stored with
  inconsistent representations.
- Validate reasonable upper bounds for pack size and price based on the product
  domain.
- Add an explicit duplicate policy in the database layer rather than always using insert-only behavior.

I would keep database constraints as the final data-integrity layer even when the same rules are checked earlier for clearer API error messages.

### Monitoring and Logging

I could use Apache Airflow for proper monitoring and logging purpose at each step of a request workflow.

Monitoring metrics would include request/job duration, throughput, validation-failure rate, duplicate rate, database batch duration, external HTML-fetch failures, retry count.
Dashboards and alerts would focus on high error rates, idle jobs, growing queue latency, or abnormal import duration.

### Deployment Improvements

For production I would replace SQLite with PostgreSQL/MySQL, run Django behind a production WSGI/ASGI server, and use environment-based configuration for database credentials, `SECRET_KEY`, allowed hosts, CORS/CSRF policy, and secure-cookie settings. Static files and uploaded import files would be placed in appropriate static/object storage instead of the application container's local filesystem.

I would package the service in a reproducible container with pinned dependencies using Docker container orchestration.

Database migrations would run as a controlled release step, with backups
and a rollback plan.

### Testing Improvements

I would expand the current test suite with:

- Unit tests for every normalization and validation boundary, including blank values, Unicode, maximum lengths, decimal precision, non-finite numbers, missing or duplicate headers.
- Import integration tests covering multiple suppliers, duplicates within one file, duplicates already in the database, partial success, transaction rollback, and accurate response counts.
- Concurrency tests proving that simultaneous imports cannot violate supplier or product uniqueness and that retries remain idempotent.
- API tests for pagination boundaries, combined filters, invalid query values, case-insensitive search, inactive suppliers.