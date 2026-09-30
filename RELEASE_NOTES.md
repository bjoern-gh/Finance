# Release Notes — Version 1.4.0

**Release Date:** September 30, 2026  
**Build:** v1.4.0  
**Test Suite:** 115 passing tests (`0.37s`)  
**Compatibility:** Python 3.11+, Streamlit 1.31+ (optimized for 1.60+), FastAPI 0.108+  

---

## Executive Summary

Version 1.4.0 represents a major architectural review and refactoring of the Financial Analysis application. This release focuses on high-performance concurrency for batch stock analysis, rock-solid portfolio storage, unified backend services across all interfaces (Streamlit, REST API, Agent tools), modern Streamlit UI components, and complete test suite expansion.

---

## Key Highlights & Improvements

### 1. Concurrent Batch Analysis (5–10x Speedup)
- **Parallel Fetching**: Upgraded `financial_analyzer.analyze_tickers` to run asynchronously using `concurrent.futures.ThreadPoolExecutor`, dynamically allocating workers from `config.ini` (`max_workers = 10`).
- **Deterministic Ordering**: Analysis results strictly preserve input watchlist ordering before applying user-configured sort criteria.
- **Thread-Safe FX Caching**: In-memory foreign exchange rates cache (`_eur_rate_cache`) is now protected with a `threading.Lock` to guarantee safe concurrent reads/writes across worker threads.

### 2. Service Unification & Bug Fixes
- **Unified Company Search**: Extracted and standardized `search_company(query)` into `financial_analyzer.py`. Streamlit UI, Agent tools, and the REST API now share a single implementation without duplicate network logic.
- **Fixed `tools.py`**: Resolved a critical `ImportError` where `tools.py` attempted to import `search_company` from `financial_analyzer` before it was defined there.
- **Complete Agent Toolset**: Implemented missing tool stubs (`get_portfolio_info`, `run_bulk_analysis`) and registered all 7 tool functions inside `FinancialAgent` in `agent.py` with robust exception handling.
- **FastAPI Search Route**: Added `GET /search?q={query}` endpoint to `api.py` for programmatic access to company lookups.

### 3. Hardened Portfolio Storage
- **Atomic File Writing**: `portfolio_manager.save_portfolio` now writes to a temporary swap file before atomically renaming, preventing file corruption or truncation in the event of power loss or process termination.
- **Resilient JSON Recovery**: `portfolio_manager.load_portfolio` catches corrupted or empty JSON files and recovers gracefully with an empty portfolio rather than crashing the application.
- **Security**: Added strict path sanitization (`_safe_path`) preventing directory traversal attacks via malicious portfolio names.

### 4. Modern Streamlit UI Experience
- **Material Symbols**: Refreshed UI iconography with modern Material Symbols (`:material/folder:`, `:material/trending_up:`, `:material/search:`, `:material/analytics:`, `:material/show_chart:`, `:material/download:`, etc.).
- **Card-Style Containers**: Encapsulated Search & Add, Import, Current Watchlist, and Export/Import modules in clean bordered containers (`st.container(border=True)`).
- **Segmented Period Control**: Replaced legacy dropdown in the Charts tab with native interactive `st.segmented_control`.
- **Clean Layout**: Removed all raw HTML `<br>` breaks in favor of native Streamlit layout and vertical spacing.

### 5. Expanded Test Suite & Quality Assurance
- **+26 New Unit Tests**: Test suite increased from 89 to **115 passing tests** executing in **0.37s**:
  - `tests/test_portfolio_manager.py`: CRUD operations, atomic writes, corruption recovery, invalid arguments.
  - `tests/test_analyze_tickers.py`: Sequential and multi-threaded batch execution, sorting rules, ticker ordering.
  - `tests/test_tools.py`: Tool wrappers and search logic with full mocking.
  - `tests/test_api.py`: FastAPI endpoints (`/`, `/search`, `/analyze`).
  - `tests/test_agent.py`: Agent execution and tool-calling loop.
- **Linter Clean**: 100% compliant with Ruff (`uv run ruff check .` passes with 0 warnings/errors).

---

## Upgrade & Migration Notes

- **Zero Breaking Changes**: All public interfaces in `financial_analyzer`, `portfolio_manager`, `api.py`, and `streamlit_app.py` maintain full backward compatibility.
- **Configuration**: Existing `config.ini` files require no changes; `max_workers = 10` is now actively utilized.
