# AnyScrape

AnyScrape is a powerful, autonomous multi-agent web scraping and research pipeline. It leverages LLMs and advanced crawling capabilities to search the web, intelligently select relevant sources, navigate through content, and synthesize comprehensive answers to user queries.

## Features

- **Multi-Agent Architecture**: Orchestrates specialized agents for searching, decision-making, crawling, and synthesis.
- **SearXNG Search**: Uses a self-hosted SearXNG metasearch engine that aggregates results from Google, Bing, DuckDuckGo, Brave, and Wikipedia — with weighted engine ranking for high-quality results.
- **Adaptive Crawling**:
  - **Fast Mode**: Quick extraction of content from top results (5 search results, 5 URLs, 4K chars/page, 1200 max tokens).
  - **Comprehensive Mode**: Deep adaptive crawling with 5x the limits (25 search results, 25 URLs, 20K chars/page, 6000 max tokens).
- **Anti-Bot Evasion**: Detects Cloudflare, CAPTCHA, PerimeterX, and other bot walls using content heuristics (blockage markers + markdown-vs-HTML ratio analysis). Automatically retries blocked pages with visible browsers via xvfb virtual display.
- **Proxy IP Rotation**: Built-in Webshare proxy support to rotate IPs and avoid rate limiting or geo-blocks.
- **LLM Synthesis**: Consolidates gathered information into structured, markdown-formatted answers with citations.
- **Fully Async Pipeline**: Non-blocking async LLM calls and per-URL browser isolation for safe concurrent request handling.
- **VPS-Ready**: Docker image includes xvfb for headless=False browser retries on servers without a display.
- **CLI Interface**: Simple command-line interface for easy interaction.
- **Web API**: FastAPI-based HTTP API with concurrency controls and error handling.

## Prerequisites

- Python 3.10+
- Docker & Docker Compose (for SearXNG and production deployment)
- OpenAI API Key (or compatible LLM API key)

## Quick Start (Docker Compose)

The easiest way to run AnyScrape with SearXNG:

```bash
git clone https://github.com/sriramakh/AnyScrape.git
cd AnyScrape
cp .env.example .env   # Edit with your API keys
docker compose up -d
```

This starts:
- **SearXNG** on port `8888` (metasearch engine)
- **AnyScrape API** on port `8081` (connected to SearXNG internally, with xvfb for anti-bot retries)

```bash
curl -X POST http://localhost:8081/query \
  -H "Content-Type: application/json" \
  -d '{"query": "top AI startups in 2026", "mode": "fast"}'
```

## Manual Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/sriramakh/AnyScrape.git
    cd AnyScrape
    ```

2.  **Start SearXNG:**
    ```bash
    docker compose up -d searxng
    ```

3.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    playwright install  # Required for crawl4ai
    ```

5.  **Set up environment variables:**
    Create a `.env` file in the root directory:
    ```env
    OPENAI_API_KEY=your_openai_api_key_here
    SEARXNG_BASE_URL=http://localhost:8888
    ```

6.  **(VPS only) Install xvfb** for anti-bot browser retries:
    ```bash
    sudo apt-get install -y xvfb
    Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
    export DISPLAY=:99
    ```

## Usage (CLI)

Run the CLI using `python -m anyscrape.cli` (or the `anyscrape` command if installed as a package):

### Basic Search
```bash
python -m anyscrape.cli "what are the job listings in walmart" --verbose
```

### Comprehensive Search (Deep Crawl)
Use `--mode comprehensive` for tasks requiring deeper navigation (e.g., finding specific job postings, aggregating news):
```bash
python -m anyscrape.cli "Fetch latest 10 engineering jobs at tredence" --mode comprehensive --verbose
```

### JSON Output
Get raw JSON output for integration with other tools:
```bash
python -m anyscrape.cli "Top AI news this week" --json
```

## Web API Server

You can also run AnyScrape as an HTTP API using FastAPI. The API supports concurrent requests with built-in concurrency limits (max 5 parallel pipelines) and proper error handling.

### Local (uvicorn)

```bash
uvicorn anyscrape.web_app:app --host 0.0.0.0 --port 8000
```

Then call it from any machine that can reach the host:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "what are the job listings in walmart", "mode": "fast"}'
```

### Docker Compose (recommended)

```bash
docker compose up -d
```

This runs both SearXNG and AnyScrape. The API is available on port `8081`. The AnyScrape container includes xvfb so anti-bot browser retries work on headless servers.

## Configuration

| Environment Variable | Description | Default |
|----------------------|-------------|---------|
| `OPENAI_API_KEY` | Required. API key for LLM. | - |
| `SEARXNG_BASE_URL` | Required. URL of your SearXNG instance. | - |
| `ANYSCRAPE_MODEL` | LLM model to use. | `gpt-4o-mini` |
| `ANYSCRAPE_MAX_RESULTS` | Max search results to process (fast mode). | `5` |
| `ANYSCRAPE_MAX_CRAWL_CONCURRENCY` | Max concurrent crawl tasks. | `3` |
| `ANYSCRAPE_HEADLESS_DEFAULT` | Run browser in headless mode. | `true` |

### Proxy Configuration (Webshare)

AnyScrape supports IP rotation via Webshare proxies to avoid blocks and rate limits. Configure using one of two methods:

**Option A — Webshare API key** (auto-fetches your full proxy list):
| Environment Variable | Description |
|----------------------|-------------|
| `WEBSHARE_API_KEY` | Your Webshare API token. Fetches up to 100 proxies automatically. |

**Option B — Direct proxy endpoint**:
| Environment Variable | Description |
|----------------------|-------------|
| `WEBSHARE_PROXY_HOST` | Proxy IP or hostname (e.g., `171.22.248.219`). |
| `WEBSHARE_PROXY_PORT` | Proxy port (e.g., `6111`). |
| `WEBSHARE_PROXY_USERNAME` | Proxy auth username. |
| `WEBSHARE_PROXY_PASSWORD` | Proxy auth password. |

If no proxy variables are set, AnyScrape crawls directly without a proxy.

## Anti-Bot Detection

AnyScrape uses a multi-layered approach to detect and bypass bot protection:

1. **Markdown-vs-HTML ratio check** — If a page returns large HTML but near-zero markdown, it's likely a JS challenge page (Cloudflare, PerimeterX, etc.).
2. **Blockage marker detection** — Scans both markdown and raw HTML for known patterns: `just a moment`, `cloudflare`, `captcha`, `security check`, `ray id`, `perimeter x`, `are you a robot`, and more.
3. **Small HTML heuristic** — Pages under 2KB with no doctype are flagged as blocked.
4. **Automatic retry** — Blocked pages are retried with `headless=False` (visible browser), which bypasses some bot detection.
5. **Domain memory** — Tracks which domains block headless browsers so future requests use visible mode first.
6. **xvfb on VPS** — Docker image includes a virtual framebuffer so visible browser retries work on headless servers.

## License

MIT
