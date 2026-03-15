from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import List, Dict, Any

from ..llm import LLMAgent
from .crawl_agent import PageContent


@dataclass
class ConsolidatedAnswer:
    """
    High-level structured response that can later be serialized
    for API/web responses.
    """

    query: str
    answer_markdown: str
    sources: List[Dict[str, str]]


logger = logging.getLogger("anyscrape.synthesis")


class SynthesisAgent:
    """
    Agent that consolidates multiple crawled pages into a single
    coherent answer tailored to the user's query.
    """

    # Per-mode limits for content extraction and token generation
    _MODE_LIMITS = {
        "fast":          {"snippet_chars": 4000,  "max_tokens": 1200},
        "comprehensive": {"snippet_chars": 12000, "max_tokens": 4096},
    }

    def __init__(self) -> None:
        self._llm = LLMAgent()
        self._mode = "fast"

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    _SYSTEM_PROMPT = (
        "You are an autonomous web research analyst and answer generator.\n"
        "You receive (1) the original user query and (2) extracted markdown "
        "from multiple crawled web pages.\n\n"
        "Your PRIMARY objective is to answer the user's query directly and "
        "use the crawled data only as evidence, not to mindlessly summarize it.\n\n"
        "You must:\n"
        "- Infer the user's intent and what they actually care about.\n"
        "- Select only the most relevant facts from the crawled content.\n"
        "- Resolve conflicts across sources where possible, or explain disagreements.\n"
        "- Explicitly call out any gaps or uncertainty in the data.\n\n"
        "Output formatting rules (choose what best fits this query + data):\n"
        "- For structured comparisons (e.g. product prices, job listings, tables of items), "
        "prefer one or more Markdown tables with clear columns (e.g. product/job title, "
        "company/vendor, location, key attributes, price/salary, source URL).\n"
        "- For step-by-step instructions, use numbered lists.\n"
        "- For conceptual explanations or general questions, use short sections with headings "
        "and bullet points.\n"
        "- You may combine formats (e.g. short narrative summary followed by a table).\n\n"
        "Always start with a short, context-aware direct answer that explicitly references the "
        "user's request (for example, mention specific stores like Amazon or Walmart if that "
        "is part of the query). Then provide details in the structure you chose. Finish with "
        "a brief 'Sources' section listing the most important origin URLs."
    )

    def _build_messages(self, query: str, pages: List[PageContent]) -> list:
        limits = self._MODE_LIMITS.get(self._mode, self._MODE_LIMITS["fast"])
        snippet_chars = limits["snippet_chars"]
        snippets = []
        for idx, p in enumerate(pages):
            snippet = p.markdown[:snippet_chars]
            snippets.append(f"Source {idx+1} ({p.url}):\n{snippet}\n")
        return [
            {
                "role": "user",
                "content": f"User query:\n{query}\n\nCrawled content:\n\n" + "\n\n".join(snippets),
            }
        ]

    def _empty_answer(self, query: str) -> ConsolidatedAnswer:
        logger.info("Step 3/3: No pages crawled, returning empty answer")
        return ConsolidatedAnswer(
            query=query,
            answer_markdown="No relevant pages could be crawled.",
            sources=[],
        )

    def _get_max_tokens(self) -> int:
        return self._MODE_LIMITS.get(self._mode, self._MODE_LIMITS["fast"])["max_tokens"]

    def synthesize(self, query: str, pages: List[PageContent]) -> ConsolidatedAnswer:
        if not pages:
            return self._empty_answer(query)
        max_tokens = self._get_max_tokens()
        logger.info("Step 3/3: Synthesizing final answer from %d pages (max_tokens=%d)", len(pages), max_tokens)
        content = self._llm.complete(
            system_prompt=self._SYSTEM_PROMPT,
            messages=self._build_messages(query, pages),
            temperature=0.3, max_tokens=max_tokens,
        )
        sources = [{"url": p.url, "title": p.title or ""} for p in pages]
        logger.info("Synthesis complete. Produced answer of length %d characters", len(content))
        return ConsolidatedAnswer(query=query, answer_markdown=content, sources=sources)

    async def asynthesize(self, query: str, pages: List[PageContent]) -> ConsolidatedAnswer:
        """Async version of synthesize."""
        if not pages:
            return self._empty_answer(query)
        max_tokens = self._get_max_tokens()
        logger.info("Step 3/3: Synthesizing final answer from %d pages (max_tokens=%d)", len(pages), max_tokens)
        content = await self._llm.acomplete(
            system_prompt=self._SYSTEM_PROMPT,
            messages=self._build_messages(query, pages),
            temperature=0.3, max_tokens=max_tokens,
        )
        sources = [{"url": p.url, "title": p.title or ""} for p in pages]
        logger.info("Synthesis complete. Produced answer of length %d characters", len(content))
        return ConsolidatedAnswer(query=query, answer_markdown=content, sources=sources)
