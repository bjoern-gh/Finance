# Release Notes — Version 1.8.0

**Release Date:** November 12, 2026  
**Build:** v1.8.0  
**Test Suite:** 159 passing tests (`0.56s`)  
**Code Quality:** 0 Ruff violations (Ruff 0.17+)  
**Compatibility:** Python 3.11–3.13, Streamlit 1.31+ (optimized for 1.66+), FastAPI 0.108+  

---

## Executive Summary

Version 1.8.0 introduces an advanced evaluation suite for raw materials, precious metals, miners, and exploration companies, alongside interactive Simply Wall St style Snowflake radar charts. It integrates Lassonde Curve lifecycle classification (Junior Explorers, Developers, Producers, and Royalty & Streaming), automatic primary commodity exposure detection (Gold, Silver, PGMs, Copper, Uranium, Lithium, etc.), and a cash runway and dilution risk engine tailored specifically for early-stage and pre-revenue resource companies.

---

## Key Highlights & Improvements

### 1. Simply Wall St Style Snowflake Radar Chart
- **Interactive Polar Visualization**: Added `build_snowflake_radar` to render 5-pillar polar charts (Value, Future Growth, Past Performance, Financial Health, Dividend Sustainability; 0–30 scale) with custom hover tooltips, theme-aware palette, and transparent background embedding.
- **Embedded Dossier & Chart Integration**: Visualized directly within Opportunity Dossier cards and the single-stock fundamentals overview in the Charts tab.
- **Progress Column**: Configured Streamlit `st.column_config.ProgressColumn` for Snowflake score in the main results table.

### 2. Lassonde Curve Mining Lifecycle Classification
- **Automated Lifecycle Staging**: Implemented `determine_mining_lifecycle` to classify resource companies along the classic Lassonde Curve:
  - *Junior Explorer*: Discovery and drilling stage, pre-revenue, negative operating cash flows.
  - *Developer*: Defined mineral resources, feasibility studies (PEA/PFS/DFS), permitting, and mine construction.
  - *Producer*: Commercial extraction with significant revenue and positive operational cash flows.
  - *Royalty & Streaming*: Capital providers receiving NSR or metal streams (60–80% cash margins).
- **Recalibrated Snowflake Scoring**: Early-stage explorers are no longer unfairly penalized for lacking P/E multiples or dividends. Health evaluates Cash Runway and Net Cash backing; Value assesses Net Cash % of market cap and analyst target upside.

### 3. Primary Commodity & Mineral Exposure Engine
- **Resource Tagging**: Implemented `determine_primary_commodity` parsing industry, sector, name, and operational summaries to identify primary commodity exposure:
  - *Precious Metals*: Gold ($\text{Au}$), Silver ($\text{Ag}$), PGMs (Platinum, Palladium).
  - *Critical & Energy Transition*: Copper ($\text{Cu}$), Uranium ($\text{U}_3\text{O}_8$), Lithium ($\text{Li}$), Nickel ($\text{Ni}$), Cobalt ($\text{Co}$), Rare Earths ($\text{REE}$), Graphite.
  - *Base & Industrial Metals*: Aluminum, Iron Ore, Zinc & Lead.
  - *Bulks & Energy*: Coal, Potash, and Fertilizers.

### 4. Cash Runway & Dilution Risk Engine
- **Exploration Burn & Runway**: Implemented `calculate_cash_runway` calculating annual cash burn rate, cash runway (months), and Net Cash ($\text{Cash} - \text{Debt}$).
- **Net Cash Backing %**: Calculates Net Cash as a percentage of Market Cap ($\frac{\text{Net Cash}}{\text{Market Cap}} \times 100\%$) to identify deep-value juniors trading near cash value.
- **Automated Dilution Risk Flagging**: Classifies companies into *Low (Cash Flow +)*, *Low (> 36 mos)*, *Moderate (12–36 mos)*, and *High (< 12 mos)*. Injects automated `⚠️ High Dilution Risk` warnings into the composite Buy Score engine for companies facing imminent capital raises.

### 5. Multi-Dimension Filtering & Visual Polish
- **Advanced Resource Filters**: Added multi-select filters across Mining Lifecycle, Commodity / Mineral, Dilution Risk, and Business Model.
- **Resource Badges**: Added Material Symbol status badges (`:material/terrain: Junior Explorer`, `:material/diamond: Gold`, `:material/warning: Dilution: High`, `:material/savings: Net Cash`) and a dedicated exploration KPI grid to Opportunity Dossiers and the Charts tab.

---

# Release Notes — Version 1.7.0

**Release Date:** November 4, 2026  
**Build:** v1.7.0  
**Test Suite:** 132 passing tests (`0.52s`)  
**Code Quality:** 0 Ruff violations (Ruff 0.17+)  
**Compatibility:** Python 3.11–3.13, Streamlit 1.31+ (optimized for 1.66+), FastAPI 0.108+  

---

## Executive Summary

Version 1.7.0 introduces modern UI design and performance architectures to the Financial Analysis platform. It introduces a custom dense dual-mode theme with Google Fonts, replaces emojis with native Material Symbols, transitions chart and dossier views to bordered container cards, accelerates interactivity with `@st.fragment` partial reruns, adds bounded in-memory caching with price history caching, and integrates a 5-pillar Simply Wall St style Snowflake scoring engine.

---

## Key Highlights & Improvements

### 1. Modern Dense Dual-Mode Theming (`.streamlit/config.toml`)
- **Typography**: Streamlit-native integration of Google Fonts (`Inter` for UI headers/body and `JetBrains Mono` for ticker symbols and codes).
- **Dense Dashboard Palette**: Configured compact padding (`paddingTop = 0.5rem`) for high information-density KPI layouts, slate backgrounds, and custom financial indicators while preserving the light/dark user appearance toggle.
- **Micro-Styling**: Subtle 6px rounded borders on widgets and containers with widget and sidebar borders enabled.

### 2. High-Performance Partial Reruns (`@st.fragment`)
- **Instant Chart Interaction**: Wrapped `render_charts_tab` in `@st.fragment` so switching stock symbols or period intervals updates only the chart view without triggering full-app reruns.
- **Fast Analysis Filtering**: Isolated `render_analysis_results` in `@st.fragment` so opportunity strategy pills (*All opportunities*, *Top confluence*, *High upside*, *Value bargains*, *Value trap warnings*) and multiselect controls update tables in memory with zero network delay.
- **Live Search Isolation**: Isolated company search queries in `@st.fragment` within the portfolio builder.

### 3. Price History Caching & Bounded Caches
- **Sub-Millisecond Chart Browsing**: Added `@st.cache_data(ttl=300, max_entries=100)` for `get_price_history_cached`, caching OHLCV data and technical indicators.
- **Bounded Cache Storage**: Configured `max_entries` limits across data loading functions to prevent memory leaks during long-running sessions.

### 4. UI Modernization & Accessibility
- **Material Symbols**: Fully transitioned from raw emojis to native Material Symbols (`:material/trending_up:`, `:material/crown:`, `:material/shield:`, `:material/rocket_launch:`, `:material/diamond:`, `:material/warning:`).
- **Opportunity Dossier Cards**: Replaced horizontal dividers with individual bordered container cards (`st.container(border=True)`) and dynamic Target Upside delta indicators.
- **Responsive 8-KPI Overview**: Upgraded the stock chart view with a balanced 8-metric KPI card.
- **Plotly Integration**: Applied transparent background rendering and synchronized font styling for charts.

### 5. 5-Pillar Snowflake Scoring
- Added `calculate_snowflake_scores` in `financial_analyzer.py` evaluating Value, Future Growth, Past Performance, Financial Health, and Dividend Sustainability (0–30 total score).

---

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
