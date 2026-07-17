import os

os.environ["ARROW_DEFAULT_MEMORY_POOL"] = "system"

import hashlib
import io
import json
import re
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import configparser
import logging

import portfolio_manager as pm
from financial_analyzer import (
    analyze_tickers,
    parse_and_convert_tickers,
    get_price_history,
)

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(layout="wide", page_title="Financial Analysis", page_icon="📈")

# ── Auth ──────────────────────────────────────────────────────────────────────


def _get_credentials() -> tuple[list[str], list[str]]:
    """
    Return (usernames, password_hashes) from env vars, config.ini [Auth], or sensible defaults.
    Priority: ENV vars > config.ini > built-in default (admin / 'admin').
    """
    # 1) Environment variables (explicit override)
    usernames_raw = os.environ.get("AUTH_USERNAMES") or os.environ.get("AUTH_USERNAME")
    hashes_raw = os.environ.get("AUTH_PASSWORD_HASHES") or os.environ.get(
        "AUTH_PASSWORD_HASH"
    )
    if usernames_raw and hashes_raw:
        usernames = [u.strip().lower() for u in usernames_raw.split(",") if u.strip()]
        hashes = [h.strip() for h in hashes_raw.split(",") if h.strip()]
        return usernames, hashes

    # 2) config.ini [Auth] section
    try:
        cfg = configparser.ConfigParser()
        cfg.read("config.ini")
        if cfg.has_section("Auth"):
            usernames_raw = cfg.get("Auth", "usernames", fallback=None) or cfg.get(
                "Auth", "username", fallback=None
            )
            hashes_raw = cfg.get("Auth", "password_hashes", fallback=None) or cfg.get(
                "Auth", "password_hash", fallback=None
            )
            if usernames_raw and hashes_raw:
                usernames = [
                    u.strip().lower() for u in usernames_raw.split(",") if u.strip()
                ]
                hashes = [h.strip() for h in hashes_raw.split(",") if h.strip()]
                return usernames, hashes
    except Exception:
        # If config parsing fails, ignore and fall back to defaults
        pass

    # 3) Fallback default account (local development only)
    # WARNING: These defaults are intentionally simple for local/dev use. Change them by setting
    # AUTH_USERNAME/AUTH_PASSWORD_HASH env vars or adding an [Auth] section to config.ini.
    default_user = "admin"
    default_pass = "admin"
    logging.warning(
        "No auth configured; using default credentials 'admin' / 'admin'. Change immediately for production."
    )
    return [default_user], [_hash(default_pass)]


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_password(username: str, password: str) -> bool:
    usernames, hashes = _get_credentials()
    entered_hash = _hash(password)
    for u, h in zip(usernames, hashes):
        if username.lower() == u and entered_hash == h:
            return True
    return False


def render_login():
    """Full-page login form. Returns True once authenticated."""
    if st.session_state.get("authenticated"):
        return True

    col = st.columns([1, 1, 1])[1]
    with col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.title("📈 Financial Analysis")
        st.subheader("Sign in")

        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")

        if st.button("Sign in", type="primary", width="stretch"):
            if check_password(username, password):
                st.session_state.authenticated = True
                st.session_state.auth_user = username
                st.rerun()
            else:
                st.error("Invalid username or password.")

    return False


# ── Company search via Yahoo Finance API ─────────────────────────────────────


@st.cache_data(ttl=60)
def search_company(query: str) -> list[dict]:
    """Search Yahoo Finance for companies matching a name or ticker query."""
    if not query or len(query) < 2:
        return []
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    params = {
        "q": query,
        "lang": "en-US",
        "region": "US",
        "quotesCount": 10,
        "newsCount": 0,
        "enableFuzzyQuery": "false",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for q in data.get("quotes", []):
            if q.get("quoteType") in ("EQUITY", "ETF", "MUTUALFUND"):
                results.append(
                    {
                        "symbol": q.get("symbol", ""),
                        "name": q.get("longname")
                        or q.get("shortname")
                        or q.get("symbol", ""),
                        "exchange": q.get("exchDisp") or q.get("exchange", ""),
                        "type": q.get("quoteType", ""),
                    }
                )
        return results
    except Exception:
        return []


@st.cache_data(ttl=300)
def run_analysis_cached(ticker_tuples: tuple) -> pd.DataFrame:
    """Cached wrapper around analyze_tickers. Cache invalidates every 5 minutes."""
    return analyze_tickers(list(ticker_tuples))


# ── Styling helpers ───────────────────────────────────────────────────────────

TREND_COLORS = {
    "STRONG BUY": "background-color: #1a7a1a; color: white",
    "BULLISH": "background-color: #4caf50; color: white",
    "OVERBOUGHT": "background-color: #ff9800; color: white",
    "OVERSOLD": "background-color: #2196f3; color: white",
    "HOLD": "background-color: #9e9e9e; color: white",
    "BEARISH": "background-color: #f44336; color: white",
    "STRONG SELL": "background-color: #b71c1c; color: white",
}

VALUATION_COLORS = {
    "Very Cheap (PEG)": "background-color: #1a7a1a; color: white",
    "Cheap": "background-color: #4caf50; color: white",
    "Fair (Good PEG)": "background-color: #8bc34a; color: white",
    "Fair": "background-color: #cddc39; color: black",
    "Fair (High PEG)": "background-color: #ffeb3b; color: black",
    "Cheap (High PEG)": "background-color: #ff9800; color: white",
    "Expensive": "background-color: #ff5722; color: white",
    "Very Expensive (PEG)": "background-color: #b71c1c; color: white",
}


def style_dataframe(df: pd.DataFrame):
    def color_trend(val):
        return TREND_COLORS.get(str(val), "")

    def color_valuation(val):
        return VALUATION_COLORS.get(str(val), "")

    def color_rsi(val):
        try:
            v = float(val)
            if v > 70:
                return "background-color: #ff9800; color: white"
            elif v < 30:
                return "background-color: #2196f3; color: white"
        except (TypeError, ValueError):
            pass
        return ""

    def color_52w_high(val):
        try:
            v = float(val)
            if v >= -5:
                return "color: #f44336; font-weight: bold"
            elif v <= -30:
                return "color: #4caf50"
        except (TypeError, ValueError):
            pass
        return ""

    def color_52w_low(val):
        try:
            v = float(val)
            if v >= 100:
                return "color: #1a7a1a; font-weight: bold"
            elif v <= 10:
                return "color: #ff9800"
        except (TypeError, ValueError):
            pass
        return ""

    styler = df.style
    if "Trend" in df.columns:
        styler = styler.map(color_trend, subset=["Trend"])
    if "Valuation" in df.columns:
        styler = styler.map(color_valuation, subset=["Valuation"])
    if "RSI" in df.columns:
        styler = styler.map(color_rsi, subset=["RSI"])
    if "52W High (%)" in df.columns:
        styler = styler.map(color_52w_high, subset=["52W High (%)"])
    if "52W Low (%)" in df.columns:
        styler = styler.map(color_52w_low, subset=["52W Low (%)"])
    return styler


# ── Chart builder ─────────────────────────────────────────────────────────────


def build_price_chart(yahoo_symbol: str, company_name: str, period: str) -> go.Figure:
    hist = get_price_history(yahoo_symbol, period)
    if hist.empty:
        return None

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.03,
        subplot_titles=(f"{company_name} ({yahoo_symbol})", "RSI (14)"),
    )

    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=hist.index,
            open=hist["Open"],
            high=hist["High"],
            low=hist["Low"],
            close=hist["Close"],
            name="Price",
            increasing_line_color="#4caf50",
            decreasing_line_color="#f44336",
        ),
        row=1,
        col=1,
    )

    # SMA200
    if "SMA200" in hist.columns:
        fig.add_trace(
            go.Scatter(
                x=hist.index,
                y=hist["SMA200"],
                name="SMA 200",
                line=dict(color="#ff9800", width=1.5),
            ),
            row=1,
            col=1,
        )

    # SMA50
    if "SMA50" in hist.columns:
        fig.add_trace(
            go.Scatter(
                x=hist.index,
                y=hist["SMA50"],
                name="SMA 50",
                line=dict(color="#2196f3", width=1.5),
            ),
            row=1,
            col=1,
        )

    # RSI
    delta = hist["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi_series = 100 - (100 / (1 + rs))

    fig.add_trace(
        go.Scatter(
            x=hist.index,
            y=rsi_series,
            name="RSI",
            line=dict(color="#9c27b0", width=1.5),
        ),
        row=2,
        col=1,
    )
    fig.add_hline(y=70, line_dash="dash", line_color="#ff9800", row=2, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#2196f3", row=2, col=1)

    # Volume as bar underneath price (optional overlay)
    fig.update_layout(
        height=600,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="RSI", row=2, col=1, range=[0, 100])

    return fig


# ── Import parser ─────────────────────────────────────────────────────────────


def parse_import_file(content: str) -> list[str]:
    """Parse uploaded file content — one entry per line, strip blanks/comments."""
    lines = []
    for line in content.splitlines():
        line = line.strip().strip(",")
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def resolve_import_entries(entries: list[str]) -> tuple[list[dict], list[str]]:
    """
    Try to resolve each entry as either:
    1. A prefixed ticker (FRA:XXX, ETR:XXX, NASDAQ:XXX, etc.)
    2. A plain Yahoo symbol (AAPL, MSFT)
    3. A company name → search Yahoo Finance

    Returns (resolved: list of ticker dicts, unresolved: list of strings)
    """
    resolved = []
    unresolved = []
    PREFIX_RE = re.compile(
        r"^(?:FRA|ETR|CVE|TSX|NYSE|NASDAQ|LSE|EPA|AMS|BIT|BME|ASX|HKG|TYO|SWX):[A-Z0-9]+$"
    )
    PLAIN_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")

    for entry in entries:
        upper = entry.strip().upper()
        if PREFIX_RE.match(upper):
            pairs = parse_and_convert_tickers(upper)
            if pairs:
                orig, yahoo = pairs[0]
                resolved.append(
                    {"original": orig, "yahoo": yahoo, "display_name": orig}
                )
        elif PLAIN_RE.match(upper):
            resolved.append({"original": upper, "yahoo": upper, "display_name": upper})
        else:
            # Try company name search
            results = search_company(entry)
            if results:
                r = results[0]
                resolved.append(
                    {
                        "original": r["symbol"],
                        "yahoo": r["symbol"],
                        "display_name": r["name"],
                    }
                )
            else:
                unresolved.append(entry)

    return resolved, unresolved


# ── Session state init ────────────────────────────────────────────────────────


def init_state():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = ""
    if "current_portfolio" not in st.session_state:
        portfolios = pm.list_portfolios()
        st.session_state.current_portfolio = portfolios[0] if portfolios else None
    if "analysis_results" not in st.session_state:
        st.session_state.analysis_results = None
    if "last_analyzed_portfolio" not in st.session_state:
        st.session_state.last_analyzed_portfolio = None
    if "creating_portfolio" not in st.session_state:
        st.session_state.creating_portfolio = False
    if "renaming_portfolio" not in st.session_state:
        st.session_state.renaming_portfolio = False
    if "import_preview" not in st.session_state:
        st.session_state.import_preview = None
    if "portfolio_import_preview" not in st.session_state:
        st.session_state.portfolio_import_preview = None


def get_current_tickers() -> list[dict]:
    if not st.session_state.current_portfolio:
        return []
    return pm.load_portfolio(st.session_state.current_portfolio)["tickers"]


# ── Sidebar — portfolio management ───────────────────────────────────────────


def render_sidebar():
    # User info + logout
    st.sidebar.caption(f"Signed in as **{st.session_state.auth_user}**")
    if st.sidebar.button("Sign out", width="stretch"):
        st.session_state.authenticated = False
        st.session_state.auth_user = ""
        st.rerun()

    st.sidebar.divider()
    st.sidebar.title("📁 Portfolios")

    portfolios = pm.list_portfolios()

    if not portfolios:
        st.info("No portfolios yet. Create one below.")
        st.session_state.current_portfolio = None
    else:
        selected = st.sidebar.selectbox(
            "Active Portfolio",
            portfolios,
            index=(
                portfolios.index(st.session_state.current_portfolio)
                if st.session_state.current_portfolio in portfolios
                else 0
            ),
            key="portfolio_selector",
        )
        if selected != st.session_state.current_portfolio:
            st.session_state.current_portfolio = selected
            st.session_state.analysis_results = None
            st.rerun()

        tickers = get_current_tickers()
        st.sidebar.caption(f"{len(tickers)} stock{'s' if len(tickers) != 1 else ''}")

    st.sidebar.divider()

    col1, col2 = st.sidebar.columns(2)
    if col1.button("＋ New", width="stretch"):
        st.session_state.creating_portfolio = True
        st.session_state.renaming_portfolio = False

    if st.session_state.current_portfolio and col2.button("✎ Rename", width="stretch"):
        st.session_state.renaming_portfolio = True
        st.session_state.creating_portfolio = False

    if st.session_state.creating_portfolio:
        new_name = st.sidebar.text_input("Portfolio name:", key="new_portfolio_name")
        if st.sidebar.button("Create", key="confirm_create"):
            if new_name.strip():
                pm.save_portfolio(new_name.strip(), [])
                st.session_state.current_portfolio = new_name.strip()
                st.session_state.creating_portfolio = False
                st.rerun()

    if st.session_state.renaming_portfolio and st.session_state.current_portfolio:
        rename_to = st.sidebar.text_input(
            "New name:", value=st.session_state.current_portfolio, key="rename_input"
        )
        if st.sidebar.button("Save name", key="confirm_rename"):
            if (
                rename_to.strip()
                and rename_to.strip() != st.session_state.current_portfolio
            ):
                pm.rename_portfolio(
                    st.session_state.current_portfolio, rename_to.strip()
                )
                st.session_state.current_portfolio = rename_to.strip()
                st.session_state.renaming_portfolio = False
                st.rerun()

    if st.session_state.current_portfolio:
        st.sidebar.divider()
        if st.sidebar.button(
            f"🗑️ Delete '{st.session_state.current_portfolio}'",
            type="secondary",
            width="stretch",
        ):
            pm.delete_portfolio(st.session_state.current_portfolio)
            remaining = pm.list_portfolios()
            st.session_state.current_portfolio = remaining[0] if remaining else None
            st.session_state.analysis_results = None
            st.rerun()


# ── Tab: Build Portfolio ──────────────────────────────────────────────────────


def render_build_tab():
    if not st.session_state.current_portfolio:
        st.info("Create a portfolio in the sidebar to get started.")
        return

    tickers = get_current_tickers()
    portfolio_name = st.session_state.current_portfolio

    # ── Search ──
    st.subheader("🔍 Search & Add Companies")
    search_col, _ = st.columns([3, 1])
    with search_col:
        query = st.text_input(
            "Search by company name or ticker symbol",
            placeholder="e.g. Apple, SAP, ASML, NVDA...",
            key="company_search",
        )

    if query:
        with st.spinner("Searching..."):
            results = search_company(query)

        if results:
            for r in results[:8]:
                c1, c2, c3 = st.columns([4, 1, 1])
                c1.markdown(
                    f"**{r['name']}** &nbsp; `{r['symbol']}` &nbsp; *{r['exchange']}* &nbsp; {r['type']}"
                )
                already = any(t["yahoo"] == r["symbol"] for t in tickers)
                if already:
                    c2.markdown("✅ Added")
                else:
                    if c2.button("＋ Add", key=f"add_{r['symbol']}"):
                        pm.add_ticker(
                            portfolio_name, r["symbol"], r["symbol"], r["name"]
                        )
                        st.session_state.analysis_results = None
                        st.rerun()
        else:
            st.caption("No results found.")

    st.divider()

    # ── Import ──
    st.subheader("📥 Import from File")
    st.caption(
        "Upload a .txt or .csv with one entry per line: "
        "company names, plain tickers (AAPL), or prefixed tickers (FRA:SAP, NASDAQ:NVDA)."
    )
    uploaded = st.file_uploader(
        "Choose file", type=["txt", "csv"], label_visibility="collapsed"
    )

    if uploaded and st.session_state.import_preview is None:
        content = uploaded.read().decode("utf-8", errors="ignore")
        entries = parse_import_file(content)
        if entries:
            with st.spinner(f"Resolving {len(entries)} entries..."):
                resolved, unresolved = resolve_import_entries(entries)
            st.session_state.import_preview = {
                "resolved": resolved,
                "unresolved": unresolved,
            }
            st.rerun()

    if st.session_state.import_preview:
        preview = st.session_state.import_preview
        resolved = preview["resolved"]
        unresolved = preview["unresolved"]

        st.markdown(f"**Found {len(resolved)} matches:**")
        if resolved:
            preview_df = pd.DataFrame(resolved)[["display_name", "yahoo", "original"]]
            preview_df.columns = ["Company Name", "Yahoo Symbol", "Original"]
            st.dataframe(preview_df, width="stretch", hide_index=True)

            if st.button("✅ Add all to portfolio", type="primary"):
                added = 0
                for t in resolved:
                    if pm.add_ticker(
                        portfolio_name, t["original"], t["yahoo"], t["display_name"]
                    ):
                        added += 1
                st.session_state.import_preview = None
                st.session_state.analysis_results = None
                st.success(f"Added {added} new tickers.")
                st.rerun()

        if unresolved:
            st.warning(
                f"Could not resolve {len(unresolved)} entries: {', '.join(unresolved)}"
            )

        if st.button("Cancel import"):
            st.session_state.import_preview = None
            st.rerun()

    st.divider()

    # ── Current portfolio list ──
    st.subheader(f"📋 Current Portfolio — {portfolio_name} ({len(tickers)} stocks)")

    if not tickers:
        st.info("No stocks yet. Search above or import a file.")
    else:
        for i, t in enumerate(tickers):
            c1, c2, c3 = st.columns([2, 4, 1])
            c1.code(t["yahoo"])
            c2.write(t.get("display_name") or t["original"])
            if c3.button("✕", key=f"remove_{t['yahoo']}_{i}", help="Remove"):
                pm.remove_ticker(portfolio_name, t["yahoo"])
                st.session_state.analysis_results = None
                st.rerun()

    st.divider()

    # ── Portfolio export / import ──
    st.subheader("📤 Export / Import Portfolio")
    exp_col, imp_col = st.columns(2)

    with exp_col:
        st.markdown("**Export**")
        st.caption("Download this portfolio as a JSON file to share or back up.")
        portfolio_data = pm.load_portfolio(portfolio_name)
        export_bytes = json.dumps(portfolio_data, indent=2, ensure_ascii=False).encode(
            "utf-8"
        )
        st.download_button(
            label=f"⬇️ Export '{portfolio_name}'",
            data=export_bytes,
            file_name=f"{portfolio_name}.json",
            mime="application/json",
            width="stretch",
        )

    with imp_col:
        st.markdown("**Import portfolio from file**")
        st.caption(
            "Upload a previously exported portfolio JSON. You can rename it before saving."
        )
        portfolio_file = st.file_uploader(
            "Choose portfolio JSON",
            type=["json"],
            key="portfolio_json_upload",
            label_visibility="collapsed",
        )

        if portfolio_file and st.session_state.portfolio_import_preview is None:
            try:
                raw = json.loads(portfolio_file.read().decode("utf-8"))
                # Validate basic schema
                if not isinstance(raw.get("tickers"), list):
                    st.error("Invalid portfolio file: missing 'tickers' list.")
                else:
                    st.session_state.portfolio_import_preview = raw
                    st.rerun()
            except Exception as e:
                st.error(f"Could not read file: {e}")

        if st.session_state.portfolio_import_preview:
            raw = st.session_state.portfolio_import_preview
            suggested_name = raw.get("name", "Imported Portfolio")
            existing = pm.list_portfolios()

            import_name = st.text_input(
                "Save as:", value=suggested_name, key="portfolio_import_name"
            )
            ticker_count = len(raw.get("tickers", []))
            st.caption(
                f"{ticker_count} stock{'s' if ticker_count != 1 else ''} in this portfolio"
            )

            warn = import_name.strip() in existing
            if warn:
                st.warning(
                    f"A portfolio named '{import_name.strip()}' already exists — it will be overwritten."
                )

            ci1, ci2 = st.columns(2)
            if ci1.button("✅ Save", type="primary", width="stretch"):
                if import_name.strip():
                    pm.save_portfolio(import_name.strip(), raw["tickers"])
                    st.session_state.current_portfolio = import_name.strip()
                    st.session_state.portfolio_import_preview = None
                    st.session_state.analysis_results = None
                    st.success(f"Portfolio '{import_name.strip()}' imported.")
                    st.rerun()
            if ci2.button("Cancel", width="stretch"):
                st.session_state.portfolio_import_preview = None
                st.rerun()


# ── Tab: Analysis ─────────────────────────────────────────────────────────────


def render_analysis_tab():
    if not st.session_state.current_portfolio:
        st.info("Create a portfolio first.")
        return

    tickers = get_current_tickers()
    if not tickers:
        st.info("Add stocks to your portfolio in the **Build Portfolio** tab.")
        return

    portfolio_name = st.session_state.current_portfolio
    ticker_tuples = tuple((t["original"], t["yahoo"]) for t in tickers)

    col1, col2 = st.columns([2, 5])
    run = col1.button("▶️ Run Analysis", type="primary", width="stretch")
    col2.caption(f"Analyzing {len(tickers)} stocks · Results cached for 5 min")

    if run:
        with st.spinner("Fetching data from Yahoo Finance..."):
            df = run_analysis_cached(ticker_tuples)
        st.session_state.analysis_results = df
        st.session_state.last_analyzed_portfolio = portfolio_name

    df = st.session_state.analysis_results
    if df is None or df.empty:
        return

    # Clear cache if portfolio changed
    if st.session_state.last_analyzed_portfolio != portfolio_name:
        st.session_state.analysis_results = None
        return

    success_df = df[df["Status"] == "OK"].copy()
    failed_df = df[df["Status"] != "OK"].copy()

    if not success_df.empty:
        st.markdown(f"### Results — {len(success_df)} stocks loaded")

        display_cols = [
            "Company",
            "Yahoo Symbol",
            "Price",
            "Currency",
            "Price (EUR)",
            "SMA200",
            "SMA50",
            "RSI",
            "P/E (KGV)",
            "Trend",
            "Valuation",
            "ATH/ATL",
            "52W High (%)",
            "52W Low (%)",
            "D/E Ratio",
            "Revenue Growth (%)",
            "Profit Margin (%)",
            "Beta",
            "Sector",
        ]
        optional_cols = ["Dividend Yield (%)", "Market Cap"]
        display_cols += [c for c in optional_cols if c in success_df.columns]
        existing_cols = [c for c in display_cols if c in success_df.columns]

        # Filter recommended buys: Valuation contains "Cheap" (case-insensitive) independent of trend
        is_cheap = (
            success_df["Valuation"]
            .astype(str)
            .str.contains("Cheap", case=False, na=False)
        )
        recommended_df = success_df[is_cheap].copy()

        if not recommended_df.empty:
            # Sort by KGV if available, else by Market Cap if available
            if "P/E (KGV)" in recommended_df.columns:
                # Sort by positive KGV first, then by P/E value ascending
                recommended_df["kvg_group"] = recommended_df["P/E (KGV)"].apply(
                    lambda x: 1 if x <= 0 else 0
                )
                recommended_df = recommended_df.sort_values(
                    by=["kvg_group", "P/E (KGV)"], ascending=[True, True]
                ).drop(columns=["kvg_group"])
            elif "Market Cap" in recommended_df.columns:
                recommended_df = recommended_df.sort_values(
                    by="Market Cap", ascending=True
                )

            st.markdown("### 🔥 Buying Opportunities")
            st.caption(
                "Stocks in your portfolio with a **Cheap** or **Very Cheap** valuation."
            )
            rec_styled = style_dataframe(recommended_df[existing_cols])
            st.dataframe(rec_styled, width="stretch", hide_index=True)
            st.markdown("<br>", unsafe_allow_html=True)

        st.markdown("### 📋 Full Portfolio Analysis")
        styled = style_dataframe(success_df[existing_cols])
        st.dataframe(styled, width="stretch", hide_index=True)

        # ── Download buttons ──
        dl1, dl2, _ = st.columns([1, 1, 4])
        csv_data = success_df[existing_cols].to_csv(index=False).encode("utf-8")
        dl1.download_button(
            "⬇️ CSV",
            data=csv_data,
            file_name=f"{portfolio_name}_analysis.csv",
            mime="text/csv",
            width="stretch",
        )

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            success_df[existing_cols].to_excel(
                writer, index=False, sheet_name="Analysis"
            )
            if not recommended_df.empty:
                recommended_df[existing_cols].to_excel(
                    writer, index=False, sheet_name="Recommended Buys"
                )
        dl2.download_button(
            "⬇️ Excel",
            data=buffer.getvalue(),
            file_name=f"{portfolio_name}_analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

    if not failed_df.empty:
        with st.expander(f"⚠️ {len(failed_df)} tickers with errors"):
            st.dataframe(
                failed_df[["Original Ticker", "Yahoo Symbol", "Company", "Status"]],
                width="stretch",
                hide_index=True,
            )


# ── Tab: Charts ───────────────────────────────────────────────────────────────


def render_charts_tab():
    if not st.session_state.current_portfolio:
        st.info("Create a portfolio first.")
        return

    tickers = get_current_tickers()
    if not tickers:
        st.info("Add stocks to your portfolio in the **Build Portfolio** tab.")
        return

    df = st.session_state.analysis_results
    options = {
        f"{t.get('display_name') or t['yahoo']} ({t['yahoo']})": t["yahoo"]
        for t in tickers
    }

    c1, c2 = st.columns([3, 1])
    selected_label = c1.selectbox("Select stock", list(options.keys()))
    period = c2.selectbox("Period", ["6mo", "1y", "2y", "5y", "max"], index=1)

    yahoo_symbol = options[selected_label]
    company_name = selected_label.split("(")[0].strip()

    # Show current metrics if analysis was run
    if df is not None and not df.empty and "Yahoo Symbol" in df.columns:
        row = df[df["Yahoo Symbol"] == yahoo_symbol]
        if not row.empty:
            r = row.iloc[0]
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("Price", f"{r.get('Price', 'N/A')}")
            m2.metric("RSI", f"{r.get('RSI', 'N/A')}")
            m3.metric("P/E", f"{r.get('P/E (KGV)', 'N/A')}")
            m4.metric("Trend", r.get("Trend", "N/A"))
            m5.metric("52W High", f"{r.get('52W High (%)', 'N/A')}%")
            m6.metric("52W Low", f"{r.get('52W Low (%)', 'N/A')}%")

    with st.spinner("Loading chart..."):
        fig = build_price_chart(yahoo_symbol, company_name, period)

    if fig:
        st.plotly_chart(fig, width="stretch")
    else:
        st.error(f"Could not load chart data for {yahoo_symbol}.")


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    init_state()

    if not render_login():
        return

    render_sidebar()

    st.title("📈 Financial Analysis")
    st.caption("Powered by Yahoo Finance · yfinance · Streamlit")

    tab1, tab2, tab3 = st.tabs(["🔍 Build Portfolio", "📊 Analysis", "📈 Charts"])
    with tab1:
        render_build_tab()
    with tab2:
        render_analysis_tab()
    with tab3:
        render_charts_tab()


if __name__ == "__main__":
    main()
