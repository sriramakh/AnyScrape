from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any

from .agents.search_agent import SearchAgent
from .agents.decision_agent import DecisionAgent
from .agents.crawl_agent import CrawlAgent, Mode
from .agents.synthesis_agent import SynthesisAgent


logger = logging.getLogger("anyscrape.orchestrator")

# Limit how many queries can run the full pipeline concurrently to avoid
# overwhelming browser instances, LLM rate limits, and proxy connections.
_MAX_CONCURRENT_QUERIES = 5
_query_semaphore: asyncio.Semaphore | None = None


def _get_query_semaphore() -> asyncio.Semaphore:
    global _query_semaphore
    if _query_semaphore is None:
        _query_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_QUERIES)
    return _query_semaphore


class AnyScrapeOrchestrator:
    """
    High-level orchestration for the multi-agent scraping pipeline:

    1. SearchAgent: run DuckDuckGo search for the user query.
    2. CrawlAgent: plan and perform crawls on selected results.
    3. SynthesisAgent: consolidate results into a final answer.
    """

    def __init__(self) -> None:
        self._search_agent = SearchAgent()
        self._decision_agent = DecisionAgent()
        self._crawl_agent = CrawlAgent()
        self._synthesis_agent = SynthesisAgent()

    async def run_query(self, query: str, mode: Mode = "fast") -> Dict[str, Any]:
        """
        Async pipeline entry point for the web API. Uses async LLM calls
        and a concurrency semaphore to handle parallel requests safely.
        """
        async with _get_query_semaphore():
            return await self._run_pipeline(query, mode)

    async def _run_pipeline(self, query: str, mode: Mode) -> Dict[str, Any]:
        logger.info("Starting AnyScrape pipeline for query: %s (mode=%s)", query, mode)

        # Configure agents for the requested mode
        self._decision_agent.set_mode(mode)
        self._synthesis_agent.set_mode(mode)

        # Comprehensive mode gets more search results to work with
        max_results = 25 if mode == "comprehensive" else None

        # Step 1: search (run blocking DDGS in a thread)
        raw_results = await self._search_agent.async_web_search(query, max_results_override=max_results)
        ranked_results = await self._search_agent.arank_relevance(query, raw_results)

        # Step 1.5: decision agent filters and deduplicates links for crawling.
        decision_output = await self._decision_agent.aselect_for_crawling(
            query, ranked_results
        )
        selected_for_crawl = decision_output.selected

        # Step 2: crawl selected pages
        pages = await self._crawl_agent.crawl_selected_results(
            query, selected_for_crawl, mode=mode
        )

        # Step 3: synthesize an answer
        consolidated = await self._synthesis_agent.asynthesize(query, pages)

        result = {
            "query": consolidated.query,
            "answer_markdown": consolidated.answer_markdown,
            "sources": consolidated.sources,
            "search_results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in ranked_results
            ],
        }
        logger.info("AnyScrape pipeline finished for query: %s", query)
        return result


def run_query_sync(query: str, mode: Mode = "fast") -> Dict[str, Any]:
    """
    Synchronous helper for CLI usage. Uses the original sync methods.
    """
    orchestrator = AnyScrapeOrchestrator()
    search = orchestrator._search_agent
    decision = orchestrator._decision_agent
    crawl = orchestrator._crawl_agent
    synthesis = orchestrator._synthesis_agent

    logger.info("Starting AnyScrape pipeline for query: %s (mode=%s)", query, mode)

    # Configure agents for the requested mode
    decision.set_mode(mode)
    synthesis.set_mode(mode)

    max_results = 25 if mode == "comprehensive" else None

    raw_results = search.web_search(query, max_results_override=max_results)
    ranked_results = search.rank_relevance(query, raw_results)
    decision_output = decision.select_for_crawling(query, ranked_results)

    pages = asyncio.run(
        crawl.crawl_selected_results(query, decision_output.selected, mode=mode)
    )

    consolidated = synthesis.synthesize(query, pages)

    result = {
        "query": consolidated.query,
        "answer_markdown": consolidated.answer_markdown,
        "sources": consolidated.sources,
        "search_results": [
            {"title": r.title, "url": r.url, "snippet": r.snippet}
            for r in ranked_results
        ],
    }
    logger.info("AnyScrape pipeline finished for query: %s", query)
    return result
