"""Unternehmens- und Analystendaten aus mehreren Quellen.

- Yahoo Finance: Analysten-Konsens, Kursziele, Kennzahlen, Profil, News, Termine
- Finnhub: Empfehlungstrend der Analysten, News, Insidergeschäfte, Earnings-Termin
- Financial Modeling Prep (FMP): Kursziel-Konsens, Analysten-Ratings
- Alpha Vantage: News-Stimmung (Sentiment-Score)
- SEC EDGAR: Anzahl gemeldeter Insider-Formulare (Form 4)
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd

from . import config as C
from .util import LOG, http_get, num

INFO_KEYS = [
    "longName", "shortName", "currency", "country", "sector", "industry", "website",
    "fullTimeEmployees", "longBusinessSummary", "marketCap", "trailingPE", "forwardPE",
    "priceToBook", "enterpriseToEbitda", "revenueGrowth", "earningsGrowth",
    "profitMargins", "debtToEquity", "freeCashflow", "shortPercentOfFloat", "beta",
    "dividendYield", "currentPrice", "targetMeanPrice", "targetMedianPrice",
    "targetHighPrice", "targetLowPrice", "numberOfAnalystOpinions",
    "recommendationMean", "recommendationKey", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
]


def is_us(sym):
    return "." not in sym and not sym.startswith("^")


# ---------------------------------------------------------------- Yahoo ----
def yahoo_info(symbols, workers=4):
    import yfinance as yf

    def one(s):
        for attempt in range(2):
            try:
                inf = yf.Ticker(s).get_info() or {}
                LOG.ok("Yahoo Finance")
                return s, {k: inf.get(k) for k in INFO_KEYS}
            except Exception as ex:
                err = ex
                time.sleep(2)
        LOG.fail("Yahoo Finance", f"info {s}: {err}")
        return s, {}

    with ThreadPoolExecutor(workers) as ex:
        return dict(ex.map(one, symbols))


def _news_item(a):
    c = a.get("content", a)
    url = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") \
        or c.get("link")
    return {"title": c.get("title"), "date": (c.get("pubDate") or c.get("displayTime") or "")[:10],
            "source": (c.get("provider") or {}).get("displayName") or c.get("publisher"),
            "url": url, "via": "Yahoo"}


def yahoo_details(symbol):
    """Zusätzliche Daten für die Endauswahl."""
    import yfinance as yf
    t = yf.Ticker(symbol)
    out = {}
    try:
        rs = t.get_recommendations_summary()
        if isinstance(rs, pd.DataFrame) and not rs.empty:
            r0 = rs.iloc[0]
            out["rec_counts"] = {k: int(r0.get(k, 0) or 0) for k in
                                 ("strongBuy", "buy", "hold", "sell", "strongSell")}
            out["rec_counts_src"] = "Yahoo"
        LOG.ok("Yahoo Finance")
    except Exception as ex:
        LOG.fail("Yahoo Finance", f"recs {symbol}: {ex}")
    try:
        ud = t.get_upgrades_downgrades()
        if isinstance(ud, pd.DataFrame) and not ud.empty:
            ud = ud.reset_index()
            dcol = "GradeDate" if "GradeDate" in ud.columns else ud.columns[0]
            ud[dcol] = pd.to_datetime(ud[dcol]).dt.tz_localize(None)
            recent = ud[ud[dcol] >= pd.Timestamp.today() - pd.Timedelta(days=90)]
            act = recent.get("Action", pd.Series(dtype=str)).astype(str).str.lower()
            out["rating_changes_90d"] = {"up": int((act == "up").sum()),
                                         "down": int((act == "down").sum()),
                                         "total": int(len(recent))}
            items = []
            for _, r in recent.sort_values(dcol, ascending=False).head(5).iterrows():
                items.append({"date": r[dcol].date().isoformat(), "firm": r.get("Firm"),
                              "to": r.get("ToGrade"), "from": r.get("FromGrade"),
                              "action": r.get("Action"),
                              "target": num(r.get("currentPriceTarget"))})
            out["rating_actions"] = items
    except Exception as ex:
        LOG.fail("Yahoo Finance", f"upgrades {symbol}: {ex}")
    try:
        news = t.get_news(count=8) or []
        out["news"] = [_news_item(a) for a in news[:6]]
    except Exception as ex:
        LOG.fail("Yahoo Finance", f"news {symbol}: {ex}")
    try:
        cal = t.get_calendar() or {}
        ed = cal.get("Earnings Date")
        if ed:
            ed = ed[0] if isinstance(ed, (list, tuple)) else ed
            out["earnings_date"] = str(ed)[:10]
            out["earnings_src"] = "Yahoo"
    except Exception as ex:
        LOG.fail("Yahoo Finance", f"calendar {symbol}: {ex}")
    return out


# --------------------------------------------------------------- Finnhub ---
class Finnhub:
    URL = "https://finnhub.io/api/v1/"

    def __init__(self):
        self.calls = 0
        self.t0 = time.time()
        LOG.describe("Finnhub", "Analysten-Empfehlungstrend, News, Insidergeschäfte, Termine (US)")

    def get(self, path, **params):
        if not C.FINNHUB_KEY:
            return None
        self.calls += 1
        if self.calls % C.FINNHUB_MAX_CALLS == 0:
            wait = 61 - (time.time() - self.t0)
            if wait > 0:
                time.sleep(wait)
            self.t0 = time.time()
        params["token"] = C.FINNHUB_KEY
        return http_get(self.URL + path, "Finnhub", params=params)

    def details(self, symbol):
        out = {}
        if not is_us(symbol):
            return out
        rec = self.get("stock/recommendation", symbol=symbol)
        if rec:
            r = rec[0]
            out["finnhub_rec"] = {"period": r.get("period"),
                                  "strongBuy": r.get("strongBuy"), "buy": r.get("buy"),
                                  "hold": r.get("hold"), "sell": r.get("sell"),
                                  "strongSell": r.get("strongSell")}
            if len(rec) >= 4:
                old = rec[3]
                pos = lambda x: (x.get("strongBuy", 0) or 0) + (x.get("buy", 0) or 0)
                tot = lambda x: sum((x.get(k, 0) or 0) for k in
                                    ("strongBuy", "buy", "hold", "sell", "strongSell")) or 1
                out["finnhub_rec_trend"] = {"now_buy_share": pos(r) / tot(r),
                                            "3m_ago_buy_share": pos(old) / tot(old),
                                            "period_old": old.get("period")}
        today = date.today()
        news = self.get("company-news", symbol=symbol,
                        **{"from": (today - timedelta(days=14)).isoformat(),
                           "to": today.isoformat()})
        if news:
            out["news_fh"] = [{"title": n.get("headline"), "source": n.get("source"),
                               "url": n.get("url"), "via": "Finnhub",
                               "date": pd.to_datetime(n.get("datetime"), unit="s").date().isoformat()}
                              for n in news[:5]]
        ins = self.get("stock/insider-transactions", symbol=symbol,
                       **{"from": (today - timedelta(days=90)).isoformat()})
        if ins and ins.get("data") is not None:
            buys = [x for x in ins["data"] if x.get("transactionCode") == "P"]
            sells = [x for x in ins["data"] if x.get("transactionCode") == "S"]
            out["insider_90d"] = {
                "buys": len(buys), "sells": len(sells),
                "buy_value": sum((x.get("change") or 0) * (x.get("transactionPrice") or 0) for x in buys),
                "sell_value": -sum((x.get("change") or 0) * (x.get("transactionPrice") or 0) for x in sells),
            }
        return out

    def earnings_calendar(self, days=60):
        today = date.today()
        res = self.get("calendar/earnings", **{"from": today.isoformat(),
                                               "to": (today + timedelta(days=days)).isoformat()})
        cal = {}
        for e in (res or {}).get("earningsCalendar", []) or []:
            s = e.get("symbol")
            if s and s not in cal:
                cal[s] = e.get("date")
        return cal


# ------------------------------------------------------------------- FMP ---
def fmp_details(symbol):
    if not C.FMP_KEY:
        return {}
    LOG.describe("Financial Modeling Prep", "Kursziel-Konsens, Analysten-Rating-Konsens")
    sym = symbol.replace("-", ".") if is_us(symbol) else symbol
    out = {}
    pt = http_get("https://financialmodelingprep.com/stable/price-target-consensus",
                  "Financial Modeling Prep", params={"symbol": sym, "apikey": C.FMP_KEY},
                  retries=1)
    if isinstance(pt, list) and pt:
        p = pt[0]
        out["fmp_target"] = {"consensus": num(p.get("targetConsensus")),
                             "median": num(p.get("targetMedian")),
                             "high": num(p.get("targetHigh")), "low": num(p.get("targetLow"))}
    gc = http_get("https://financialmodelingprep.com/stable/grades-consensus",
                  "Financial Modeling Prep", params={"symbol": sym, "apikey": C.FMP_KEY},
                  retries=1)
    if isinstance(gc, list) and gc:
        g = gc[0]
        out["fmp_grades"] = {k: g.get(k) for k in
                             ("strongBuy", "buy", "hold", "sell", "strongSell", "consensus")}
    return out


# ----------------------------------------------------------- Alpha Vantage -
def alphavantage_sentiment(symbol):
    if not C.ALPHAVANTAGE_KEY or not is_us(symbol):
        return {}
    LOG.describe("Alpha Vantage", "News-Stimmung (Sentiment) der letzten Artikel, US-Werte")
    res = http_get("https://www.alphavantage.co/query", "Alpha Vantage",
                   params={"function": "NEWS_SENTIMENT", "tickers": symbol,
                           "limit": 50, "apikey": C.ALPHAVANTAGE_KEY}, retries=0)
    if not res or "feed" not in res:
        if res:
            LOG.fail("Alpha Vantage", (res.get("Information") or res.get("Note") or "keine Daten")[:150])
        return {}
    scores = []
    for a in res["feed"]:
        for ts in a.get("ticker_sentiment", []):
            if ts.get("ticker") == symbol and num(ts.get("relevance_score")) and \
                    num(ts["relevance_score"]) >= 0.3:
                scores.append(num(ts.get("ticker_sentiment_score")))
    scores = [s for s in scores if s is not None]
    if not scores:
        return {"av_sentiment": None, "av_articles": len(res["feed"])}
    return {"av_sentiment": sum(scores) / len(scores), "av_articles": len(scores)}


# -------------------------------------------------------------------- SEC --
_SEC_MAP = None


def sec_form4_count(symbol):
    global _SEC_MAP
    if not C.SEC_USER_AGENT or not is_us(symbol):
        return {}
    LOG.describe("SEC EDGAR", "Anzahl Insider-Meldungen (Form 4) der letzten 90 Tage, US")
    h = {"User-Agent": C.SEC_USER_AGENT}
    if _SEC_MAP is None:
        m = http_get("https://www.sec.gov/files/company_tickers.json", "SEC EDGAR", headers=h)
        _SEC_MAP = {v["ticker"].upper(): v["cik_str"] for v in (m or {}).values()}
    cik = _SEC_MAP.get(symbol.replace("-", ".").upper()) or _SEC_MAP.get(symbol.upper())
    if not cik:
        return {}
    sub = http_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", "SEC EDGAR",
                   headers=h)
    time.sleep(0.15)  # SEC erlaubt max. 10 Abrufe/Sekunde
    if not sub:
        return {}
    rec = sub.get("filings", {}).get("recent", {})
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    n = sum(1 for f, d in zip(rec.get("form", []), rec.get("filingDate", []))
            if f == "4" and d >= cutoff)
    return {"sec_form4_90d": n,
            "sec_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4"}
