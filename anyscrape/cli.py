from __future__ import annotations

import argparse
import json
from typing import Any

from dotenv import load_dotenv

from .logging_utils import configure_logging
from .orchestrator import run_query_sync


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="AnyScrape: multi-agent web scraping prototype (internal testing)."
    )
    parser.add_argument(
        "query",
        nargs="+",
        help="Search query to answer (e.g. 'samsung refrigerator price on amazon').",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON response instead of formatted markdown.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show step-by-step logs of how the agents and models are working.",
    )
    parser.add_argument(
        "--mode",
        choices=["fast", "comprehensive"],
        default="fast",
        help=(
            "Crawl mode: 'fast' (under ~45s crawl phase, shallower) or "
            "'comprehensive' (deeper, slower, uses adaptive crawling)."
        ),
    )

    args = parser.parse_args()
    query = " ".join(args.query)

    # Configure logging before running the pipeline so that step-by-step
    # progress is visible while the agents work.
    configure_logging(verbose=args.verbose)

    result: dict[str, Any] = run_query_sync(query, mode=args.mode)  # type: ignore[arg-type]

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("# Answer\n")
        print(result["answer_markdown"])
        print("\n\n# Sources\n")
        for s in result["sources"]:
            title = s.get("title") or s["url"]
            print(f"- {title} ({s['url']})")


if __name__ == "__main__":
    main()
