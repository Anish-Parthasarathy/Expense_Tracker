"""
models.py
---------
SQLAlchemy 2.0 ORM models for the expense tracker.

Two tables:
  - categories : lookup table for expense categories
  - expenses   : individual spending records, each tied to a category

Both models inherit from Base (defined in database.py), which is the
single source of truth for metadata used by Alembic migrations.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Category(Base):
    """
    Represents a spending category (e.g. "Food", "Transport").

    The `name` column has a unique constraint so the application can return
    a 409 Conflict instead of a DB-level IntegrityError that would be
    harder to translate into a clean HTTP response.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # unique=True enforces one name per category at the DB level as well
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    # server_default uses a DB-side function so the timestamp is always set
    # even if a row is inserted via raw SQL outside the ORM.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship to expenses – back_populates links both sides together.
    # lazy="select" (default) loads expenses only when accessed.
    expenses: Mapped[list["Expense"]] = relationship(
        "Expense", back_populates="category"
    )


class Expense(Base):
    """
    Represents a single spending record.

    Amount is stored as NUMERIC(10, 2) which maps to Python's Decimal type,
    ensuring exact decimal arithmetic without floating-point rounding errors.
    """

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Numeric(10, 2): up to 10 significant digits, 2 after the decimal point.
    # Use Decimal in Python code – never float – to avoid rounding surprises.
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Optional free-text note about the expense
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The date the money was spent (not necessarily today)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Foreign key to categories.id; NOT NULL enforces that every expense
    # must belong to a category.
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Many-side of the one-to-many relationship
    category: Mapped["Category"] = relationship("Category", back_populates="expenses")
