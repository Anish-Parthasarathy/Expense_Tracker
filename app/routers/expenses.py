"""
routers/expenses.py
-------------------
CRUD routes for expenses PLUS the monthly summary endpoint.

Pagination design:
  - Default: skip=0, limit=20
  - Hard cap: limit is silently capped at 100 to prevent DB overload.
    (A 422 error on over-limit would force clients to adjust; a silent cap
     is friendlier for read-only queries.)

Filters: category_id, start_date, end_date can be combined freely.

Summary endpoint:
  Uses SQLAlchemy's func.sum + group_by to aggregate *in the database*,
  not in Python, so large datasets stay fast.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(tags=["expenses"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_expense_or_404(expense_id: int, db: Session) -> models.Expense:
    """Fetch an expense by PK or raise 404. Used in get/update/delete."""
    expense = db.get(models.Expense, expense_id)
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Expense {expense_id} not found.",
        )
    return expense


# ---------------------------------------------------------------------------
# Expense CRUD
# ---------------------------------------------------------------------------

@router.post(
    "/expenses",
    response_model=schemas.ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new expense",
)
def create_expense(payload: schemas.ExpenseCreate, db: Session = Depends(get_db)):
    """
    Create an expense.

    Validates that the referenced category exists before inserting, so the
    caller gets a 404 rather than a cryptic FK-violation 500.
    """
    # Ensure the category exists
    if not db.get(models.Category, payload.category_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category {payload.category_id} not found.",
        )

    expense = models.Expense(**payload.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.get(
    "/expenses",
    response_model=list[schemas.ExpenseResponse],
    summary="List expenses with optional filters and pagination",
)
def list_expenses(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records returned (hard cap: 100)"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    start_date: Optional[date] = Query(None, description="Include expenses on/after this date"),
    end_date: Optional[date] = Query(None, description="Include expenses on/before this date"),
    db: Session = Depends(get_db),
):
    """
    List expenses.

    `limit` is bound to [1, 100] by FastAPI's Query validation, so clients
    that pass limit=500 receive a 422 with a clear message instead of a
    silently capped value.
    """
    query = db.query(models.Expense)

    if category_id is not None:
        query = query.filter(models.Expense.category_id == category_id)
    if start_date:
        query = query.filter(models.Expense.expense_date >= start_date)
    if end_date:
        query = query.filter(models.Expense.expense_date <= end_date)

    return (
        query.order_by(models.Expense.expense_date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get(
    "/expense/{expense_id}",
    response_model=schemas.ExpenseResponse,
    summary="Get a single expense by ID",
)
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    """Return a single expense or 404 if it doesn't exist."""
    return _get_expense_or_404(expense_id, db)


@router.put(
    "/expense/{expense_id}",
    response_model=schemas.ExpenseResponse,
    summary="Update an expense",
)
def update_expense(
    expense_id: int,
    payload: schemas.ExpenseUpdate,
    db: Session = Depends(get_db),
):
    """
    Update an expense (full or partial).

    Only fields explicitly provided in the JSON body are updated.
    `model_dump(exclude_unset=True)` gives us only the keys the caller sent,
    so omitting a field in the payload leaves it unchanged.
    """
    expense = _get_expense_or_404(expense_id, db)

    updates = payload.model_dump(exclude_unset=True)

    # If category_id is being changed, validate the new category exists
    if "category_id" in updates and not db.get(models.Category, updates["category_id"]):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category {updates['category_id']} not found.",
        )

    for field, value in updates.items():
        setattr(expense, field, value)

    db.commit()
    db.refresh(expense)
    return expense


@router.delete(
    "/expense/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an expense",
)
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    """Delete an expense by ID, or 404 if it doesn't exist."""
    expense = _get_expense_or_404(expense_id, db)
    db.delete(expense)
    db.commit()


# ---------------------------------------------------------------------------
# Summary endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/summary",
    response_model=schemas.SummaryResponse,
    summary="Monthly spending summary grouped by category",
)
def get_summary(
    month: str = Query(..., description="Month in YYYY-MM format, e.g. 2026-09"),
    db: Session = Depends(get_db),
):
    """
    Return total spending per category for the given month, plus a grand total.

    Aggregation is done entirely in SQL (func.sum + group_by) so the DB
    does the heavy lifting regardless of how many expense rows exist.

    Month format is validated manually here because `date` parsing would
    strip the day component; we want exactly YYYY-MM.
    """
    # --- Validate month format ---
    import re
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Invalid month format '{month}'. "
                "Expected YYYY-MM, e.g. '2026-09'."
            ),
        )

    year, mon = map(int, month.split("-"))

    # --- SQL aggregation query ---
    # We JOIN expenses → categories and aggregate by category name.
    # Using func.sum gives us a single DB round-trip instead of loading all
    # expense rows and summing in Python.
    rows = (
        db.query(
            models.Category.name.label("category"),
            func.sum(models.Expense.amount).label("total"),
        )
        .join(models.Expense, models.Expense.category_id == models.Category.id)
        .filter(
            func.extract("year", models.Expense.expense_date) == year,
            func.extract("month", models.Expense.expense_date) == mon,
        )
        .group_by(models.Category.name)
        .order_by(models.Category.name)
        .all()
    )

    by_category = [
        schemas.CategorySummary(category=row.category, total=Decimal(str(row.total)))
        for row in rows
    ]

    grand_total = sum((item.total for item in by_category), Decimal("0"))

    return schemas.SummaryResponse(
        month=month,
        total=grand_total,
        by_category=by_category,
    )
