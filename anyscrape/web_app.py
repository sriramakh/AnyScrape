from __future__ import annotations

from typing import Literal, Optional, Dict, Any

from fastapi import FastAPI
from pydantic import BaseModel

from .logging_utils import configure_logging
from .orchestrator import AnyScrapeOrchestrator
from .agents.crawl_agent import Mode


app = FastAPI(
    title="AnyScrape API",
    description="Multi-agent autonomous web scraping and research API.",
    version="0.1.0",
)

_orchestrator: Optional[AnyScrapeOrchestrator] = None


class QueryRequest(BaseModel):
    query: str
    mode: Literal["fast", "comprehensive"] = "fast"


class QueryResponse(BaseModel):
    query: str
    answer_markdown: str
    sources: list[Dict[str, str]]
    search_results: list[Dict[str, Any]]


@app.on_event("startup")
async def startup_event() -> None:
    """
    Initialize logging and orchestrator once when the server starts.
    """
    global _orchestrator
    configure_logging(verbose=True)
    _orchestrator = AnyScrapeOrchestrator()


@app.get("/health", tags=["system"])
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse, tags=["query"])
async def query_endpoint(payload: QueryRequest) -> QueryResponse:
    """
    Run the full AnyScrape pipeline for a given query.
    """
    assert _orchestrator is not None, "Orchestrator not initialized"
    mode: Mode = payload.mode  # type: ignore[assignment]
    result = await _orchestrator.run_query(payload.query, mode=mode)
    return QueryResponse(**result)


@app.get("/", tags=["ui"])
async def root() -> Dict[str, str]:
    """
    Minimal landing endpoint with a short description.
    (A richer HTML UI can be added later.)
    """
    return {
        "message": "AnyScrape API is running. POST a JSON body to /query with "
        '{"query": \"your question\", "mode": "fast"|"comprehensive"} to use it.'
    }


