# Expense Tracker API

A clean, well-commented FastAPI backend for tracking personal expenses. Built as a learning project to demonstrate **FastAPI**, **SQLAlchemy 2.0**, **Pydantic v2**, and **Alembic** working together against PostgreSQL.

---

## Project Structure

```
├── app/
│   ├── main.py          # App factory – router wiring only
│   ├── database.py      # Engine, SessionLocal, Base, get_db dependency
│   ├── models.py        # SQLAlchemy ORM models (Category, Expense)
│   ├── schemas.py       # Pydantic v2 schemas (Create / Update / Response)
│   ├── routers/
│   │   ├── categories.py
│   │   └── expenses.py  # Also contains the /summary endpoint
│   └── tests/
│       └── test_api.py  # Full pytest suite (in-memory SQLite)
├── alembic/             # DB migration scaffold
├── alembic.ini
├── .env                 # DATABASE_URL (git-ignored)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Clone and create a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure the database

Edit `.env` and set your PostgreSQL connection string:

```
DATABASE_URL=postgresql://YOUR_USER:YOUR_PASSWORD@localhost:5432/expense_db
```

Create the target database first if it doesn't exist:

```bash
psql -U postgres -c "CREATE DATABASE expense_db;"
```

### 4. Run migrations

```bash
# Generate the first migration from the ORM models
alembic revision --autogenerate -m "initial schema"

# Apply it to the database
alembic upgrade head
```

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

The API is now live at **http://127.0.0.1:8000**.  
Interactive docs: **http://127.0.0.1:8000/docs**

---

## Running Tests

Tests use an **in-memory SQLite** database — no PostgreSQL connection required.

```bash
pytest app/tests/ -v
```

---

## API Reference & curl Examples

### Categories

**Create a category**
```bash
curl -s -X POST http://localhost:8000/categories/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Food"}' | python -m json.tool
```

**List all categories**
```bash
curl -s http://localhost:8000/categories/ | python -m json.tool
```

**Delete a category** (returns 204 No Content)
```bash
curl -s -X DELETE http://localhost:8000/categories/1
```

**Duplicate name → 409**
```bash
curl -s -X POST http://localhost:8000/categories/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Food"}'
# {"detail":"Category 'Food' already exists."}
```

---

### Expenses

**Create an expense**
```bash
curl -s -X POST http://localhost:8000/expenses \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "120.50",
    "description": "Weekly groceries",
    "expense_date": "2026-09-15",
    "category_id": 1
  }' | python -m json.tool
```

**List expenses (with pagination and filters)**
```bash
# Default (first 20, newest first)
curl -s "http://localhost:8000/expenses" | python -m json.tool

# Page 2 of results, 10 at a time
curl -s "http://localhost:8000/expenses?skip=10&limit=10" | python -m json.tool

# Filter by category and date range
curl -s "http://localhost:8000/expenses?category_id=1&start_date=2026-09-01&end_date=2026-09-30" | python -m json.tool
```

**Get a single expense**
```bash
curl -s http://localhost:8000/expense/1 | python -m json.tool
```

**Update an expense** (partial update – only send fields you want to change)
```bash
curl -s -X PUT http://localhost:8000/expense/1 \
  -H "Content-Type: application/json" \
  -d '{"amount": "99.99", "description": "Updated note"}' | python -m json.tool
```

**Delete an expense** (returns 204 No Content)
```bash
curl -s -X DELETE http://localhost:8000/expense/1
```

---

### Monthly Summary

```bash
# Total per category for September 2026
curl -s "http://localhost:8000/summary?month=2026-09" | python -m json.tool
```

**Example response:**
```json
{
  "month": "2026-09",
  "total": "5400.00",
  "by_category": [
    {"category": "Food", "total": "3200.00"},
    {"category": "Transport", "total": "2200.00"}
  ]
}
```

**Invalid format → 422**
```bash
curl -s "http://localhost:8000/summary?month=September"
# {"detail":"Invalid month format 'September'. Expected YYYY-MM, e.g. '2026-09'."}
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Separate Create/Update/Response schemas | Keeps validation intent explicit; avoids leaking server fields into create payloads |
| `Decimal` / `Numeric(10,2)` for amounts | No floating-point rounding errors in financial data |
| `exclude_unset=True` in PUT handler | Allows partial updates without requiring all fields |
| 409 before FK violation on delete | Converts opaque DB errors into user-friendly conflict messages |
| SQL aggregation in `/summary` | `func.sum` + `group_by` keeps the query O(1) in Python regardless of row count |
| `pool_pre_ping=True` on engine | Prevents stale-connection errors on long-running or restarted services |
| In-memory SQLite for tests | Tests run anywhere with no DB setup; `StaticPool` ensures threads share the same DB state |
