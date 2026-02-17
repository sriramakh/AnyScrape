from duckduckgo_search import DDGS
import json
import traceback

def test_search():
    queries = ["test", "what are the job listings in walmart"]
    for query in queries:
        print(f"\nTesting search for: {query}")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
                print(f"Found {len(results)} results")
                if results:
                    print(json.dumps(results[0], indent=2))
        except Exception:
            traceback.print_exc()

if __name__ == "__main__":
    test_search()
