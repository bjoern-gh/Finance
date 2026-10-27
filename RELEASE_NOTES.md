# Release Notes — Version 1.6.0

**Release Date:** October 27, 2026  
**Build:** v1.6.0  
**Test Suite:** 132 passing tests (`0.51s`)  
**Code Quality:** 0 Ruff violations (Ruff 0.17+)  
**Compatibility:** Python 3.11–3.13, Streamlit 1.31+, FastAPI 0.108+  

---

## Executive Summary

Version 1.6.0 is a maintenance and stability release focused on code quality, clean logging, upstream warning mitigation, and dependency reliability. It eliminates all 40 `ruff` lint violations across the codebase, suppresses noisy internal `Pandas4Warning` deprecations originating from `yfinance` operations on pandas 3.1+, and improves Streamlit startup and auth logging.

---

## Key Highlights & Improvements

### 1. Zero-Warning Clean Console Experience
- **Upstream Deprecation Suppression**: Intercepted and filtered `Pandas4Warning` and `DeprecationWarning` triggered by `yfinance` internal `.sort_index(inplace=True)`, `.set_index(..., inplace=True)`, and `.drop(..., inplace=True)` methods on pandas 3.1+.
- **Clean Streamlit CLI Startup**: Added `watchdog` to production dependencies in `pyproject.toml`, resolving macOS filesystem watcher warnings on `streamlit run`.
- **Deduplicated Auth Notice**: Guarded the fallback development authentication warning so it alerts only once per process rather than repeating on every UI rerun.

### 2. Full Linter Compliance & Code Quality
- **Ruff Compliance**: Resolved all 40 lint violations across `agent.py`, `financial_analyzer.py`, `main.py`, and `streamlit_app.py`.
- **Structured Module Logging (`LOG015`)**: Transitioned from global root logger calls (`logging.info`, `logging.warning`, etc.) to dedicated module loggers (`logging.getLogger(__name__)`).
- **Robust Exception Handling (`BLE001`, `S110`, `G201`, `TRY401`)**: Replaced blind `except Exception:` blocks with structured exception logging (`logger.exception` and `exc_info=True`), and narrowed file-parsing exceptions in `streamlit_app.py`.
- **Simplified Branch Logic (`SIM102`)**: Combined nested conditional checks in Streamlit action handlers into clean single-line `if ... and ...:` conditions.

### 3. Dependency Alignment
- Added `watchdog>=6.0.0` and `openai>=3.39.0` directly to `pyproject.toml` dependencies.
- Updated `uv.lock` to reflect version 1.6.0.

---

# Release Notes — Version 1.5.0

**Release Date:** October 20, 2026  
**Build:** v1.5.0  
**Test Suite:** 132 passing tests (`0.52s`)  
**Compatibility:** Python 3.11+, Streamlit 1.31+ (optimized for 1.60+), FastAPI 0.108+  

---

## Executive Summary

Version 1.5.0 enhances the presentation layer of the Financial Analysis application with intelligent, automatic number formatting across Streamlit pandas DataFrames and metric card components. All floating-point and currency metrics default to 2 decimal places, while Target Upside displays as a clean whole integer percentage without decimal separators.

---

## Key Highlights & Improvements

### 1. Automatic Default Number Formatting for Streamlit DataFrames
- **2-Decimal Standard (`%.2f`)**: Floating-point values (e.g. `Price`, `SMA200`, `SMA50`, `RSI`, `P/E (KGV)`, `52W High (%)`, `52W Low (%)`, `Beta`, `Dividend Yield (%)`, `Target Price`) are automatically formatted to two decimal digits (e.g., `1.20` instead of `1.200000`).
- **Target Upside as Full Percentage (`%.0f%%`)**: Target Upside is automatically formatted as a whole integer percentage without decimal separator (e.g., `16%` or `-3%` instead of `15.60%` or `15.600000`).
- **Integer Clarity (`%.0f`)**: Integer values (such as `Buy Score`) maintain clean whole-number formatting.
- **Native Column Configuration**: Introduced `get_column_config(df)` leveraging Streamlit's native `st.column_config.NumberColumn` for both Buying Opportunities and Full Portfolio Analysis tables.

### 2. UI-Only Scope & Data Integrity
- **Calculation Precision Preserved**: Underlying raw float data remains unmodified in backend processing, sorting algorithms, and Excel/CSV exports.
- **Unified Styler Integration**: `style_dataframe` sets baseline Styler formatting (`precision=2`, `na_rep="-"`) and dedicated Target Upside formatting alongside cell background and text color rules.

### 3. Metric Cards Harmonization
- Aligned `Current Price`, `Target Upside`, and 52W range metrics in Opportunity Dossiers and Charts with 2-decimal and whole-percentage display conventions.

### 4. Expanded Test Suite
- Added dedicated test suite `tests/test_ui_formatting.py` covering formatting helpers, column configurations, Styler outputs, and missing/null values.
- Total test suite expanded to **132 passing tests** (100% passing in 0.52s).

---

## Upgrade & Migration Notes

- **Zero Breaking Changes**: All public interfaces in `financial_analyzer`, `portfolio_manager`, `api.py`, and `streamlit_app.py` maintain full backward compatibility.
- **Automatic Behavior**: No configuration changes required; formatting is enabled automatically on table and metric rendering.
