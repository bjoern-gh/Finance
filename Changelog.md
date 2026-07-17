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