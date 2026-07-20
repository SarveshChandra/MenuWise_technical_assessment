# MenuWise Python Backend Engineering Challenge

## Steps
  1. Project setup

  brew install python
  python3 —version
  brew install git
  mkdir -p MenuWise_technical_assessment
  Move starter files like requirements.txt to created directory

  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install —upgrade pip
  vim requirements.txt (remove pandas)
  pip install -r requirements.txt
  pip list

  django-admin startproject config .
  python manage.py startapp products
  vim settings.py
  (Add ‘rest_framework’, ‘django_filters’, ‘products’ to INSTALLED_APPS)
  python manage.py migrate (initialise the database)
  python manage.py createsuperuser
  (sarveshchandra, sarvesh071191@gmail.com, sarvesh@products)

  python manage.py runserver
  127.0.0.1:8000
  127.0.0.1:8000/admin

  2. Github setup
  https://github.com/SarveshChandra/MenuWise_technical_assessment

  git init
  add .gitignore
  git add .
  git status
  git commit -m “message for commit”
  git branch -M main
  git remote add origin https://github.com/SarveshChandra/MenuWise_technical_assessment.git
  git remote -v
  git push -u origin main

  3. CSV import endpoint command
  curl -X POST \            
    -F "file=@samples/sample_products.csv" \
    http://127.0.0.1:8000/api/products/import/csv/

  4. HTML scraper import endpoint commands
  python3 -m http.server 8001 --directory samples                      

  curl -X POST \
    -H "Content-Type: application/json" \
    -d '{
      "url": "http://127.0.0.1:8001/supplier_price_table.html",
      "supplier_name": "Sample Supplier",
      "country_code": "IN",
      "currency": "INR"
    }' \
    http://127.0.0.1:8000/api/products/import/html/

  5. Tests
  python manage.py test products
  python manage.py test products -v 2
  python manage.py test products.tests.ProductTests.test_model_validation

## Overview

Thank you for your interest in joining MenuWise.

This challenge is designed to evaluate how you think about backend engineering, data handling, APIs, architecture, and code quality in a real-world SaaS environment.

Please spend no more than **4 hours** on this challenge.

We are evaluating:
- Engineering judgment
- Backend architecture
- Data modelling
- API design
- Validation and error handling
- Code quality
- Performance awareness
- Communication

---

# Scenario

MenuWise aggregates ingredient and supplier pricing data from multiple sources.

Supplier datasets are often messy:
- inconsistent product naming
- duplicate SKUs
- missing pricing
- invalid pack sizes
- incorrect currencies
- inconsistent units

Your task is to build a small backend service that imports, validates, stores, and exposes supplier product pricing data.

---

# Technical Requirements

Use:
- Python 3.11+
- Django
- Django REST Framework

You may additionally use:
- Celery
- Pandas
- Requests
- BeautifulSoup
- Playwright
- pytest
- factory_boy
- Docker

Avoid excessive frameworks or unnecessary complexity.

---

# Core Tasks

## 1. Create the Data Model

Create models for:

### Supplier
Fields:
- name
- country_code
- active
- created_at

### Product
Fields:
- supplier
- supplier_sku
- product_name
- pack_size
- unit
- currency
- price
- imported_at

### Validation Rules
- supplier_sku must be unique per supplier
- price cannot be negative
- pack_size must be greater than zero
- unit must be normalized to:
  - g
  - kg
  - ml
  - l
  - each

If currency is missing:
- default to INR when supplier country_code = IN
- otherwise default to USD

---

# 2. CSV Import Endpoint

Create an endpoint to import CSV data.

Requirements:
- validate rows
- skip invalid rows safely
- return validation errors
- avoid duplicate inserts
- support importing at least 5,000 rows efficiently

Document your decisions.

---

# 3. Supplier API

Build REST endpoints for:

## GET /products
Features:
- pagination
- filtering by supplier
- filtering by currency
- filtering by active suppliers
- search by product_name

## GET /products/{id}

## GET /suppliers

Use efficient query handling.

---

# 4. Django Admin

Configure Django Admin for:
- Supplier
- Product

Requirements:
- searchable product list
- filtering
- useful list displays
- import visibility

---

# 5. Basic Scraping Task

Create a small importer that extracts supplier pricing data from:
- either a provided HTML table
- or a public webpage

Requirements:
- parse rows
- normalize units
- validate data
- store products

You may use:
- Requests + BeautifulSoup
- Playwright
- Scrapy

---

# 6. Tests

Add tests for:
- model validation
- CSV import
- API filtering/search
- duplicate handling

---

# 7. Documentation

Include:
- README.md
- DECISIONS.md

DECISIONS.md should explain:
- import strategy
- validation approach
- query optimization decisions
- scalability considerations
- what you would improve with more time

---

# Submission

Provide:
- Git repository link
- README.md
- DECISIONS.md

---

# Evaluation Criteria

| Area | Weight |
|---|---:|
| Django/API implementation | 25% |
| Import/ETL correctness | 20% |
| Query performance | 15% |
| Tests | 20% |
| Code quality | 10% |
| Documentation & communication | 10% |