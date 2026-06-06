import pandas as pd
import configparser
import logging
from financial_analyzer import analyze_tickers # Importiere die Hauptanalysefunktion

# --- Konfiguration des Loggers ---
# Der Logger wird bereits in financial_analyzer.py konfiguriert.
# Hier stellen wir nur sicher, dass der Root-Logger auf INFO gesetzt ist,
# falls main.py direkt ausgeführt wird und financial_analyzer.py nicht importiert wurde.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Konfiguration laden ---
config = configparser.ConfigParser()
config.read('config.ini')

# Allgemeine Einstellungen, die nur für die Ausgabe in main.py relevant sind
RAW_DATA = config.get('General', 'raw_data')
OUTPUT_CSV = config.getboolean('General', 'output_csv')
OUTPUT_CSV_FILENAME = config.get('General', 'output_csv_filename')

# Metrik-Einstellungen (werden in financial_analyzer.py geladen, hier nur für die Anzeige-Spalten)
INCLUDE_DIVIDEND_YIELD = config.getboolean('Metrics', 'include_dividend_yield')
INCLUDE_MARKET_CAP = config.getboolean('Metrics', 'include_market_cap')


def main():
    logging.info("Starte die Finanzanalyse-Anwendung.")

    # Rufe die Analysefunktion aus dem Modul auf
    df = analyze_tickers(RAW_DATA)
    
    logging.info("\n--- ENDERGEBNIS ---")
    
    if not df.empty:
        # Trenne erfolgreiche und fehlgeschlagene Abfragen
        successful_df = df[df["Status"] == "OK"].copy()
        failed_df = df[df["Status"] != "OK"].copy()

        if not successful_df.empty:
            logging.info("\n--- Erfolgreich geladene Ticker ---")
            display_cols = ["Original_Ticker", "Yahoo_Symbol", "Firmenname", "Preis", "SMA", "KGV", "Trend"]
            if INCLUDE_DIVIDEND_YIELD:
                display_cols.append("Dividendenrendite (%)")
            if INCLUDE_MARKET_CAP:
                display_cols.append("Marktkapitalisierung")

            # Sicherstellen, dass alle Spalten existieren, bevor sie ausgewählt werden
            existing_cols = [col for col in display_cols if col in successful_df.columns]
            
            # Ausgabe des DataFrames als String
            logging.info("\n" + successful_df[existing_cols].to_string(index=False))
        else:
            logging.warning("\nKeine Ticker konnten erfolgreich geladen werden.")

        if not failed_df.empty:
            logging.warning("\n--- Ticker mit Fehlern ---")
            error_cols = ["Original_Ticker", "Yahoo_Symbol", "Firmenname", "Status"]
            existing_error_cols = [col for col in error_cols if col in failed_df.columns]
            # Ausgabe des DataFrames als String
            logging.warning("\n" + failed_df[existing_error_cols].to_string(index=False))
            logging.warning(f"\n({len(failed_df)} Ticker konnten nicht geladen werden.)")
    else:
        logging.error("Keine Daten gefunden oder Fehler bei allen Abfragen.")

    # Optional: Ergebnisse in CSV speichern
    if OUTPUT_CSV and not df.empty:
        try:
            df.to_csv(OUTPUT_CSV_FILENAME, index=False, encoding='utf-8')
            logging.info(f"Ergebnisse erfolgreich in '{OUTPUT_CSV_FILENAME}' gespeichert.")
        except Exception as e:
            logging.error(f"Fehler beim Speichern der CSV-Datei: {e}")


if __name__ == "__main__":
    main()
