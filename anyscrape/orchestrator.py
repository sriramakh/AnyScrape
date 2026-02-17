from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any

from .agents.search_agent import SearchAgent
from .agents.decision_agent import DecisionAgent
from .agents.crawl_agent import CrawlAgent, Mode
from .agents.synthesis_agent import SynthesisAgent


logger = logging.getLogger("anyscrape.orchestrator")


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
        logger.info("Starting AnyScrape pipeline for query: %s", query)

        # Step 1: search
        raw_results = self._search_agent.web_search(query)
        ranked_results = self._search_agent.rank_relevance(query, raw_results)

        # Step 1.5: decision agent filters and deduplicates links for crawling.
        decision_output = self._decision_agent.select_for_crawling(
            query, ranked_results
        )
        selected_for_crawl = decision_output.selected

        # Step 2: crawl selected pages
        pages = await self._crawl_agent.crawl_selected_results(
            query, selected_for_crawl, mode=mode
        )

        # Step 3: synthesize an answer
        consolidated = self._synthesis_agent.synthesize(query, pages)

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
    Synchronous helper for CLI usage.
    """
    orchestrator = AnyScrapeOrchestrator()
    return asyncio.run(orchestrator.run_query(query, mode=mode))
