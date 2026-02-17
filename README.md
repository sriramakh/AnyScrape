# AnyScrape

AnyScrape is a powerful, autonomous multi-agent web scraping and research pipeline. It leverages LLMs and advanced crawling capabilities to search the web, intelligently select relevant sources, navigate through content, and synthesize comprehensive answers to user queries.

## Features

- **Multi-Agent Architecture**: Orchestrates specialized agents for searching, decision-making, crawling, and synthesis.
- **Intelligent Search**: Uses DuckDuckGo (via `ddgs`) to find relevant web pages.
- **Adaptive Crawling**:
  - **Fast Mode**: Quick extraction of content from top results.
  - **Comprehensive Mode**: Deep adaptive crawling that follows links and explores domains to find specific information (e.g., job listings, news).
- **Anti-Bot Evasion**: Automatically detects blocking (CAPTCHAs, 403s) and retries with visible browsers or different strategies.
- **LLM Synthesis**: Consolidates gathered information into structured, markdown-formatted answers with citations.
- **CLI Interface**: Simple command-line interface for easy interaction.
- **Web API**: FastAPI-based HTTP API so you can call AnyScrape from any machine or service.

## Prerequisites

- Python 3.10+
- OpenAI API Key (or compatible LLM API key)

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/anyscrape.git
    cd anyscrape
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    playwright install  # Required for crawl4ai
    ```

4.  **Set up environment variables:**
    Create a `.env` file in the root directory:
    ```env
    OPENAI_API_KEY=your_openai_api_key_here
    # Optional settings:
    # ANYSCRAPE_MODEL=gpt-4o-mini
    # ANYSCRAPE_MAX_RESULTS=5
    # ANYSCRAPE_MAX_CRAWL_CONCURRENCY=3
    # ANYSCRAPE_HEADLESS_DEFAULT=true
    ```

## Usage (Local)

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

You can also run AnyScrape as an HTTP API using FastAPI.

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

### Docker (CLI and API)

Build the image:

```bash
docker build -t anyscrape:latest .
```

Run as CLI (default entrypoint):

```bash
docker run --rm --env-file .env anyscrape:latest \
  "what are the job listings in walmart" --mode fast --verbose
```

Run as Web API:

```bash
docker run --rm -p 8000:8000 --env-file .env \
  --entrypoint uvicorn anyscrape:latest \
  anyscrape.web_app:app --host 0.0.0.0 --port 8000
```

## Configuration

| Environment Variable | Description | Default |
|----------------------|-------------|---------|
| `OPENAI_API_KEY` | Required. API key for LLM. | - |
| `ANYSCRAPE_MODEL` | LLM model to use. | `gpt-4o-mini` |
| `ANYSCRAPE_MAX_RESULTS` | Max search results to process. | `5` |
| `ANYSCRAPE_MAX_CRAWL_CONCURRENCY` | Max concurrent crawl tasks. | `3` |
| `ANYSCRAPE_HEADLESS_DEFAULT` | Run browser in headless mode. | `true` |

## License

MIT
