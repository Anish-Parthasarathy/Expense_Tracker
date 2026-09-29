"""
main.py
-------
FastAPI application factory.

Routers are registered here with a single prefix each. Keeping this file
thin (only wiring, no business logic) makes the codebase easy to navigate.
"""

from fastapi import FastAPI

from app.routers import categories, expenses

app = FastAPI(
    title="Expense Tracker API",
    description=(
        "A simple expense tracking API. "
        "Track spending across custom categories with monthly summaries."
    ),
    version="1.0.0",
)

# Register routers – categories router already has /categories prefix baked in,
# expenses router uses bare /expenses paths defined at the route level.
app.include_router(categories.router)
app.include_router(expenses.router)


@app.get("/", tags=["health"])
def root():
    """Health-check / root endpoint."""
    return {"status": "ok", "message": "Expense Tracker API is running."}
