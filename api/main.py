"""
api/main.py
────────────
Phase 2: FastAPI service layer in front of the existing graphs/database
layer. This does not replace ui/app.py — the Streamlit dashboard keeps
working exactly as before, reading/writing the same SQLite database. This
API is a second, programmatic interface onto the same repositories and
graphs, so a CI pipeline, a script, or another service can drive the same
invoice pipeline without going through Streamlit.

Run with:
    uvicorn api.main:app --reload --port 8000

Then see interactive docs at http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from database.schema import initialize_database
from api.routers import audit, customers, failed, health, invoices, jobs, mcp_router, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Finance Overdue Agent API",
    description=(
        "Programmatic interface onto the existing LangGraph invoice "
        "follow-up pipeline: upload CSVs, inspect jobs/audit logs, retry "
        "failed invoices, look up customer risk memory, generate a single "
        "follow-up email on demand, and discover/call MCP tools directly."
    ),
    version="0.3.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(audit.router)
app.include_router(failed.router)
app.include_router(customers.router)
app.include_router(invoices.router)
app.include_router(mcp_router.router)
