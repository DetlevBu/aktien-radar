"""Kursdaten: Yahoo Finance (Hauptquelle) und Stooq (Ersatz für US-Werte)."""
from __future__ import annotations

import time
from io import StringIO
from pathlib import Path

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


CACHE_FILE = Path(__file__).resolve().parent.parent / ".cache" / "prices.pkl"
FIELDS = ("Close", "High", "Low", "Volume")


def _fetch(symbols, period, chunk=100):
    """Lädt Kurse blockweise. Erkennt Drosselung (Block fast leer), wartet und
    wiederholt den Block einmal in kleineren Teilen."""
    import yfinance as yf
    frames = {k: [] for k in FIELDS}

    def one(part, label):
        try:
            df = yf.download(part, period=period, interval="1d", auto_adjust=True,
                             group_by="column", threads=True, progress=False)
        except Exception as ex:
            LOG.fail("Yahoo Finance", f"{label}: {str(ex)[:80]}")
            return 0
        if df is None or df.empty:
            return 0
        n_ok = 0
        for k in FIELDS:
            sub = df[k]
            if isinstance(sub, pd.Series):
                sub = sub.to_frame(part[0])
            sub = sub.dropna(axis=1, how="all")
            frames[k].append(sub)
            if k == "Close":
                n_ok = sub.shape[1]
        return n_ok

    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        n_ok = one(part, f"Kursblock {i}")
        if n_ok < 0.5 * len(part):
            LOG.fail("Yahoo Finance", f"Kursblock {i}: nur {n_ok}/{len(part)} – Pause, Wiederholung")
            time.sleep(60)
            got = set().union(*[set(f.columns) for f in frames["Close"]]) if frames["Close"] else set()
            rest = [s for s in part if s not in got]
            for j in range(0, len(rest), 25):
                one(rest[j:j + 25], f"Wiederholung {i}+{j}")
                time.sleep(4)
        else:
            LOG.ok("Yahoo Finance")
        time.sleep(2)
    out = {}
    for k, lst in frames.items():
        d = pd.concat(lst, axis=1) if lst else pd.DataFrame()
        d = d.loc[:, ~d.columns.duplicated()]
        d.index = pd.to_datetime(d.index).tz_localize(None)
        out[k.lower()] = d.sort_index()
    return out


def _merge(old, new):
    """Hängt neue Kurse an den Cache an. Weichen alte und neue Kurse an
    überlappenden Tagen ab (Aktiensplit oder Dividenden-Bereinigung), wird die
    alte Historie mit dem mittleren Verhältnis neu skaliert."""
    out = {}
    for k in ("close", "high", "low", "volume"):
        o, n = old.get(k, pd.DataFrame()), new.get(k, pd.DataFrame())
        if o.empty:
            out[k] = n
            continue
        o = o.copy()
        if k != "volume":
            for s in n.columns.intersection(o.columns):
                ov = o[s].dropna().index.intersection(n[s].dropna().index)
                if len(ov) >= 3:
                    r = (n.loc[ov, s] / o.loc[ov, s]).median()
                    if np.isfinite(r) and abs(r - 1) > 0.002:
                        o[s] = o[s] * r
        out[k] = n.combine_first(o)
    return out


def download(symbols, period="6y"):
    """Lädt Tageskurse mit Cache: bekannte Werte nur letzter Monat, neue Werte
    komplett. Gibt dict mit breiten DataFrames close/high/low/volume."""
    LOG.describe("Yahoo Finance", "Kurse, Indizes, Devisen, Analysten, Kennzahlen, News")
    LOG.describe("Stooq", "Ersatz-Kursquelle für US-Werte")
    cache = {}
    try:
        if CACHE_FILE.exists():
            cache = pd.read_pickle(CACHE_FILE)
    except Exception as ex:
        LOG.fail("Yahoo Finance", f"Cache unlesbar: {ex}")
    cc = cache.get("close", pd.DataFrame())
    fresh = pd.Timestamp.today().normalize() - pd.Timedelta(days=12)
    known = [s for s in symbols if s in cc.columns and cc[s].dropna().shape[0] > 0
             and cc[s].dropna().index.max() >= fresh]
    unknown = [s for s in symbols if s not in set(known)]
    print(f"Kurs-Cache: {len(known)} bekannt (Update 1 Monat), {len(unknown)} neu (komplett)", flush=True)
    new_full = _fetch(unknown, period) if unknown else {}
    new_upd = _fetch(known, "1mo") if known else {}
    merged = _merge(cache, new_full) if new_full else cache
    merged = _merge(merged, new_upd) if new_upd else merged
    out = {k: merged.get(k, pd.DataFrame()) for k in ("close", "high", "low", "volume")}
    _stooq_fill(out, symbols)
    cut = pd.Timestamp.today() - pd.Timedelta(days=int(6.2 * 365))
    for k in out:
        out[k].index = pd.to_datetime(out[k].index).tz_localize(None)
        out[k] = out[k][out[k].index >= cut].sort_index()
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        pd.to_pickle(out, CACHE_FILE)
    except Exception as ex:
        LOG.fail("Yahoo Finance", f"Cache nicht gespeichert: {ex}")
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
