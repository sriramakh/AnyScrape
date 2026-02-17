try:
    import ddgs
    print(f"ddgs version: {ddgs.__version__}")
    print(dir(ddgs))
except ImportError:
    print("ddgs not found")

try:
    import duckduckgo_search
    print(f"duckduckgo_search version: {duckduckgo_search.__version__}")
except ImportError:
    print("duckduckgo_search not found")
