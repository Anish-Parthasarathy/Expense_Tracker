"""
tests/test_api.py
-----------------
Pytest test suite for the Expense Tracker API.

Strategy:
  - Uses FastAPI's TestClient which runs the app in-process (no server needed).
  - Overrides the `get_db` dependency to use a *separate* in-memory SQLite
    database so tests never touch your real PostgreSQL instance and can run
    anywhere without extra setup.
  - Each test function gets a fresh database via the `db_session` and `client`
    fixtures, which roll back or drop/recreate tables between tests.

SQLite vs PostgreSQL note:
  SQLite doesn't support EXTRACT() the same way PostgreSQL does.
  For the summary tests we import and monkeypatch the dependency; the
  filter logic is tested end-to-end, and the SQL aggregation correctness
  is validated against the known seeded data.
"""

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db

# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------

# Use a single shared in-memory SQLite DB for the whole test session.
# StaticPool is required when using in-memory SQLite with multiple threads
# (TestClient spawns one), ensuring all connections share the same DB state.
SQLITE_URL = "sqlite://"

engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Enable SQLite foreign-key enforcement (off by default in SQLite)
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function", autouse=True)
def reset_db():
    """
    Create all tables before each test and drop them after.
    This gives every test a completely clean slate.
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    """
    Return a TestClient whose requests use the in-memory SQLite DB.

    Dependency override: FastAPI lets us swap out `get_db` for a test
    version that points at our test database, without touching app code.
    """
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    # Clean up the override after each test
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_category(client, name="Food"):
    """Create a category and return the response JSON."""
    resp = client.post("/categories/", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_expense(client, category_id, amount="50.00", expense_date="2026-09-15", description=None):
    """Create an expense and return the response JSON."""
    payload = {
        "amount": amount,
        "expense_date": expense_date,
        "category_id": category_id,
    }
    if description:
        payload["description"] = description
    resp = client.post("/expenses", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Category tests
# ---------------------------------------------------------------------------

class TestCategories:
    def test_create_category(self, client):
        resp = client.post("/categories/", json={"name": "Transport"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Transport"
        assert "id" in data
        assert "created_at" in data

    def test_list_categories(self, client):
        make_category(client, "Food")
        make_category(client, "Utilities")
        resp = client.get("/categories/")
        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()]
        # Should be returned alphabetically
        assert names == sorted(names)
        assert "Food" in names
        assert "Utilities" in names

    def test_duplicate_category_returns_409(self, client):
        """Creating two categories with the same name must return 409, not 500."""
        make_category(client, "Entertainment")
        resp = client.post("/categories/", json={"name": "Entertainment"})
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_delete_category(self, client):
        cat = make_category(client, "OneOff")
        resp = client.delete(f"/categories/{cat['id']}")
        assert resp.status_code == 204

    def test_delete_category_with_expenses_returns_409(self, client):
        """Deleting a category that still has expenses must return 409."""
        cat = make_category(client, "Groceries")
        make_expense(client, cat["id"])
        resp = client.delete(f"/categories/{cat['id']}")
        assert resp.status_code == 409
        assert "expense" in resp.json()["detail"].lower()

    def test_delete_nonexistent_category_returns_404(self, client):
        resp = client.delete("/categories/9999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Expense tests
# ---------------------------------------------------------------------------

class TestExpenses:
    def test_create_expense(self, client):
        cat = make_category(client)
        resp = client.post(
            "/expenses",
            json={
                "amount": "120.50",
                "expense_date": "2026-09-01",
                "category_id": cat["id"],
                "description": "Weekly groceries",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["amount"] == "120.50"
        assert data["category"]["name"] == "Food"
        assert data["description"] == "Weekly groceries"

    def test_create_expense_invalid_amount(self, client):
        """Amount ≤ 0 must be rejected by Pydantic with 422."""
        cat = make_category(client)
        resp = client.post(
            "/expenses",
            json={"amount": "-10.00", "expense_date": "2026-09-01", "category_id": cat["id"]},
        )
        assert resp.status_code == 422

    def test_create_expense_missing_category_returns_404(self, client):
        resp = client.post(
            "/expenses",
            json={"amount": "10.00", "expense_date": "2026-09-01", "category_id": 9999},
        )
        assert resp.status_code == 404

    def test_get_expense(self, client):
        cat = make_category(client)
        exp = make_expense(client, cat["id"], amount="75.00")
        resp = client.get(f"/expense/{exp['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == exp["id"]

    def test_get_nonexistent_expense_returns_404(self, client):
        resp = client.get("/expense/9999")
        assert resp.status_code == 404

    def test_update_expense(self, client):
        cat = make_category(client)
        exp = make_expense(client, cat["id"], amount="30.00")
        resp = client.put(
            f"/expense/{exp['id']}",
            json={"amount": "45.99", "description": "Updated note"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["amount"] == "45.99"
        assert data["description"] == "Updated note"

    def test_delete_expense(self, client):
        cat = make_category(client)
        exp = make_expense(client, cat["id"])
        resp = client.delete(f"/expense/{exp['id']}")
        assert resp.status_code == 204
        # Confirm it's gone
        assert client.get(f"/expense/{exp['id']}").status_code == 404

    # --- Pagination tests ---

    def test_pagination_default(self, client):
        cat = make_category(client)
        for i in range(5):
            make_expense(client, cat["id"], amount=f"{10 + i}.00")
        resp = client.get("/expenses")
        assert resp.status_code == 200
        assert len(resp.json()) == 5

    def test_pagination_limit_cap(self, client):
        """
        FastAPI validates limit ≤ 100 via Query(le=100).
        Sending limit=200 should return 422, not 200 with 200 results.
        """
        resp = client.get("/expenses?limit=200")
        assert resp.status_code == 422

    def test_pagination_skip(self, client):
        cat = make_category(client)
        for i in range(5):
            make_expense(client, cat["id"], amount=f"{i + 1}0.00")
        resp = client.get("/expenses?skip=3&limit=10")
        assert resp.status_code == 200
        assert len(resp.json()) == 2  # 5 total, skip 3 → 2 remain

    def test_filter_by_category(self, client):
        cat_food = make_category(client, "Food")
        cat_transport = make_category(client, "Transport")
        make_expense(client, cat_food["id"], amount="20.00")
        make_expense(client, cat_transport["id"], amount="15.00")
        resp = client.get(f"/expenses?category_id={cat_food['id']}")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["category_id"] == cat_food["id"]


# ---------------------------------------------------------------------------
# Summary tests
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_two_categories(self, client):
        """
        Seed expenses across two categories for September 2026 and verify
        the summary returns correct per-category and grand totals.
        """
        cat_food = make_category(client, "Food")
        cat_rent = make_category(client, "Rent")

        # Food: 200.00 + 500.00 = 700.00
        make_expense(client, cat_food["id"], amount="200.00", expense_date="2026-09-05")
        make_expense(client, cat_food["id"], amount="500.00", expense_date="2026-09-20")

        # Rent: 1500.00
        make_expense(client, cat_rent["id"], amount="1500.00", expense_date="2026-09-01")

        resp = client.get("/summary?month=2026-09")
        assert resp.status_code == 200
        data = resp.json()

        assert data["month"] == "2026-09"

        by_cat = {item["category"]: Decimal(item["total"]) for item in data["by_category"]}
        assert by_cat["Food"] == Decimal("700.00")
        assert by_cat["Rent"] == Decimal("1500.00")
        assert Decimal(data["total"]) == Decimal("2200.00")

    def test_summary_excludes_other_months(self, client):
        """Expenses outside the queried month must not appear in the total."""
        cat = make_category(client, "Misc")
        make_expense(client, cat["id"], amount="999.00", expense_date="2026-08-31")  # August
        make_expense(client, cat["id"], amount="100.00", expense_date="2026-09-01")  # September

        resp = client.get("/summary?month=2026-09")
        assert resp.status_code == 200
        assert Decimal(resp.json()["total"]) == Decimal("100.00")

    def test_summary_empty_month(self, client):
        """A month with no expenses should return total=0 and empty by_category."""
        resp = client.get("/summary?month=2025-01")
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(data["total"]) == Decimal("0")
        assert data["by_category"] == []

    def test_summary_invalid_month_format(self, client):
        """Invalid month string should return 422 with a clear message."""
        for bad in ["2026-9", "09-2026", "2026/09", "September"]:
            resp = client.get(f"/summary?month={bad}")
            assert resp.status_code == 422, f"Expected 422 for month='{bad}', got {resp.status_code}"
