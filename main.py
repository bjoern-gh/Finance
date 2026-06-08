import configparser
import logging

# Import the main analysis function and parser
from financial_analyzer import analyze_tickers, parse_and_convert_tickers

# --- Logger Configuration ---
# The logger is already configured in financial_analyzer.py.
# Here we only ensure that the Root-Logger is set to INFO,
# if main.py is executed directly and financial_analyzer.py has not been imported.
# Removed redundant logging.basicConfig as it's configured in financial_analyzer.py
# logging.basicConfig(
#     level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
# )

# --- Load Configuration ---
config = configparser.ConfigParser()
config.read("config.ini")

# General settings relevant only for output in main.py
RAW_DATA = config.get("General", "raw_data")
OUTPUT_CSV = config.getboolean("General", "output_csv")
OUTPUT_CSV_FILENAME = config.get("General", "output_csv_filename")

# Metric settings (loaded in financial_analyzer.py, here only for display columns)
INCLUDE_DIVIDEND_YIELD = config.getboolean("Metrics", "include_dividend_yield")
INCLUDE_MARKET_CAP = config.getboolean("Metrics", "include_market_cap")


def main():
    logging.info("Starting financial analysis application.")

    # Parse raw data into a list of ticker tuples
    ticker_tuples = parse_and_convert_tickers(RAW_DATA)

    # Call the analysis function from the module
    df = analyze_tickers(ticker_tuples)

    logging.info("\n--- ANALYSIS RESULTS ---")

    if not df.empty:
        # Separate successful and failed queries
        successful_df = df[df["Status"] == "OK"].copy()
        failed_df = df[df["Status"] != "OK"].copy()

        if not successful_df.empty:
            logging.info("\n--- Successfully loaded tickers ---")
            display_cols = [
                "Original Ticker",
                "Yahoo Symbol",
                "Company",
                "Price",
                "SMA200",
                "SMA50",
                "RSI",
                "P/E (KGV)",
                "Trend",
                "ATH/ATL",
                "Valuation",
            ]
            if INCLUDE_DIVIDEND_YIELD:
                display_cols.append("Dividend Yield (%)")
            if INCLUDE_MARKET_CAP:
                display_cols.append("Market Cap")

            # Ensure all columns exist before selecting them
            existing_cols = [
                col for col in display_cols if col in successful_df.columns
            ]

            # Output the DataFrame as a string
            logging.info("\n" + successful_df[existing_cols].to_string(index=False))
        else:
            logging.warning("\nNo tickers were successfully loaded.")

        if not failed_df.empty:
            logging.warning("\n--- Tickers with errors ---")
            error_cols = ["Original Ticker", "Yahoo Symbol", "Company", "Status"]
            existing_error_cols = [
                col for col in error_cols if col in failed_df.columns
            ]
            # Output the DataFrame as a string
            logging.warning(
                "\n" + failed_df[existing_error_cols].to_string(index=False)
            )
            logging.warning(
                f"\n({len(failed_df)} tickers could not be loaded.)"
            )
    else:
        logging.error("No data found or errors in all queries.")

    # Optional: Save results to CSV
    if OUTPUT_CSV and not df.empty:
        try:
            df.to_csv(OUTPUT_CSV_FILENAME, index=False, encoding="utf-8")
            logging.info(
                f"Results successfully saved to '{OUTPUT_CSV_FILENAME}'."
            )
        except Exception as e:
            logging.error(f"Error saving CSV file: {e}")


if __name__ == "__main__":
    main()