"""Kursdaten: Yahoo Finance (Hauptquelle) und Stooq (Ersatz für US-Werte)."""
from __future__ import annotations

import time
from io import StringIO

import numpy as np
import pandas as pd

from .util import LOG, http_get

INDEX_TICKERS = {
    "^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^GDAXI": "DAX",
    "^STOXX": "Stoxx Europe 600", "^STOXX50E": "Euro Stoxx 50", "^VIX": "VIX",
}
FX_TICKERS = {"USD": "USDEUR=X", "GBP": "GBPEUR=X", "CHF": "CHFEUR=X",
              "SEK": "SEKEUR=X", "DKK": "DKKEUR=X", "NOK": "NOKEUR=X"}

SUFFIX_CCY = {".DE": "EUR", ".F": "EUR", ".PA": "EUR", ".AS": "EUR", ".MI": "EUR",
              ".MC": "EUR", ".BR": "EUR", ".HE": "EUR", ".VI": "EUR", ".LS": "EUR",
              ".IR": "EUR", ".SW": "CHF", ".L": "GBp", ".ST": "SEK", ".CO": "DKK",
              ".OL": "NOK"}


def currency_of(symbol):
    for suf, ccy in SUFFIX_CCY.items():
        if symbol.endswith(suf):
            return ccy
    return "USD"


def download(symbols, period="6y", chunk=150):
    """Lädt Tageskurse. Gibt dict mit breiten DataFrames close/high/low/volume."""
    import yfinance as yf
    LOG.describe("Yahoo Finance", "Kurse, Indizes, Devisen, Analysten, Kennzahlen, News")
    LOG.describe("Stooq", "Ersatz-Kursquelle für US-Werte")
    frames = {k: [] for k in ("Close", "High", "Low", "Volume")}
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        try:
            df = yf.download(part, period=period, interval="1d", auto_adjust=True,
                             group_by="column", threads=True, progress=False)
            if df is None or df.empty:
                LOG.fail("Yahoo Finance", f"Kursblock {i}: leer")
                continue
            for k in frames:
                sub = df[k]
                if isinstance(sub, pd.Series):
                    sub = sub.to_frame(part[0])
                frames[k].append(sub)
            LOG.ok("Yahoo Finance")
        except Exception as ex:
            LOG.fail("Yahoo Finance", f"Kursblock {i}: {ex}")
        time.sleep(1.5)  # Yahoo nicht überlasten
    # Leere Blöcke (meist Yahoo-Drosselung) nach Pause einmal wiederholen
    got = set().union(*[set(f.columns) for f in frames["Close"]]) if frames["Close"] else set()
    retry = [s for s in symbols if s not in got]
    if retry:
        time.sleep(30)
        for i in range(0, len(retry), 100):
            part = retry[i:i + 100]
            try:
                df = yf.download(part, period=period, interval="1d", auto_adjust=True,
                                 group_by="column", threads=True, progress=False)
                if df is not None and not df.empty:
                    for k in frames:
                        sub = df[k]
                        if isinstance(sub, pd.Series):
                            sub = sub.to_frame(part[0])
                        frames[k].append(sub)
                    LOG.ok("Yahoo Finance")
            except Exception as ex:
                LOG.fail("Yahoo Finance", f"Wiederholung {i}: {ex}")
            time.sleep(3)
    out = {}
    for k, lst in frames.items():
        out[k.lower()] = (pd.concat(lst, axis=1) if lst else pd.DataFrame())
        out[k.lower()] = out[k.lower()].loc[:, ~out[k.lower()].columns.duplicated()]
    _stooq_fill(out, symbols)
    for k in out:
        out[k].index = pd.to_datetime(out[k].index).tz_localize(None)
        out[k] = out[k].sort_index()
    return out


def _stooq_fill(out, symbols):
    """Fehlende US-Werte über Stooq nachladen (max. 40, um Zeit zu sparen)."""
    close = out.get("close", pd.DataFrame())
    import re
    missing = [s for s in symbols if re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", s)
               and (s not in close.columns or close[s].dropna().empty)]
    for s in missing[:40]:
        txt = http_get(f"https://stooq.com/q/d/l/?s={s.lower().replace('-', '.')}.us&i=d",
                       "Stooq", as_json=False, retries=1)
        if not txt or "Date" not in txt[:50]:
            continue
        try:
            d = pd.read_csv(StringIO(txt), parse_dates=["Date"]).set_index("Date")
            d = d[d.index >= d.index.max() - pd.Timedelta(days=6 * 365)]
            for k, col in (("close", "Close"), ("high", "High"), ("low", "Low"),
                           ("volume", "Volume")):
                out[k] = out[k].join(d[col].rename(s), how="outer") if not out[k].empty \
                    else d[[col]].rename(columns={col: s})
        except Exception as ex:
            LOG.fail("Stooq", f"{s}: {ex}")


def fx_to_eur(prices, currency):
    """Letzter Umrechnungskurs Lokalwährung -> EUR aus Yahoo-Devisenkursen."""
    if currency == "EUR":
        return 1.0
    factor = 0.01 if currency == "GBp" else 1.0
    base = "GBP" if currency == "GBp" else currency
    t = FX_TICKERS.get(base)
    if not t or t not in prices["close"].columns:
        return None
    s = prices["close"][t].dropna()
    return float(s.iloc[-1]) * factor if len(s) else None


def clean_series(s: pd.Series) -> pd.Series:
    s = s.dropna()
    s = s[s > 0]
    # Einzeltages-Ausreißer (Sprung > 60 % hin und am Folgetag zurück) entfernen
    r = s.pct_change()
    spike = (r.abs() > 0.6) & (r.shift(-1).abs() > 0.35) & (np.sign(r) != np.sign(r.shift(-1)))
    return s[~spike]


def last_valid(df, col):
    if col not in df.columns:
        return None
    s = df[col].dropna()
    return float(s.iloc[-1]) if len(s) else None


__all__ = ["download", "currency_of", "fx_to_eur", "clean_series", "last_valid",
           "INDEX_TICKERS", "FX_TICKERS", "np"]
