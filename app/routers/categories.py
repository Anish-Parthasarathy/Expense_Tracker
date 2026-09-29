"""
routers/categories.py
---------------------
CRUD routes for expense categories.

Business rules enforced here:
  - POST /categories   → 409 if a category with the same name already exists
  - GET /categories    → returns all categories (no pagination; count expected to be small)
  - DELETE /categories/{id} → 409 if the category still has associated expenses
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/categories", tags=["categories"])


@router.post(
    "/",
    response_model=schemas.CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new category",
)
def create_category(payload: schemas.CategoryCreate, db: Session = Depends(get_db)):
    """
    Create a category.

    Returns 409 if a category with the same name (case-sensitive) already
    exists, so the client gets a clear error rather than a 500 from a DB
    unique-constraint violation.
    """
    # Check for duplicate before inserting to give a clean 409
    existing = (
        db.query(models.Category)
        .filter(models.Category.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Category '{payload.name}' already exists.",
        )

    category = models.Category(name=payload.name)
    db.add(category)
    db.commit()
    db.refresh(category)  # refresh to load server-generated fields like created_at
    return category


@router.get(
    "/",
    response_model=list[schemas.CategoryResponse],
    summary="List all categories",
)
def list_categories(db: Session = Depends(get_db)):
    """Return every category ordered by name for predictable output."""
    return db.query(models.Category).order_by(models.Category.name).all()


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a category",
)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    """
    Delete a category by ID.

    Returns 404 if the category doesn't exist.
    Returns 409 if the category still has expenses linked to it,
    protecting referential integrity in a user-friendly way.
    """
    category = db.get(models.Category, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category {category_id} not found.",
        )

    # Prevent deletion of categories that still have expenses attached.
    # Without this guard the FK constraint would also block it, but the
    # resulting error would be a 500, not a helpful 409.
    if category.expenses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Category '{category.name}' still has {len(category.expenses)} "
                "expense(s). Remove or reassign them before deleting the category."
            ),
        )

    db.delete(category)
    db.commit()
    # 204 No Content → FastAPI sends an empty response body automatically
