from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import List

from ..llm import LLMAgent
from ..memory_store import get_memory_store, get_domain_from_url
from .search_agent import SearchResult


logger = logging.getLogger("anyscrape.decision")
_AGENT_NAME = "decision_agent"


@dataclass
class DecisionOutput:
    selected: List[SearchResult]
    skipped: List[SearchResult]


class DecisionAgent:
    """
    Agent that decides which search results should be sent to the
    CrawlAgent, using URL de-duplication, simple heuristics, LLM
    guidance, and stored memory of past successful domains.
    """

    def __init__(self) -> None:
        self._llm = LLMAgent()
        self._memory = get_memory_store()
        self._max_urls = 5  # default, overridden per-call via set_mode

    def set_mode(self, mode: str) -> None:
        """Adjust limits based on crawl mode."""
        if mode == "comprehensive":
            self._max_urls = 10
        else:
            self._max_urls = 5

    def _deduplicate(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Remove obvious duplicates based on canonicalized URL.
        """
        seen_keys: set[str] = set()
        unique: List[SearchResult] = []
        for r in results:
            url = r.url
            domain = get_domain_from_url(url) or ""
            path_key = url.split("?", 1)[0].split("#", 1)[0]
            key = f"{domain}{path_key}"
            if key in seen_keys:
                logger.debug("Skipping duplicate URL candidate: %s", url)
                if domain:
                    self._memory.increment(_AGENT_NAME, domain, "duplicate_skips", 1)
                continue
            seen_keys.add(key)
            unique.append(r)
        if len(unique) != len(results):
            logger.info(
                "Deduplicated search results: %d -> %d",
                len(results),
                len(unique),
            )
        return unique

    def _score_bias_from_memory(self, result: SearchResult) -> float:
        """
        Use stored memory (per-domain stats) to bias selection.
        """
        domain = get_domain_from_url(result.url)
        if not domain:
            return 0.0
        stats = self._memory.get_domain_stats(_AGENT_NAME, domain)
        # Simple heuristic: more past selections slightly increase priority.
        selected_count = int(stats.get("selected_count", 0))
        blocked_count = int(stats.get("blocked_or_irrelevant_count", 0))
        return 0.1 * selected_count - 0.2 * blocked_count

    def _build_decision_prompt(
        self, query: str, candidates: List[SearchResult]
    ) -> tuple[str, list, list]:
        lines = []
        for idx, r in enumerate(candidates):
            bias = self._score_bias_from_memory(r)
            lines.append(
                f"{idx+1}. title={r.title!r}, url={r.url!r}, snippet={r.snippet!r}, bias={bias:+.2f}"
            )

        max_urls = self._max_urls
        system_prompt = (
            "You are a decision-making agent for a web scraping system.\n"
            "Given a user query and a list of search results, you MUST select only the URLs "
            "that are truly relevant to answering the query, and avoid redundant/duplicate "
            "or obviously low-value pages (e.g., generic category pages if a precise page "
            "exists).\n\n"
            "Rules:\n"
            "- Prefer results that are specific to the query intent (e.g. product pages, job listings).\n"
            "- Avoid near-duplicate URLs or pages that look like the same content.\n"
            f"- Choose at most {max_urls} URLs unless the list is very small.\n"
            "- Respond ONLY with a comma-separated list of indices, e.g. '1,3,4'."
        )
        messages = [
            {
                "role": "user",
                "content": f"Query:\n{query}\n\nCandidates:\n" + "\n".join(lines),
            }
        ]
        return system_prompt, messages, lines

    def _apply_decision(
        self, candidates: List[SearchResult], content: str
    ) -> DecisionOutput:
        selected_indices: List[int] = []
        for token in content.split(","):
            token = token.strip()
            if not token.isdigit():
                continue
            idx = int(token) - 1
            if 0 <= idx < len(candidates):
                selected_indices.append(idx)

        if not selected_indices:
            logger.info(
                "Decision LLM returned no usable indices, falling back to top-3 of %d candidates",
                len(candidates),
            )
            selected_indices = list(range(min(3, len(candidates))))

        selected_results: List[SearchResult] = []
        skipped_results: List[SearchResult] = []

        for idx, r in enumerate(candidates):
            domain = get_domain_from_url(r.url)
            if idx in selected_indices:
                selected_results.append(r)
                if domain:
                    self._memory.increment(_AGENT_NAME, domain, "selected_count", 1)
            else:
                skipped_results.append(r)
                if domain:
                    self._memory.increment(_AGENT_NAME, domain, "blocked_or_irrelevant_count", 1)

        logger.info(
            "DecisionAgent selected %d/%d candidates for crawling",
            len(selected_results),
            len(candidates),
        )
        return DecisionOutput(selected=selected_results, skipped=skipped_results)

    def _prepare_candidates(
        self, ranked_results: List[SearchResult], max_candidates: int | None = None
    ) -> List[SearchResult]:
        deduped = self._deduplicate(ranked_results)
        if max_candidates is None:
            max_candidates = min(10, len(deduped))
        return deduped[:max_candidates]

    def select_for_crawling(
        self, query: str, ranked_results: List[SearchResult], max_candidates: int | None = None
    ) -> DecisionOutput:
        """
        Choose a subset of ranked search results to crawl.
        """
        if not ranked_results:
            return DecisionOutput(selected=[], skipped=[])

        candidates = self._prepare_candidates(ranked_results, max_candidates)
        system_prompt, messages, _ = self._build_decision_prompt(query, candidates)
        content = self._llm.complete(
            system_prompt=system_prompt, messages=messages,
            temperature=0.1, max_tokens=64,
        )
        return self._apply_decision(candidates, content)

    async def aselect_for_crawling(
        self, query: str, ranked_results: List[SearchResult], max_candidates: int | None = None
    ) -> DecisionOutput:
        """
        Async version of select_for_crawling.
        """
        if not ranked_results:
            return DecisionOutput(selected=[], skipped=[])

        candidates = self._prepare_candidates(ranked_results, max_candidates)
        system_prompt, messages, _ = self._build_decision_prompt(query, candidates)
        content = await self._llm.acomplete(
            system_prompt=system_prompt, messages=messages,
            temperature=0.1, max_tokens=64,
        )
        return self._apply_decision(candidates, content)


