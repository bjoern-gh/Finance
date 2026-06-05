import yfinance as yf
import pandas as pd
import re
from concurrent.futures import ThreadPoolExecutor

# 1. Die Rohdaten
raw_data = "FRA:R5AFRA:6E2ETR:NMMFRA:BAJFRA:TSFAFRA:5BGFRA:ABR0FRA:RIO1ETR:DHLCVE:RDSFRA:0HE1FRA:RWEFRA:SAPETR:HCLETR:DTEFRA:756ETR:EOANFRA:SVRFRA:0W2ETR:KIN2FRA:F4S0FRA:BY6FRA:GV6ETR:XONAFRA:RG3FRA:A980FRA:R3NKFRA:SHAUETR:SIIFRA:1AHFRA:3CPNASDAQ:VOXRFRA:53GFRA:6LS0FRA:PURFRA:ELO1ETR:CDM1FRA:9NHFRA:R6C0FRA:PA2FRA:SEG1FRA:HGRFRA:C3JFRA:7RH1FRA:IUQFRA:RNFFRA:T7C0FRA:US8FRA:RRZFRA:IKLFRA:SVMFRA:8RCFRA:23SPFRA:GGDFRA:RKM0FRA:8N6FRA:RGG1FRA:D150FRA:32JPFRA:97E1FRA:F85FRA:MRGFRA:OEXCVE:SUMFRA:M11FRA:AZ3FRA:IVV1FRA:9MM1FRA:J0GFRA:5N91FRA:1SZ0FRA:B7UFRA:E8KFRA:3FXFRA:2KYFRA:LY1FRA:FR4NCVE:SICOFRA:3Y0FRA:LLJAFRA:1CU0FRA:1OCFRA:RM2FRA:5QGFRA:FLM1"

def parse_and_convert_tickers(data_string):
    """Extrahiert Symbole und konvertiert sie in das Yahoo Finance Format."""
    pattern = r'(?:FRA:|ETR:|CVE:|NASDAQ:)[A-Z0-9]+?(?=(?:FRA:|ETR:|CVE:|NASDAQ:)|$)'
    raw_tickers = re.findall(pattern, data_string)
    
    converted = []
    for t in raw_tickers:
        if t.startswith("FRA:"):
            converted.append(t.replace("FRA:", "") + ".F")
        elif t.startswith("ETR:"):
            converted.append(t.replace("ETR:", "") + ".DE")
        elif t.startswith("CVE:"):
            converted.append(t.replace("CVE:", "") + ".V")
        elif t.startswith("NASDAQ:"):
            converted.append(t.replace("NASDAQ:", ""))
        else:
            converted.append(t)
    return converted

def get_financial_metrics(ticker_symbol):
    """Holt Daten von Yahoo Finance und berechnet Kennzahlen."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        # 1 Jahr Daten für SMA 200
        hist = ticker.history(period="1y")

        if hist.empty:
            return {"Ticker": ticker_symbol, "Status": "Keine Daten (Delisted?)"}

        curr_p = hist['Close'].iloc[-1]
        sma_series = hist['Close'].rolling(window=200).mean()
        sma_v = sma_series.iloc[-1]

        # Fundamentaldaten
        info = ticker.info
        pe_v = info.get('trailingPE') or info.get('forwardPE')
        
        if pe_v is None or pe_v == "None":
            eps = info.get('trailingEps')
            pe_v = curr_p / eps if (eps and eps != 0) else "N/A"

        # Trend-Check
        is_bullish = False
        if not pd.isna(sma_v):
            is_bullish = curr_p > sma_v
            
        trend = "BULLISH" if is_bullish and (isinstance(pe_v, (int, float)) and pe_v < 25 or pe_v == "N/A") else "HALTEN"

        return {
            "Ticker": ticker_symbol,
            "Preis": round(curr_p, 2),
            "SMA200": round(sma_v, 2) if not pd.isna(sma_v) else "N/A",
            "KGV": round(pe_v, 2) if isinstance(pe_v, (int, float)) else "N/A",
            "Trend": trend
        }
    except Exception:
        return {"Ticker": ticker_symbol, "Status": "Fehler"}

def main():
    ticker_list = parse_and_convert_tickers(raw_data)
    print(f"Analyse von {len(ticker_list)} Tickers gestartet...\n")

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_financial_metrics, ticker_list))

    df = pd.DataFrame(results)
    
    print("\n--- ENDERGEBNIS ---")
    if not df.empty:
        # Nur Zeilen anzeigen, die Daten haben
        success_df = df[df["Status"].isna()] if "Status" in df.columns else df
        if not success_df.empty:
            cols = ["Ticker", "Preis", "SMA200", "KGV", "Trend"]
            print(success_df[cols].to_string(index=False))
        
        # Fehlermeldungen anzeigen falls vorhanden
        if "Status" in df.columns:
            error_count = df["Status"].count()
            if error_count > 0:
                print(f"\n({error_count} Ticker konnten nicht geladen werden - evtl. ungültige Symbole)")

if __name__ == "__main__":
    main()
