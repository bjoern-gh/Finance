import streamlit as st
import configparser
import yfinance as yf # Import yfinance for plain ticker lookup
import pandas as pd # Import pandas for DataFrame operations

# Importiere die Analysefunktion aus unserem Modul
from financial_analyzer import analyze_tickers, parse_and_convert_tickers

# --- Konfiguration laden ---
config = configparser.ConfigParser()
config.read("config.ini")

# Allgemeine Einstellungen
DEFAULT_RAW_DATA = config.get("General", "raw_data")
INCLUDE_DIVIDEND_YIELD = config.getboolean("Metrics", "include_dividend_yield")
INCLUDE_MARKET_CAP = config.getboolean("Metrics", "include_market_cap")

# --- Streamlit App Konfiguration ---
st.set_page_config(layout="wide", page_title="Finanzanalyse-App")

st.title("📈 Finanzanalyse-App")
st.markdown("Analysiere Finanz-Ticker und erhalte Kennzahlen von Yahoo Finance.")

# Helper function to process plain tickers
def process_plain_tickers(plain_tickers_string):
    resolved_tickers = []
    unresolved_plain_tickers = []
    if not plain_tickers_string:
        return resolved_tickers, unresolved_plain_tickers

    plain_tickers_list = [t.strip().upper() for t in plain_tickers_string.split(',') if t.strip()]

    for ticker_symbol in plain_tickers_list:
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            # Check if the ticker actually exists and has a longName
            if info and info.get('longName'):
                resolved_tickers.append((ticker_symbol, ticker_symbol))
            else:
                unresolved_plain_tickers.append(ticker_symbol)
        except Exception:
            unresolved_plain_tickers.append(ticker_symbol)
    return resolved_tickers, unresolved_plain_tickers


# --- Ticker Eingabe ---
st.header("Ticker-Symbole eingeben")

col1, col2 = st.columns(2)

with col1:
    user_prefixed_tickers = st.text_area(
        "Geben Sie Ticker-Symbole mit Präfix ein (z.B. FRA:RWE,ETR:SAP)",
        value=DEFAULT_RAW_DATA.replace(",", ",\n"),
        height=150,
        key="prefixed_tickers"
    )

with col2:
    user_plain_tickers = st.text_area(
        "Geben Sie einfache Ticker-Symbole ein (z.B. AAPL, MSFT)",
        value="", # Default empty for plain tickers
        height=150,
        key="plain_tickers"
    )


# --- Analyse Button ---
if st.button("Analyse starten"):
    all_ticker_tuples = []
    unresolved_plain_tickers_display = []

    # Process prefixed tickers
    if user_prefixed_tickers.strip():
        all_ticker_tuples.extend(parse_and_convert_tickers(
            user_prefixed_tickers.replace(",\n", ",").replace("\n", ",")
        ))

    # Process plain tickers
    if user_plain_tickers.strip():
        resolved_plain, unresolved_plain = process_plain_tickers(user_plain_tickers)
        all_ticker_tuples.extend(resolved_plain)
        unresolved_plain_tickers_display.extend(unresolved_plain)

    if not all_ticker_tuples:
        st.warning("Bitte geben Sie mindestens ein gültiges Ticker-Symbol ein.")
    else:
        st.info("Analyse wird gestartet... Dies kann einen Moment dauern.")

        # Rufe die Analysefunktion auf
        df_results = analyze_tickers(all_ticker_tuples)

        st.subheader("Analyse-Ergebnisse")

        if not df_results.empty:
            successful_df = df_results[df_results["Status"] == "OK"].copy()
            failed_df = df_results[df_results["Status"] != "OK"].copy()

            if not successful_df.empty:
                st.success("Erfolgreich geladene Ticker:")
                display_cols = [
                    "Original_Ticker",
                    "Yahoo_Symbol",
                    "Firmenname",
                    "Preis",
                    "SMA",
                    "KGV",
                    "Trend",
                    "ATH/ATL",
                ]
                if INCLUDE_DIVIDEND_YIELD:
                    display_cols.append("Dividendenrendite (%)")
                if INCLUDE_MARKET_CAP:
                    display_cols.append("Marktkapitalisierung")

                existing_cols = [
                    col for col in display_cols if col in successful_df.columns
                ]
                st.dataframe(successful_df[existing_cols], use_container_width=True)
            else:
                st.warning("Keine Ticker konnten erfolgreich geladen werden.")

            if not failed_df.empty:
                st.error("Ticker mit Fehlern:")
                error_cols = ["Original_Ticker", "Yahoo_Symbol", "Firmenname", "Status"]
                existing_error_cols = [
                    col for col in error_cols if col in failed_df.columns
                ]
                st.dataframe(failed_df[existing_cols], use_container_width=True) # Use existing_cols for failed_df as well
                st.warning(f"({len(failed_df)} Ticker konnten nicht geladen werden.)")
        else:
            st.error("Keine Daten gefunden oder Fehler bei allen Abfragen.")
        
        if unresolved_plain_tickers_display:
            st.warning(f"Folgende einfache Ticker konnten nicht aufgelöst werden: {', '.join(unresolved_plain_tickers_display)}")


st.markdown("---")
st.caption("Powered by Streamlit, FastAPI, yfinance & Pandas")