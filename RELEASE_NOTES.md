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
