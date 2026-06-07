# Finance Project

This project provides a financial analysis application that fetches stock data using `yfinance`, calculates various metrics, and presents the results. It also includes a Streamlit application for interactive visualization.

## Project Structure

*   `main.py`: The main entry point for the console application.
*   `financial_analyzer.py`: Contains the core logic for fetching and analyzing financial data.
*   `api.py`: (Assumed) Contains API-related functionalities.
*   `streamlit_app.py`: The Streamlit application for interactive analysis.
*   `config.ini`: Configuration file for various application settings.
*   `requirements.txt`: Lists core Python dependencies for the application.
*   `dev-requirements.txt`: Lists development dependencies like testing and linting tools.
*   `tests/`: Directory containing unit tests for the project.
*   `Dockerfile`: Instructions for building a Docker image of the application.

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

4.  **Install core dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Install development dependencies (optional, for testing and linting):**
    ```bash
    pip install -r dev-requirements.txt
    ```

6.  **Configure `config.ini`:**
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

This project uses `black` for code formatting and `ruff` for linting to ensure consistent code style and identify potential issues.

### Format Code

To automatically format your code:

```bash
black .
```

### Lint Code

To check your code for style and quality issues:

```bash
ruff check .
```

### Auto-fix Linting Issues

To automatically fix some linting issues:

```bash
ruff check . --fix
```

## Deployment with Docker

To build and run the application using Docker:

1.  **Build the Docker Image:**
    ```bash
    docker build -t finance-app .
    ```

2.  **Run the Docker Container (for Streamlit app):**
    ```bash
    docker run -p 8501:8501 finance-app
    ```
    Then open your web browser to `http://localhost:8501`.

    *(To run the console app instead, modify the `CMD` instruction in the `Dockerfile` to `CMD ["python", "main.py"]`)*
