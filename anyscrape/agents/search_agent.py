from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import List

import requests

from ..config import get_settings
from ..llm import LLMAgent


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str | None = None


logger = logging.getLogger("anyscrape.search")


class SearchAgent:
    """
    Agent responsible for web search via SearXNG and selecting the most
    relevant links for the user query.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._llm = LLMAgent()

    # ── SearXNG search ───────────────────────────────────────────

    def web_search(self, query: str, max_results_override: int | None = None) -> List[SearchResult]:
        """
        Search via SearXNG JSON API. Paginates automatically to collect
        the requested number of results.
        """
        base_url = self._settings.searxng_base_url.rstrip("/")
        if not base_url:
            raise RuntimeError(
                "SEARXNG_BASE_URL is not set. SearXNG is required for web search. "
                "Set it in your .env file (e.g. SEARXNG_BASE_URL=http://localhost:8888)."
            )

        max_results = max_results_override or self._settings.max_search_results
        logger.info("Step 1/3: Running SearXNG search for query: %s (max_results=%d)", query, max_results)

        results: List[SearchResult] = []
        seen_urls: set[str] = set()
        # SearXNG returns ~10 results per page
        pages_needed = max(1, (max_results + 9) // 10)

        for page in range(1, pages_needed + 1):
            try:
                resp = requests.get(
                    f"{base_url}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "pageno": page,
                        "categories": "general",
                        "language": "en",
                    },
                    headers={"Accept": "application/json"},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error("SearXNG request failed (page %d): %s", page, e)
                break

            page_results = data.get("results", [])
            if not page_results:
                logger.debug("SearXNG returned empty results on page %d, stopping pagination", page)
                break

            for r in page_results:
                title = r.get("title") or ""
                url = r.get("url") or ""
                snippet = r.get("content") or ""
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append(SearchResult(title=title, url=url, snippet=snippet))
                if len(results) >= max_results:
                    break

            if len(results) >= max_results:
                break

        logger.info("SearXNG returned %d results", len(results))
        return results[:max_results]

    async def async_web_search(self, query: str, max_results_override: int | None = None) -> List[SearchResult]:
        """
        Run SearXNG search in a thread to avoid blocking the event loop.
        """
        return await asyncio.to_thread(self.web_search, query, max_results_override)

    # ── LLM re-ranking ───────────────────────────────────────────

    def _parse_rank_indices(self, content: str, results: List[SearchResult]) -> List[int]:
        index_order: List[int] = []
        for token in content.split(","):
            token = token.strip()
            if not token.isdigit():
                continue
            idx = int(token) - 1
            if 0 <= idx < len(results):
                index_order.append(idx)
        return index_order

    def _build_rank_prompt(self, query: str, results: List[SearchResult]) -> tuple[str, list]:
        json_lines = []
        for idx, r in enumerate(results):
            json_lines.append(
                f"{idx+1}. title={r.title!r}, url={r.url!r}, snippet={r.snippet!r}"
            )
        system_prompt = (
            "You are a web research planner. Given a user query and a list of "
            "search results, you must select and re-order the results from most "
            "to least relevant. Respond ONLY with a comma-separated list of "
            "result indices in desired order, e.g. '2,1,3'."
        )
        messages = [
            {"role": "user", "content": f"Query: {query}\nResults:\n" + "\n".join(json_lines)}
        ]
        return system_prompt, messages

    def _apply_ranking(self, results: List[SearchResult], index_order: List[int]) -> List[SearchResult]:
        if not index_order:
            logger.info(
                "Re-ranking returned no valid indices, keeping original order for %d results",
                len(results),
            )
            return results
        ordered = [results[i] for i in index_order]
        top = ordered[0]
        logger.info(
            "Top search result after re-ranking: %s (%s)",
            (top.title or top.url)[:80],
            top.url,
        )
        return ordered

    def rank_relevance(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """
        Let the LLM re-rank the top results by relevance to the query.
        """
        if not results:
            return results
        system_prompt, messages = self._build_rank_prompt(query, results)
        content = self._llm.complete(
            system_prompt=system_prompt, messages=messages,
            temperature=0.0, max_tokens=64,
        )
        return self._apply_ranking(results, self._parse_rank_indices(content, results))

    async def arank_relevance(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """
        Async version of rank_relevance.
        """
        if not results:
            return results
        system_prompt, messages = self._build_rank_prompt(query, results)
        content = await self._llm.acomplete(
            system_prompt=system_prompt, messages=messages,
            temperature=0.0, max_tokens=64,
        )
        return self._apply_ranking(results, self._parse_rank_indices(content, results))
