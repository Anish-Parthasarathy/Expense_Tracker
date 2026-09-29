"""
schemas.py
----------
Pydantic v2 schemas used for request validation and response serialisation.

Design decision: we use *three* separate schema classes per resource
(Create, Update, Response) rather than one "mega-schema" so that:
  - Create schemas can have all required fields.
  - Update schemas can make every field Optional for PATCH-style behaviour.
  - Response schemas can include server-generated fields (id, created_at)
    without leaking them into create/update payloads.

`model_config = ConfigDict(from_attributes=True)` on response schemas tells
Pydantic to read attributes from ORM objects directly (replaces the old
`orm_mode = True` from Pydantic v1).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Category schemas
# ---------------------------------------------------------------------------


class CategoryCreate(BaseModel):
    """Payload expected when creating a new category."""

    name: str = Field(..., min_length=1, max_length=100, examples=["Food"])


class CategoryResponse(BaseModel):
    """Shape of a category returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Expense schemas
# ---------------------------------------------------------------------------


class ExpenseCreate(BaseModel):
    """Payload expected when creating a new expense."""

    amount: Decimal = Field(
        ...,
        gt=0,  # must be strictly greater than zero
        decimal_places=2,
        examples=[Decimal("42.50")],
    )
    description: Optional[str] = Field(None, max_length=500)
    expense_date: date
    category_id: int


class ExpenseUpdate(BaseModel):
    """
    Payload for a full replacement (PUT) of an expense.

    All fields are Optional so the caller can update just one attribute
    without resending the unchanged ones. The route handler picks up only
    the fields that are explicitly supplied.
    """

    amount: Optional[Decimal] = Field(
        None,
        gt=0,
        decimal_places=2,
    )
    description: Optional[str] = Field(None, max_length=500)
    expense_date: Optional[date] = None
    category_id: Optional[int] = None


class ExpenseResponse(BaseModel):
    """Shape of an expense returned from the API, including nested category."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    description: Optional[str]
    expense_date: date
    category_id: int
    created_at: datetime

    # Nested category object so callers don't need a second request
    category: CategoryResponse


# ---------------------------------------------------------------------------
# Summary schemas
# ---------------------------------------------------------------------------


class CategorySummary(BaseModel):
    """Per-category spending total for the summary endpoint."""

    category: str
    total: Decimal


class SummaryResponse(BaseModel):
    """Response for GET /summary?month=YYYY-MM."""

    month: str
    total: Decimal
    by_category: list[CategorySummary]
