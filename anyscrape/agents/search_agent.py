from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import List

from ddgs import DDGS

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
    Agent responsible for running DuckDuckGo search and
    selecting the most relevant links for the user query.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._llm = LLMAgent()

    def web_search(self, query: str) -> List[SearchResult]:
        """
        Use DuckDuckGo to get top N search results as raw JSON.
        """
        max_results = self._settings.max_search_results
        logger.info("Step 1/3: Running DuckDuckGo search for query: %s", query)

        results: List[SearchResult] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                title = r.get("title") or ""
                url = r.get("href") or r.get("url") or ""
                snippet = r.get("body") or r.get("snippet")
                if not url:
                    continue
                results.append(SearchResult(title=title, url=url, snippet=snippet))
        logger.info("DuckDuckGo returned %d results", len(results))
        return results

    def rank_relevance(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """
        Let the LLM re-rank the top results by relevance to the query.
        """
        if not results:
            return results

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
        content = self._llm.complete(
            system_prompt=system_prompt,
            messages=[
                {"role": "user", "content": f"Query: {query}\nResults:\n" + "\n".join(json_lines)}
            ],
            temperature=0.0,
            max_tokens=64,
        )

        index_order: List[int] = []
        for token in content.split(","):
            token = token.strip()
            if not token.isdigit():
                continue
            idx = int(token) - 1
            if 0 <= idx < len(results):
                index_order.append(idx)

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



