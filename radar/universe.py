"""Aktien-Universum: welche Werte werden überhaupt durchsucht?

Quellen:
- Wikipedia (S&P 500, S&P 400, Nasdaq 100, DAX, Euro Stoxx 50)
- GitHub "datasets/s-and-p-500-companies" (Ersatz für S&P 500)
- Yahoo-Finance-Screener (deutsche Werte > 1 Mrd. Börsenwert als MDAX/TecDAX-
  Abdeckung, europäische Werte > ca. 3 Mrd. € als Stoxx-600-Näherung)

Gelingt ein Abruf nicht, wird die letzte erfolgreiche Liste aus dem Cache
verwendet und das auf der Seite vermerkt.
"""
from __future__ import annotations

import re
from io import StringIO

import pandas as pd

from .config import DATA_DIR
from .util import LOG, http_get, read_json, write_json, now_utc

CACHE = DATA_DIR / "universe_cache.json"

WIKI = {  # Name: (URL, Region, erwartete Anzahl)
    "S&P 500": ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "US", 503),
    "S&P 400": ("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "US", 400),
    "Nasdaq 100": ("https://en.wikipedia.org/wiki/Nasdaq-100", "US", 101),
    "DAX": ("https://en.wikipedia.org/wiki/DAX", "DE", 40),
    "Euro Stoxx 50": ("https://en.wikipedia.org/wiki/EURO_STOXX_50", "EU", 50),
}
SYM_RE = re.compile(r"^[A-Z0-9]{1,6}([.-][A-Z0-9]{1,4})?$")
SP500_GITHUB = ("https://raw.githubusercontent.com/datasets/"
                "s-and-p-500-companies/main/data/constituents.csv")

SYM_COLS = ["Symbol", "Ticker", "Ticker symbol"]
NAME_COLS = ["Security", "Company", "Name"]
SECTOR_COLS = ["GICS Sector", "Sector", "Prime Standard Sector", "ICB Industry[14]"]

# Yahoo-Screener: (Region, Börsen, Mindest-Börsenwert in Landeswährung, Label)
# Zusätzlich: nur Heimatbörse (Endung) und Bilanzwährung des Landes, damit
# ausländische Zweitlistings (z. B. US-Aktien in Frankfurt) herausfallen; danach
# die größten N Werte nach Börsenwert.
SCREENS = [
    ("de", ["GER"], 1.0e9, "DE", ".DE", {"EUR"}, 160),
    ("fr", ["PAR"], 3.0e9, "EU", ".PA", {"EUR"}, 110),
    ("nl", ["AMS"], 3.0e9, "EU", ".AS", {"EUR", "USD"}, 40),
    ("it", ["MIL"], 3.0e9, "EU", ".MI", {"EUR"}, 60),
    ("es", ["MCE"], 3.0e9, "EU", ".MC", {"EUR"}, 40),
    ("be", ["BRU"], 3.0e9, "EU", ".BR", {"EUR"}, 20),
    ("fi", ["HEL"], 3.0e9, "EU", ".HE", {"EUR"}, 20),
    ("at", ["VIE"], 3.0e9, "EU", ".VI", {"EUR"}, 12),
    ("pt", ["LIS"], 3.0e9, "EU", ".LS", {"EUR"}, 8),
    ("ie", ["ISE"], 3.0e9, "EU", ".IR", {"EUR"}, 8),
    ("ch", ["EBS"], 3.0e9, "EU", ".SW", {"CHF", "EUR", "USD"}, 60),
    ("gb", ["LSE"], 2.5e9, "EU", ".L", {"GBP", "GBp", "USD", "EUR"}, 140),
    ("se", ["STO"], 35e9, "EU", ".ST", {"SEK"}, 60),
    ("dk", ["CPH"], 25e9, "EU", ".CO", {"DKK"}, 25),
    ("no", ["OSL"], 35e9, "EU", ".OL", {"NOK"}, 25),
]


def _norm(c):
    return re.sub(r"\[.*?\]", "", str(c)).strip().lower()


def _pick(cols, options):
    for o in options:
        for c in cols:
            if _norm(c) == o.lower():
                return c
    return None


def _wiki_table(name, url, region, expected):
    html = http_get(url, "Wikipedia", as_json=False)
    if not html:
        return []
    try:
        tables = pd.read_html(StringIO(html))
    except Exception as ex:
        LOG.fail("Wikipedia", f"{name}: {ex}")
        return []
    best, best_err = [], 1e9
    for t in tables:
        if isinstance(t.columns, pd.MultiIndex):
            continue  # z. B. Tabellen mit Indexänderungen (Added/Removed)
        t = t.loc[:, ~pd.Index([_norm(c) for c in t.columns]).duplicated()]
        sc = _pick(t.columns, SYM_COLS)
        if sc is None or len(t) < 20:
            continue
        nc = _pick(t.columns, NAME_COLS)
        sec = _pick(t.columns, SECTOR_COLS)
        rows = []
        for _, r in t.iterrows():
            sym = str(r[sc]).strip().upper()
            if region == "US":
                sym = sym.replace(".", "-")      # BRK.B -> BRK-B (Yahoo)
            if not SYM_RE.match(sym):
                continue
            rows.append({"symbol": sym,
                         "name": str(r[nc]) if nc is not None else sym,
                         "sector": str(r[sec]) if sec is not None else None,
                         "region": region, "index": [name]})
        err = abs(len(rows) - expected)
        if len(rows) >= 0.6 * expected and err < best_err:
            best, best_err = rows, err
    if not best:
        info = [f"{len(t)}x{list(map(str, t.columns))[:5]}" for t in tables if len(t) >= 0.6 * expected]
        LOG.fail("Wikipedia", f"{name}: keine passende Tabelle; Kandidaten: {info[:3]}")
    return best


def _sp500_github():
    txt = http_get(SP500_GITHUB, "GitHub datasets", as_json=False)
    if not txt:
        return []
    df = pd.read_csv(StringIO(txt))
    return [{"symbol": s.replace(".", "-"), "name": n, "sector": sec,
             "region": "US", "index": ["S&P 500"]}
            for s, n, sec in zip(df["Symbol"], df["Security"], df["GICS Sector"])]


def _yahoo_screen(region, exchanges, min_cap, label, suffix, ccys, max_n):
    import yfinance as yf
    from yfinance import EquityQuery as Q
    q = Q("and", [Q("eq", ["region", region]),
                  Q("is-in", ["exchange", *exchanges]),
                  Q("gt", ["intradaymarketcap", min_cap])])
    out, offset = [], 0
    try:
        while offset < 1000:
            res = yf.screen(q, offset=offset, size=250,
                            sortField="intradaymarketcap", sortAsc=False)
            quotes = res.get("quotes", []) if res else []
            for x in quotes:
                if x.get("quoteType", "EQUITY") != "EQUITY":
                    continue
                if not x["symbol"].endswith(suffix):
                    continue
                fc = x.get("financialCurrency")
                if fc and fc not in ccys:
                    continue
                out.append({"symbol": x["symbol"],
                            "name": x.get("longName") or x.get("shortName") or x["symbol"],
                            "sector": x.get("sector"), "region": label,
                            "index": [f"Yahoo-Screener {region.upper()}"]})
            if len(quotes) < 250:
                break
            offset += 250
        LOG.ok("Yahoo Screener")
        out = out[:max_n]
    except Exception as ex:
        LOG.fail("Yahoo Screener", f"{region}: {ex}")
    return out


def load_universe():
    """Gibt (Liste der Aktien, Info je Teilliste) zurück."""
    LOG.describe("Wikipedia", "Indexlisten S&P 500/400, Nasdaq 100, DAX, Euro Stoxx 50")
    LOG.describe("GitHub datasets", "Ersatzliste S&P 500")
    LOG.describe("Yahoo Screener", "Deutsche und europäische Werte nach Börsenwert")
    cache = read_json(CACHE, {}) or {}
    parts, info = {}, {}
    today = now_utc().date().isoformat()

    def take(name, rows, src):
        if rows:
            parts[name] = rows
            info[name] = {"count": len(rows), "source": src, "as_of": today}
            cache[name] = {"rows": rows, "as_of": today, "source": src}
        elif name in cache:
            parts[name] = cache[name]["rows"]
            info[name] = {"count": len(parts[name]), "as_of": cache[name]["as_of"],
                          "source": cache[name]["source"] + " (Cache, Live-Abruf fehlgeschlagen)"}
        else:
            info[name] = {"count": 0, "source": "nicht verfügbar", "as_of": None}

    for name, (url, region, expected) in WIKI.items():
        rows = _wiki_table(name, url, region, expected)
        if name == "S&P 500" and len(rows) < 400:
            rows = _sp500_github()
            take(name, rows, "GitHub datasets")
            continue
        take(name, rows, "Wikipedia")

    for region, ex, cap, label, suf, ccys, max_n in SCREENS:
        take(f"Screener {region.upper()}",
             _yahoo_screen(region, ex, cap, label, suf, ccys, max_n), "Yahoo Screener")

    write_json(CACHE, cache)

    merged: dict[str, dict] = {}
    for name, rows in parts.items():
        for r in rows:
            m = merged.get(r["symbol"])
            if m:
                for ix in r["index"]:
                    if ix not in m["index"]:
                        m["index"].append(ix)
                m["sector"] = m.get("sector") or r.get("sector")
            else:
                merged[r["symbol"]] = dict(r, index=list(r["index"]))
    return list(merged.values()), info
