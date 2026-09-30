# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-09-30

### Added
- **Multi-threaded Batch Analysis**:
  - Implemented parallel execution in `financial_analyzer.analyze_tickers` using `concurrent.futures.ThreadPoolExecutor` and `max_workers` from `config.ini`, delivering ~5-10x performance improvement for large portfolios.
  - Added thread-safe synchronization for the in-memory FX rates cache (`_eur_rate_cache`) with `threading.Lock`.
- **Backend Service Unification**:
  - Moved `search_company` to `financial_analyzer.py` as a shared core service used by Streamlit, FastAPI, and Agent tools.
  - Added `/search` REST endpoint in `api.py`.
- **Tooling & Agent Capabilities**:
  - Fixed broken `search_company` import in `tools.py`.
  - Implemented `get_portfolio_info` and `run_bulk_analysis` tool functions.
  - Registered all tool definitions in `agent.py` and improved error handling during tool execution.
- **Robust Storage**:
  - Added atomic file write operations in `portfolio_manager.py` using temporary swap files.
  - Implemented graceful error recovery for corrupted or empty JSON portfolio files.
  - Added path traversal protection for portfolio names.
- **Expanded Test Suite**:
  - Increased unit test coverage from 89 to 115 tests.
  - Added test suites for portfolio manager (`test_portfolio_manager.py`), batch analysis concurrency (`test_analyze_tickers.py`), agent and tools (`test_tools.py`, `test_agent.py`), and FastAPI routes (`test_api.py`).

### Changed
- **Streamlit Modernization**:
  - Modernized UI layout with Material Symbols icons (`:material/...:`).
  - Adopted bordered container grouping (`st.container(border=True)`) across search, import, portfolio list, and export views.
  - Replaced period dropdown in charts with Streamlit's native `st.segmented_control`.
  - Removed raw HTML line break hacks in favor of native Streamlit spacing.

---

## [1.3.0] - 2026-08-10

### Added
- **Business Model Categorization & Filtering**:
  - Added automatic detection and classification for company business models (e.g., distinguishing non-operating **Royalty & Streaming** companies like Franco-Nevada, Wheaton Precious Metals, Vox Royalties, Triple Flag from **Operating Miners** and general operating companies).
  - Added interactive filtering by Business Model in the Streamlit UI.
  - Added comprehensive test suite coverage (89 tests) for metric calculations, valuation rules, and business model categorization.
- **Agentic AI Integration (Proof of Concept)**:
  - Introduced `agent.py` and `tools.py` providing LLM agent capabilities and tool definitions for financial analysis.
  - Added custom Streamlit development skill (`.agents/skills/developing-with-streamlit`).
- **Modern `uv` Development Environment**:
  - Integrated `pyproject.toml` configuration using `hatchling` build backend and defined dev dependencies (`black`, `pytest`, `pytest-mock`, `ruff`).
  - Added reproducible lockfile `uv.lock`.

### Changed
- Refined valuation and sorting rules for financial indicators (positive lowest P/E / KGV ranked first, extended buying opportunities logic).
- Updated documentation and project structure representation in `README.md`.

---

## [1.2.0] - 2026-07-23

### Added
- Standardized `uv` virtual environment setup and project tooling configuration (`pyproject.toml`).
- Extended valuation classification logic (Cheap and Very Cheap buying opportunities).

### Changed
- Adjusted sorting algorithm to rank positive lowest KGV first.

---

## [1.1.0] - 2026-07-17

### Fixed
- **Segmentation Fault Fix (Python 3.14 + PyArrow Conflict)**:
  - Resolved mimalloc memory allocator conflict between Python 3.14 and PyArrow by setting `ARROW_DEFAULT_MEMORY_POOL=system` across entry points (`streamlit_app.py`, `financial_analyzer.py`, `conftest.py`) and `.venv/bin/activate`.
- **Sort Column Warning & Data Mutation Fix**:
  - Resolved `WARNING - Sort column 'KGV' not found` by implementing alias mapping (mapping "KGV", "PE", "P/E" to `"P/E (KGV)"`).
  - Fixed non-destructive sorting logic so sorting by text columns (e.g. Company, Sector) no longer converts strings to `NaN`.

### Added
- Added `Changelog.md` and contributing guidelines in `README.md`.
