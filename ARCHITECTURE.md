# AnyScrape Architecture

AnyScrape is designed as a modular, multi-agent system where specialized agents collaborate to perform web research and extraction tasks.

## High-Level Overview

The system follows a linear pipeline orchestrated by the `AnyScrapeOrchestrator`:

1.  **User Query** -> **Search Agent** -> **Decision Agent** -> **Crawl Agent** -> **Synthesis Agent** -> **Final Answer**

## Core Components

### 1. Orchestrator (`anyscrape/orchestrator.py`)
-   **Role**: The central controller that manages the workflow.
-   **Responsibility**:
    -   Initializes all agents.
    -   Passes data between agents (e.g., search results to decision agent, selected URLs to crawl agent).
    -   Handles the high-level execution flow (Search -> Decide -> Crawl -> Synthesize).
-   **Concurrency**: A global semaphore (default: 5) limits how many queries run the full pipeline in parallel, preventing resource exhaustion under load.
-   **Dual paths**:
    -   `run_query()` — Fully async path used by the web API. All LLM calls use `AsyncOpenAI` and never block the event loop.
    -   `run_query_sync()` — Sync path for CLI usage. Uses the synchronous OpenAI client.

### 2. Agents

#### Search Agent (`anyscrape/agents/search_agent.py`)
-   **Role**: Discover information sources.
-   **Tools**: `ddgs` (DuckDuckGo Search).
-   **Logic**:
    -   Performs a web search based on the user's query.
    -   Retrieves titles, URLs, and snippets.
    -   Re-ranks results using an LLM to prioritize relevance.
-   **Async**: `async_web_search()` runs the blocking DDGS call in a thread via `asyncio.to_thread`. `arank_relevance()` uses the async LLM client.

#### Decision Agent (`anyscrape/agents/decision_agent.py`)
-   **Role**: Selection and Filtering.
-   **Logic**:
    -   Analyzes the ranked search results.
    -   Deduplicates URLs using canonicalized keys.
    -   Uses domain memory to bias selection toward historically successful domains.
    -   Decides which URLs are most likely to contain the answer via LLM.
    -   Filters out irrelevant or low-quality links before crawling to save resources.
-   **Async**: `aselect_for_crawling()` uses the async LLM client.

#### Crawl Agent (`anyscrape/agents/crawl_agent.py`)
-   **Role**: Content Extraction.
-   **Tools**: `crawl4ai` (AsyncWebCrawler, AdaptiveCrawler).
-   **Modes**:
    -   **Fast Mode**: Concurrently crawls selected URLs with a 45-second global timeout. Best for quick answers.
    -   **Comprehensive Mode**:
        -   Performs deeper, adaptive crawling.
        -   Follows internal links and navigates pagination (e.g., for job listings).
        -   Uses heuristics to detect anti-bot measures (captchas, blocking).
        -   Retries with visible (non-headless) browsers if blocking is detected.
-   **Browser Isolation**: Each URL gets its own `AsyncWebCrawler` instance. This prevents shared config mutation across concurrent crawl tasks — a critical fix for safe parallelism.
-   **Proxy Rotation**: The `ProxyRotator` class manages Webshare proxies:
    -   **API mode**: Fetches up to 100 proxies from Webshare's API and round-robins through them.
    -   **Direct mode**: Uses a single rotating proxy endpoint.
    -   Proxies are injected into each crawler via `BrowserConfig(proxy_config=...)`.
    -   Fully opt-in: if no proxy env vars are set, crawling works directly.
-   **Memory**: Uses `MemoryStore` to track domain reputation (e.g., "this domain blocks headless browsers").

#### Synthesis Agent (`anyscrape/agents/synthesis_agent.py`)
-   **Role**: Answer Generation.
-   **Tools**: LLM (OpenAI GPT-4o-mini by default).
-   **Logic**:
    -   Ingests the raw markdown content extracted by the Crawl Agent (first 4000 chars per page).
    -   Synthesizes a coherent, markdown-formatted answer to the user's original query.
    -   Chooses output format based on query type: tables for comparisons, numbered lists for instructions, sections with headings for explanations.
    -   Generates citations and references to source URLs.
-   **Async**: `asynthesize()` uses the async LLM client.

### 3. Shared Services

#### LLM Agent (`anyscrape/llm.py`)
-   Thin wrapper around OpenAI chat completions.
-   Maintains both a sync (`OpenAI`) and async (`AsyncOpenAI`) client.
-   `complete()` — Synchronous, used by the CLI path.
-   `acomplete()` — Async, used by the web API path. Does not block the event loop.

#### Configuration (`anyscrape/config.py`)
-   Loads settings from environment variables (`.env`).
-   Manages API keys, operational parameters (concurrency, model selection), and proxy credentials.

#### Memory Store (`anyscrape/memory_store.py`)
-   A persistent JSON-based store (`anyscrape/memory.json`).
-   Tracks historical performance and behavior of domains (e.g., success rates, blocking frequency).
-   Thread-safe with `threading.Lock`.
-   Batched writes: saves to disk at most once every 5 seconds to reduce I/O contention under concurrent requests. Provides a `flush()` method for explicit saves.

#### Proxy Rotator (`anyscrape/agents/crawl_agent.py`)
-   Lazy-loads proxies on first use from Webshare API or direct config.
-   Shuffles the proxy list and round-robins through them.
-   Each `_crawl_single` call gets the next proxy, ensuring IP diversity across concurrent crawls.

### 4. Web API (`anyscrape/web_app.py`)
-   FastAPI application with three endpoints: `GET /` (landing), `GET /health`, `POST /query`.
-   Initializes a single `AnyScrapeOrchestrator` at startup.
-   Error handling: catches pipeline exceptions and returns structured JSON error responses instead of raw 500s.
-   Concurrency is managed by the orchestrator's semaphore — excess requests queue up rather than overwhelming resources.

## Data Flow

1.  **Input**: User provides a natural language query via CLI or HTTP API.
2.  **Search**: Search Agent returns a list of `SearchResult` objects.
3.  **Decision**: Decision Agent returns a filtered `DecisionOutput` (selected + skipped URLs).
4.  **Crawl**: Crawl Agent visits URLs (each with its own browser + proxy) and returns `PageContent` objects (HTML & Markdown).
5.  **Synthesis**: Synthesis Agent processes `PageContent` and produces a `ConsolidatedAnswer`.
6.  **Output**: JSON or Markdown output to stdout (CLI) or HTTP response (API).

## Concurrency Model

```
Request 1 ──┐
Request 2 ──┤  Semaphore (max 5)    Per-URL Browser Isolation
Request 3 ──┼──────────────────► Each URL gets its own AsyncWebCrawler
Request 4 ──┤                    + rotated proxy from ProxyRotator
Request 5 ──┘                    + asyncio.Semaphore for crawl concurrency

Request 6 ──► queued until a slot opens
```

- **Web API**: All LLM calls use `AsyncOpenAI` (non-blocking). DuckDuckGo search runs in a thread via `asyncio.to_thread`.
- **CLI**: Uses synchronous clients directly. Crawling still uses async internally via `asyncio.run`.
