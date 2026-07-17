  ### Cause of the Segmentation Fault

  The crash is a known issue caused by a conflict between Python 3.14's new memory allocator and PyArrow (which is imported by pandas and used heavily under the hood by streamlit).

  1. Python 3.14 + mimalloc: Starting with Python 3.13/3.14, Python integrates the mimalloc allocator for memory management.
  2. PyArrow + mimalloc: PyArrow also packages its own custom mimalloc memory allocator. When the application runs, both Python and PyArrow try to initialize their own independent mimalloc
  allocators, causing conflicts, memory corruption, and a segmentation fault during thread/interpreter initialization or teardown.
  ──────
  ### Solution implemented

  We resolved this by forcing PyArrow to bypass its bundled mimalloc allocator and use the standard system memory allocator (malloc/free) instead. This is done by setting the environment variable
  ARROW_DEFAULT_MEMORY_POOL=system.

  We applied this environment variable fix across all entry points in the project to make sure the app never crashes, regardless of how it is launched:

  1. At Code Level (Python):
      • Added os.environ["ARROW_DEFAULT_MEMORY_POOL"] = "system" at the absolute top (before any other module imports) in:
	  • streamlit_app.py
	  • financial_analyzer.py
	  • conftest.py

  2. At Environment Level (Virtual Environment):
      • Updated activate to export ARROW_DEFAULT_MEMORY_POOL=system upon activation and clean it up (unset/restore) upon deactivation.

 ### 🔍 Root Cause of the Warning Log

  The log warning:

    2026-07-17 13:16:46,553 - WARNING - Sort column 'KGV' not found.

  was happening because:

  1. In config.ini, the default setting is sort_by_column = KGV.
  2. However, the application uses English keys internally and the corresponding column name returned in the results is "P/E (KGV)".
  3. Because the string "KGV" did not exactly match "P/E (KGV)", the sorting logic skipped it and threw a warning.

  Additionally, the original sorting implementation had a bug where it would permanently overwrite text-based columns (like Company or Sector) with NaN if a user attempted to sort by them (due to
  calling pd.to_numeric(..., errors="coerce") directly on the column).
  ──────
  ### 🛠️ Improvements Made

  I updated the sorting logic in financial_analyzer.py to make it alias-aware and non-destructive:

  1. Alias Mapping: It now maps common input aliases (e.g., "KGV", "PE", "P/E") to the correct DataFrame column name "P/E (KGV)".
  2. Safe Sort Keys: It uses the Pandas key parameter in sort_values to temporarily convert only numeric columns (like Price, RSI, or P/E) to float during the sorting step.
  3. No Mutations: Because it uses a temporary sorting key, if you sort by text columns (like Company), their original text values will no longer be wiped out or replaced by NaN.
