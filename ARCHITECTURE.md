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

### 2. Agents

#### Search Agent (`anyscrape/agents/search_agent.py`)
-   **Role**: Discover information sources.
-   **Tools**: `ddgs` (DuckDuckGo Search).
-   **Logic**:
    -   Performs a web search based on the user's query.
    -   Retrieves titles, URLs, and snippets.
    -   Optionally re-ranks results using an LLM to prioritize relevance.

#### Decision Agent (`anyscrape/agents/decision_agent.py`)
-   **Role**: Selection and Filtering.
-   **Logic**:
    -   Analyzes the ranked search results.
    -   Decides which URLs are most likely to contain the answer.
    -   Filters out irrelevant or low-quality links before crawling to save resources.

#### Crawl Agent (`anyscrape/agents/crawl_agent.py`)
-   **Role**: Content Extraction.
-   **Tools**: `crawl4ai` (AsyncWebCrawler, AdaptiveCrawler).
-   **Modes**:
    -   **Fast Mode**: Concurrently crawls selected URLs with a global timeout. Best for quick answers.
    -   **Comprehensive Mode**:
        -   Performs deeper, adaptive crawling.
        -   Follows internal links and navigates pagination (e.g., for job listings).
        -   Uses heuristics to detect anti-bot measures (captchas, blocking).
        -   Retries with visible (non-headless) browsers if blocking is detected.
-   **Memory**: Uses `MemoryStore` to track domain reputation (e.g., "this domain blocks headless browsers").

#### Synthesis Agent (`anyscrape/agents/synthesis_agent.py`)
-   **Role**: Answer Generation.
-   **Tools**: LLM (OpenAI GPT-4o-mini by default).
-   **Logic**:
    -   Ingests the raw markdown content extracted by the Crawl Agent.
    -   Synthesizes a coherent, markdown-formatted answer to the user's original query.
    -   Generates citations and references to source URLs.

### 3. Shared Services

#### Configuration (`anyscrape/config.py`)
-   Loads settings from environment variables (`.env`).
-   Manages API keys and operational parameters (concurrency, model selection).

#### Memory Store (`anyscrape/memory_store.py`)
-   A persistent JSON-based store (`anyscrape/memory.json`).
-   Tracks historical performance and behavior of domains (e.g., success rates, blocking frequency).

## Data Flow

1.  **Input**: User provides a natural language query via CLI.
2.  **Search**: Search Agent returns a list of `SearchResult` objects.
3.  **Decision**: Decision Agent returns a filtered list of URLs to crawl.
4.  **Crawl**: Crawl Agent visits URLs and returns `PageContent` objects (HTML & Markdown).
5.  **Synthesis**: Synthesis Agent processes `PageContent` and produces a `SynthesisResult`.
6.  **Output**: JSON or Markdown output to stdout.
