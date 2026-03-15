from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import random
import time
from typing import List, Dict, Any, Literal, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from crawl4ai import (
    AsyncWebCrawler,
    AdaptiveCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
)

from ..config import get_settings
from ..llm import LLMAgent
from ..memory_store import get_memory_store, get_domain_from_url
from .search_agent import SearchResult


Mode = Literal["fast", "comprehensive"]

@dataclass
class PageContent:
    url: str
    title: str | None
    markdown: str
    html: str


logger = logging.getLogger("anyscrape.crawl")


class ProxyRotator:
    """Manages a pool of Webshare proxies and rotates through them."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._proxies: List[Dict[str, str]] = []
        self._index = 0
        self._loaded = False

    def _load_proxies(self) -> None:
        """Load proxies from Webshare API or direct config."""
        if self._loaded:
            return
        self._loaded = True

        # Option 1: Fetch proxy list from Webshare API
        if self._settings.webshare_api_key:
            try:
                resp = requests.get(
                    "https://proxy.webshare.io/api/v2/proxy/list/"
                    "?mode=direct&page=1&page_size=100",
                    headers={"Authorization": f"Token {self._settings.webshare_api_key}"},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                for p in data.get("results", []):
                    self._proxies.append({
                        "server": f"http://{p['proxy_address']}:{p['port']}",
                        "username": p.get("username", ""),
                        "password": p.get("password", ""),
                    })
                logger.info("Loaded %d proxies from Webshare API", len(self._proxies))
            except Exception as e:
                logger.error("Failed to load proxies from Webshare API: %s", e)

        # Option 2: Direct proxy credentials (single rotating endpoint)
        if not self._proxies and self._settings.webshare_proxy_host:
            self._proxies.append({
                "server": f"http://{self._settings.webshare_proxy_username}:{self._settings.webshare_proxy_password}@{self._settings.webshare_proxy_host}:{self._settings.webshare_proxy_port}",
            })
            logger.info("Using direct Webshare rotating proxy endpoint")

        # Shuffle to avoid all workers hitting the same proxy first
        if len(self._proxies) > 1:
            random.shuffle(self._proxies)

    def get_proxy(self) -> Optional[Dict[str, str]]:
        """Return the next proxy config dict, or None if no proxies configured."""
        self._load_proxies()
        if not self._proxies:
            return None
        proxy = self._proxies[self._index % len(self._proxies)]
        self._index += 1
        return proxy

    @property
    def is_enabled(self) -> bool:
        self._load_proxies()
        return len(self._proxies) > 0


class CrawlAgent:
    """
    Agent responsible for crawling and extracting relevant content
    from selected URLs. Uses Crawl4AI under the hood and retries with
    non-headless mode if anti-bot blocking is detected.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._llm = LLMAgent()
        self._memory = get_memory_store()
        self._proxy_rotator = ProxyRotator(self._settings)

    async def _crawl_single(
        self, crawler: AsyncWebCrawler | None, url: str, headless: bool | None = None
    ) -> PageContent | None:
        """
        Crawl a single URL with automatic anti-bot detection and retry.
        """
        domain = get_domain_from_url(url)
        # Use domain-level memory to prefer visible browser when headless has
        # frequently been blocked in the past.
        prefer_non_headless = False
        if domain:
            blocked = int(
                self._memory.get_value("crawl_agent", domain, "blocked_count", 0)
            )
            successful = int(
                self._memory.get_value("crawl_agent", domain, "success_count", 0)
            )
            if blocked >= 2 and blocked > successful:
                prefer_non_headless = True

        default_headless = self._settings.headless_default
        if prefer_non_headless:
            default_headless = False

        headless_flag = default_headless if headless is None else headless

        async def run_with_headless(flag: bool) -> PageContent | None:
            proxy = self._proxy_rotator.get_proxy()
            if proxy:
                # Log proxy host without credentials
                proxy_host = proxy["server"].split("@")[-1] if "@" in proxy["server"] else proxy["server"]
                logger.info("Crawling URL (headless=%s, proxy=%s): %s", flag, proxy_host, url)
            else:
                logger.info("Crawling URL (headless=%s): %s", flag, url)
            browser_config = BrowserConfig(
                headless=flag,
                proxy_config=proxy if proxy else None,
            )
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                page_timeout=80000,
                screenshot=False,
            )
            # Use a dedicated crawler per call to avoid shared config mutation
            # across concurrent tasks.
            async with AsyncWebCrawler(config=browser_config) as per_url_crawler:
                result = await per_url_crawler.arun(url=url, config=run_config)
            if not getattr(result, "success", True):
                logger.warning("Crawl failed for %s (headless=%s)", url, flag)
                if domain:
                    self._memory.increment("crawl_agent", domain, "failed_crawls", 1)
                return None

            html: str = getattr(result, "html", "") or ""
            markdown = getattr(result, "markdown", "") or ""
            title = None
            if html:
                soup = BeautifulSoup(html, "html.parser")
                if soup.title and soup.title.string:
                    title = soup.title.string.strip()
            page = PageContent(url=url, title=title, markdown=markdown, html=html)
            logger.info(
                "Finished crawl for %s (headless=%s), html_len=%d, md_len=%d",
                url,
                flag,
                len(html),
                len(markdown),
            )
            if domain:
                self._memory.increment("crawl_agent", domain, "success_count", 1)
            return page

        first_attempt = await run_with_headless(headless_flag)
        if first_attempt and not self._looks_blocked(first_attempt):
            return first_attempt

        # Retry with visible browser if first attempt failed or looks blocked.
        if headless_flag:
            logger.info(
                "First crawl attempt appears blocked for %s, retrying with headless=False",
                url,
            )
            second_attempt = await run_with_headless(False)
            if second_attempt and not self._looks_blocked(second_attempt):
                if domain:
                    self._memory.increment(
                        "crawl_agent", domain, "headless_block_events", 1
                    )
                return second_attempt

        return first_attempt

    def _looks_blocked(self, page: PageContent) -> bool:
        """
        Heuristics to detect if a page likely represents a bot-detection wall.
        """
        text = page.markdown.lower()[:2000]
        blockage_markers = [
            "access denied",
            "unusual traffic",
            "verify you are human",
            "captcha",
            "akamai",
            "request blocked",
        ]
        if any(marker in text for marker in blockage_markers):
            logger.debug("Blockage markers detected in content for %s", page.url)
            domain = get_domain_from_url(page.url)
            if domain:
                self._memory.increment("crawl_agent", domain, "blocked_count", 1)
            return True
        if len(page.html) < 2000 and "doctype html" not in page.html.lower():
            logger.debug(
                "Suspiciously small HTML (%d bytes) for %s, may be blocked",
                len(page.html),
                page.url,
            )
            domain = get_domain_from_url(page.url)
            if domain:
                self._memory.increment("crawl_agent", domain, "blocked_count", 1)
            return True
        return False

    def _build_crawl_plan_prompt(self, query: str, search_results: List[SearchResult]) -> tuple[str, list]:
        numbered = []
        for idx, r in enumerate(search_results):
            numbered.append(
                f"{idx+1}. title={r.title!r}, url={r.url!r}, snippet={r.snippet!r}"
            )
        system_prompt = (
            "You are a web scraping planner. Given a user query and a list of "
            "search results, choose which URLs should be deeply crawled to "
            "answer the query. Respond ONLY with a comma-separated list of "
            "result indices (e.g. '1,3,4'). Prefer primary sources related to "
            "the query, such as product pages or official listings."
        )
        messages = [
            {"role": "user", "content": f"Query: {query}\nResults:\n" + "\n".join(numbered)}
        ]
        return system_prompt, messages

    def _parse_crawl_indices(self, content: str, count: int) -> List[int]:
        selected_indices: List[int] = []
        for token in content.split(","):
            token = token.strip()
            if not token.isdigit():
                continue
            idx = int(token) - 1
            if 0 <= idx < count:
                selected_indices.append(idx)
        return selected_indices

    async def crawl_selected_results(
        self,
        query: str,
        search_results: List[SearchResult],
        mode: Mode = "fast",
    ) -> List[PageContent]:
        """
        Use the LLM to select which search results to crawl and then
        crawl them concurrently. Each URL gets its own browser instance
        to avoid shared state issues under concurrency.
        """
        if not search_results:
            logger.info("No search results to crawl for query: %s", query)
            return []

        # Ask LLM which URLs to crawl (async to not block event loop)
        system_prompt, messages = self._build_crawl_plan_prompt(query, search_results)
        content = await self._llm.acomplete(
            system_prompt=system_prompt, messages=messages,
            temperature=0.1, max_tokens=64,
        )

        selected_indices = self._parse_crawl_indices(content, len(search_results))

        if not selected_indices:
            logger.info(
                "Planning LLM did not return specific indices to crawl, using all %d results",
                len(search_results),
            )
            selected_indices = list(range(len(search_results)))
        else:
            logger.info(
                "Planning LLM selected %d of %d results to crawl: %s",
                len(selected_indices),
                len(search_results),
                ", ".join(str(i + 1) for i in selected_indices),
            )

        urls = [search_results[i].url for i in selected_indices]
        concurrency = max(1, self._settings.max_crawl_concurrency)
        logger.info(
            "Step 2/3: Crawling %d URLs with concurrency=%d in %s mode",
            len(urls),
            concurrency,
            mode,
        )

        sem = asyncio.Semaphore(concurrency)

        async def bound_crawl(u: str) -> PageContent | None:
            async with sem:
                return await self._crawl_single(None, u)

        tasks = [asyncio.create_task(bound_crawl(u)) for u in urls]

        pages: List[PageContent | None]
        if mode == "fast":
            crawl_timeout = 45.0
            start_time = time.monotonic()
            try:
                pages = await asyncio.wait_for(
                    asyncio.gather(*tasks), timeout=crawl_timeout
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Crawl phase exceeded %.1f seconds; returning partial results",
                    crawl_timeout,
                )
                pages = [t.result() if t.done() else None for t in tasks]
            elapsed = time.monotonic() - start_time
            logger.info(
                "Fast crawl phase finished in %.1f seconds", elapsed
            )
        else:
            pages = await asyncio.gather(*tasks)

            # Adaptive crawl per root URL for comprehensive mode.
            for u in urls:
                logger.info(
                    "Comprehensive mode: running adaptive crawl for %s", u
                )
                async with AsyncWebCrawler() as adaptive_crawler:
                    adaptive = AdaptiveCrawler(adaptive_crawler)
                    adaptive_result = await adaptive.digest(start_url=u, query=query)
                    summary_markdown = getattr(adaptive_result, "markdown", "")
                    if summary_markdown:
                        pages.append(
                            PageContent(
                                url=u,
                                title="Adaptive summary",
                                markdown=summary_markdown,
                                html="",
                            )
                        )

        successful_pages = [r for r in pages if r is not None]
        logger.info(
            "Completed crawling. Successfully crawled %d/%d URLs",
            len(successful_pages),
            len(urls),
        )
        return successful_pages

    async def adaptive_crawl(
        self, start_url: str, query: str
    ) -> Dict[str, Any]:
        """
        Optional helper that uses Crawl4AI's AdaptiveCrawler to
        follow links and stop when it has enough information.
        """
        logger.info("Starting adaptive crawl from %s for query: %s", start_url, query)
        async with AsyncWebCrawler() as crawler:
            adaptive = AdaptiveCrawler(crawler)
            result = await adaptive.digest(start_url=start_url, query=query)
            summary = {
                "start_url": start_url,
                "crawled_urls": list(getattr(result, "crawled_urls", [])),
                "confidence": getattr(adaptive, "confidence", None),
                "summary_markdown": getattr(result, "markdown", ""),
            }
            logger.info(
                "Adaptive crawl finished. Crawled %d pages, confidence=%s",
                len(summary["crawled_urls"]),
                summary["confidence"],
            )
            return summary

