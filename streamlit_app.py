import streamlit as st
import pandas as pd
import logging
import configparser

# Importiere die Analysefunktion aus unserem Modul
from financial_analyzer import analyze_tickers

# --- Konfiguration laden ---
config = configparser.ConfigParser()
config.read('config.ini')

# Allgemeine Einstellungen
DEFAULT_RAW_DATA = config.get('General', 'raw_data')
INCLUDE_DIVIDEND_YIELD = config.getboolean('Metrics', 'include_dividend_yield')
INCLUDE_MARKET_CAP = config.getboolean('Metrics', 'include_market_cap')

# --- Streamlit App Konfiguration ---
st.set_page_config(layout="wide", page_title="Finanzanalyse-App")

st.title("📈 Finanzanalyse-App")
st.markdown("Analysiere Finanz-Ticker und erhalte Kennzahlen von Yahoo Finance.")

# --- Ticker Eingabe ---
st.header("Ticker-Symbole eingeben")
user_tickers = st.text_area(
    "Geben Sie Ticker-Symbole ein (kommagetrennt, z.B. FRA:RWE,ETR:SAP)",
    value=DEFAULT_RAW_DATA.replace(",", ",\n"), # Zeilenumbrüche für bessere Lesbarkeit
    height=150
)

# --- Analyse Button ---
if st.button("Analyse starten"):
    if not user_tickers.strip():
        st.warning("Bitte geben Sie mindestens ein Ticker-Symbol ein.")
    else:
        # Logging-Ausgabe in Streamlit umleiten (optional, aber gut für Debugging)
        # Streamlit hat einen eigenen Mechanismus für Meldungen, aber Logging ist robuster
        # Für eine saubere Streamlit-Ausgabe können wir die Logging-Handler anpassen
        # oder einfach st.info/warning/error verwenden.
        # Für dieses Beispiel lassen wir das Logging im Hintergrund laufen.

        st.info("Analyse wird gestartet... Dies kann einen Moment dauern.")
        
        # Rufe die Analysefunktion auf
        # Die analyze_tickers Funktion gibt bereits ein DataFrame zurück
        df_results = analyze_tickers(user_tickers.replace(",\n", ",").replace("\n", ","))

        st.subheader("Analyse-Ergebnisse")

        if not df_results.empty:
            successful_df = df_results[df_results["Status"] == "OK"].copy()
            failed_df = df_results[df_results["Status"] != "OK"].copy()

            if not successful_df.empty:
                st.success("Erfolgreich geladene Ticker:")
                display_cols = ["Original_Ticker", "Yahoo_Symbol", "Firmenname", "Preis", "SMA", "KGV", "Trend"]
                if INCLUDE_DIVIDEND_YIELD:
                    display_cols.append("Dividendenrendite (%)")
                if INCLUDE_MARKET_CAP:
                    display_cols.append("Marktkapitalisierung")

                # Sicherstellen, dass alle Spalten existieren
                existing_cols = [col for col in display_cols if col in successful_df.columns]
                st.dataframe(successful_df[existing_cols], use_container_width=True)
            else:
                st.warning("Keine Ticker konnten erfolgreich geladen werden.")

            if not failed_df.empty:
                st.error("Ticker mit Fehlern:")
                error_cols = ["Original_Ticker", "Yahoo_Symbol", "Firmenname", "Status"]
                existing_error_cols = [col for col in error_cols if col in failed_df.columns]
                st.dataframe(failed_df[existing_error_cols], use_container_width=True)
                st.warning(f"({len(failed_df)} Ticker konnten nicht geladen werden.)")
        else:
            st.error("Keine Daten gefunden oder Fehler bei allen Abfragen.")

st.markdown("---")
st.caption("Powered by Streamlit, FastAPI, yfinance & Pandas")
