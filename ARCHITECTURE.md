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
    -   Configures agents based on mode (fast vs comprehensive) before each run.
-   **Concurrency**: A global semaphore (default: 5) limits how many queries run the full pipeline in parallel, preventing resource exhaustion under load.
-   **Dual paths**:
    -   `run_query()` — Fully async path used by the web API. All LLM calls use `AsyncOpenAI` and never block the event loop.
    -   `run_query_sync()` — Sync path for CLI usage. Uses the synchronous OpenAI client.

### 2. Agents

#### Search Agent (`anyscrape/agents/search_agent.py`)
-   **Role**: Discover information sources.
-   **Tools**: SearXNG (self-hosted metasearch engine).
-   **Logic**:
    -   Queries a SearXNG instance via its JSON API (`/search?q=...&format=json&categories=general&language=en`).
    -   Aggregates results from multiple search engines (Google, Bing, DuckDuckGo, Brave, Wikipedia) with weighted ranking (Google 2x, DuckDuckGo/Brave 1.5x, Wikipedia 1x, Bing 0.5x).
    -   Paginates automatically to collect the requested number of results (5 for fast, 25 for comprehensive).
    -   Deduplicates URLs across pages.
    -   Re-ranks results using an LLM to prioritize relevance.
-   **Async**: `async_web_search()` runs the blocking HTTP call in a thread via `asyncio.to_thread`. `arank_relevance()` uses the async LLM client.

#### Decision Agent (`anyscrape/agents/decision_agent.py`)
-   **Role**: Selection and Filtering.
-   **Logic**:
    -   Analyzes the ranked search results.
    -   Deduplicates URLs using canonicalized keys.
    -   Uses domain memory to bias selection toward historically successful domains.
    -   Decides which URLs are most likely to contain the answer via LLM.
    -   Filters out irrelevant or low-quality links before crawling to save resources.
-   **Mode-aware**: Selects up to 5 URLs in fast mode, up to 25 in comprehensive mode.
-   **Async**: `aselect_for_crawling()` uses the async LLM client.

#### Crawl Agent (`anyscrape/agents/crawl_agent.py`)
-   **Role**: Content Extraction.
-   **Tools**: `crawl4ai` (AsyncWebCrawler, AdaptiveCrawler).
-   **Modes**:
    -   **Fast Mode**: Concurrently crawls selected URLs with a 45-second global timeout. Best for quick answers.
    -   **Comprehensive Mode**:
        -   Performs deeper, adaptive crawling.
        -   Follows internal links and navigates pagination (e.g., for job listings).
        -   No global timeout — allows full exploration.
-   **Anti-Bot Detection** (`_looks_blocked`):
    -   **Markdown-vs-HTML ratio**: Large HTML (>5KB) with tiny markdown (<200 chars) indicates a JS challenge page.
    -   **Blockage markers**: Scans both markdown and raw HTML for 18+ known patterns including `just a moment`, `cloudflare`, `ray id`, `captcha`, `security check`, `perimeter x`, `are you a robot`, `checking your browser`, etc.
    -   **Small HTML heuristic**: Pages under 2KB with no doctype are flagged.
    -   **Automatic retry**: Blocked pages are retried with `headless=False` (visible browser via xvfb on VPS).
-   **Browser Isolation**: Each URL gets its own `AsyncWebCrawler` instance. This prevents shared config mutation across concurrent crawl tasks — a critical fix for safe parallelism.
-   **Proxy Rotation**: The `ProxyRotator` class manages Webshare proxies:
    -   **API mode**: Fetches up to 100 proxies from Webshare's API and round-robins through them.
    -   **Direct mode**: Uses a single proxy endpoint with separate server/username/password fields.
    -   Proxies are injected into each crawler via `BrowserConfig(proxy_config=...)`.
    -   Fully opt-in: if no proxy env vars are set, crawling works directly.
-   **Memory**: Uses `MemoryStore` to track domain reputation (e.g., "this domain blocks headless browsers").

#### Synthesis Agent (`anyscrape/agents/synthesis_agent.py`)
-   **Role**: Answer Generation.
-   **Tools**: LLM (OpenAI GPT-4o-mini by default).
-   **Logic**:
    -   Ingests the raw markdown content extracted by the Crawl Agent.
    -   Synthesizes a coherent, markdown-formatted answer to the user's original query.
    -   Chooses output format based on query type: tables for comparisons, numbered lists for instructions, sections with headings for explanations.
    -   Generates citations and references to source URLs.
-   **Mode-aware limits**:
    -   Fast: 4,000 chars/page, 1,200 max output tokens.
    -   Comprehensive: 20,000 chars/page, 6,000 max output tokens.
-   **Async**: `asynthesize()` uses the async LLM client.

### 3. Shared Services

#### LLM Agent (`anyscrape/llm.py`)
-   Thin wrapper around OpenAI chat completions.
-   Maintains both a sync (`OpenAI`) and async (`AsyncOpenAI`) client.
-   `complete()` — Synchronous, used by the CLI path.
-   `acomplete()` — Async, used by the web API path. Does not block the event loop.

#### Configuration (`anyscrape/config.py`)
-   Loads settings from environment variables (`.env`).
-   Manages API keys, operational parameters (concurrency, model selection), proxy credentials, and SearXNG URL.

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

### 5. Docker & Deployment

#### Dockerfile
-   Based on `python:3.11-slim-bookworm`.
-   Installs `xvfb` for virtual framebuffer support — enables `headless=False` browser retries on servers without a physical display.
-   Starts `Xvfb :99` in the background before launching uvicorn.
-   Sets `DISPLAY=:99` so Playwright finds the virtual display.

#### Docker Compose (`docker-compose.yml`)
-   **searxng** service: Runs `searxng/searxng:latest` on port 8888, with custom settings (weighted engines, rate limiting disabled, JSON format enabled).
-   **anyscrape** service: Builds from Dockerfile, connects to SearXNG via Docker internal DNS (`http://searxng:8080`), exposes API on port 8081.

#### SearXNG Configuration (`searxng/`)
-   `settings.yml`: Enables JSON format, configures engine weights (Google 2x > DuckDuckGo/Brave 1.5x > Wikipedia 1x > Bing 0.5x), disables rate limiting.
-   `limiter.toml`: Disables bot detection for internal API usage.

## Data Flow

1.  **Input**: User provides a natural language query via CLI or HTTP API.
2.  **Search**: Search Agent queries SearXNG and returns a list of `SearchResult` objects.
3.  **Decision**: Decision Agent returns a filtered `DecisionOutput` (selected + skipped URLs).
4.  **Crawl**: Crawl Agent visits URLs (each with its own browser + proxy) and returns `PageContent` objects (HTML & Markdown). Blocked pages are detected and retried with visible browsers.
5.  **Synthesis**: Synthesis Agent processes `PageContent` and produces a `ConsolidatedAnswer`.
6.  **Output**: JSON or Markdown output to stdout (CLI) or HTTP response (API).

## Mode Comparison

| Parameter | Fast | Comprehensive |
|-----------|------|---------------|
| Search results | 5 | 25 |
| Max URLs to crawl | 5 | 25 |
| Content per page | 4,000 chars | 20,000 chars |
| Synthesis max tokens | 1,200 | 6,000 |
| Crawl timeout | 45 seconds | No limit |
| Adaptive crawling | No | Yes |

## Anti-Bot Detection Flow

```
Crawl URL (headless=True)
  │
  ├── Success + content looks real → Return page
  │
  └── Blocked detected?
      ├── Markdown < 200 chars but HTML > 5KB → Blocked (JS challenge)
      ├── Contains "cloudflare", "captcha", etc. → Blocked (bot wall)
      └── HTML < 2KB, no doctype → Blocked (empty response)
          │
          ▼
      Retry with headless=False (visible browser via xvfb)
          │
          ├── Success → Return page + record headless_block_event
          └── Still blocked → Return best attempt + record blocked_count
```

## Concurrency Model

```
Request 1 ──┐
Request 2 ──┤  Semaphore (max 5)    Per-URL Browser Isolation
Request 3 ──┼──────────────────► Each URL gets its own AsyncWebCrawler
Request 4 ──┤                    + rotated proxy from ProxyRotator
Request 5 ──┘                    + asyncio.Semaphore for crawl concurrency

Request 6 ──► queued until a slot opens
```

- **Web API**: All LLM calls use `AsyncOpenAI` (non-blocking). SearXNG search runs in a thread via `asyncio.to_thread`.
- **CLI**: Uses synchronous clients directly. Crawling still uses async internally via `asyncio.run`.
- **VPS**: Docker container runs xvfb virtual framebuffer so `headless=False` retries work without a physical display.
