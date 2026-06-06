# Finance Project

This project provides a financial analysis application that fetches stock data using `yfinance`, calculates various metrics, and presents the results. It also includes a Streamlit application for interactive visualization.

## Project Structure

*   `main.py`: The main entry point for the console application.
*   `financial_analyzer.py`: Contains the core logic for fetching and analyzing financial data.
*   `api.py`: (Assumed) Contains API-related functionalities.
*   `streamlit_app.py`: The Streamlit application for interactive analysis.
*   `config.ini`: Configuration file for various application settings.
*   `requirements.txt`: Lists all Python dependencies.
*   `tests/`: Directory containing unit tests for the project.

## Setup

To set up the project, follow these steps:

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd Finance
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    ```

3.  **Activate the virtual environment:**
    *   On macOS/Linux:
        ```bash
        source .venv/bin/activate
        ```
    *   On Windows:
        ```bash
        .venv\Scripts\activate
        ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure `config.ini`:**
    Ensure your `config.ini` file is properly configured with the necessary settings, such as `RAW_DATA` (your ticker list), `SMA_PERIOD`, `KGV_MAX_THRESHOLD`, etc. An example `config.ini` might look like this:

    ```ini
    [General]
    raw_data = FRA:R5AETR:DAINASDAQ:AAPL
    output_csv = True
    output_csv_filename = financial_analysis_results.csv
    sma_period = 20
    kgv_max_threshold = 25
    max_workers = 5
    history_period = 1y
    retries = 3
    retry_delay_seconds = 5
    sort_by_column = Preis
    sort_ascending = False

    [Metrics]
    include_dividend_yield = True
    include_market_cap = True
    ```

## How to Run

### Console Application

To run the main financial analysis application from the console:

```bash
python main.py
```

The results will be printed to the console and optionally saved to a CSV file as configured in `config.ini`.

### Streamlit Application

To run the interactive Streamlit application:

```bash
streamlit run streamlit_app.py
```

This will open the application in your web browser.

## Running Tests

Unit tests are implemented using `pytest`. To run the tests:

1.  **Activate your virtual environment** (if not already active).
2.  **Navigate to the project root directory.**
3.  **Run pytest:**
    ```bash
    pytest
    ```

## Code Quality

This project uses `black` for code formatting and `flake8` for linting to ensure consistent code style and identify potential issues.

### Format Code

To automatically format your code:

```bash
black .
```

### Lint Code

To check your code for style and quality issues:

```bash
flake8 .
```
