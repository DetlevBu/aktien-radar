"""Tageslauf: Daten holen, auswählen, bewerten, Webseite schreiben.

Aufruf: python -m radar.run
"""
from __future__ import annotations

import time
from datetime import date

import numpy as np
import pandas as pd

from . import backtest, config as C, fundamentals as F, macro, probability, tracking
from .indicators import feature_frame
from .prices import FX_TICKERS, INDEX_TICKERS, currency_of, fx_to_eur
from .render import render
from .util import LOG, num, now_utc, write_json


def log(msg):
    print(f"[{now_utc().strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    t0 = time.time()
    today = now_utc().date().isoformat()

    # 1) Universum --------------------------------------------------------
    if C.SYNTHETIC:
        from .synthetic import fake_universe, fake_prices
        universe, uinfo = fake_universe()
    else:
        from .universe import load_universe
        universe, uinfo = load_universe()
    meta = {u["symbol"]: u for u in universe}
    log(f"Universum: {len(universe)} Aktien")

    # 2) Kurse -------------------------------------------------------------
    syms = sorted(set(meta) | set(tracking.all_pick_symbols()))
    extra = list(INDEX_TICKERS) + list(FX_TICKERS.values())
    if C.SYNTHETIC:
        prices = fake_prices(syms + extra)
    else:
        from .prices import download
        prices = download(syms + extra)
    close, vol = prices["close"], prices["volume"]
    log(f"Kurse: {close.shape[1]} Reihen, letzter Tag {close.index.max().date()}")

    # 3) Kennzahlen für alle Aktien ----------------------------------------
    feats, regions = {}, {}
    for s in syms:
        if s not in close.columns or close[s].dropna().shape[0] < 260:
            continue
        ccy = currency_of(s)
        feats[s] = feature_frame(close[s], vol[s] if s in vol.columns else None,
                                 fx_to_eur(prices, ccy))
        regions[s] = meta.get(s, {}).get("region", "US")
    rows = []
    for s, f in feats.items():
        last = f.iloc[-1].to_dict()
        last.update(symbol=s, region=regions[s], price_date=f.index[-1].date().isoformat())
        rows.append(last)
    last = pd.DataFrame(rows).set_index("symbol")
    stale_cut = close.index.max() - pd.Timedelta(days=5)
    last = last[pd.to_datetime(last["price_date"]) >= stale_cut]
    log(f"Kennzahlen: {len(last)} Aktien mit aktuellen Daten")

    # 4) Backtest (nutzt dieselben Kennzahlen) -----------------------------
    panel = backtest.build_panel({s: feats[s] for s in feats if s in meta}, regions)
    bt = backtest.run(panel)
    write_json(C.DATA_DIR / "backtest.json", bt)
    calib = bt.get("calibration", [])
    log("Backtest fertig")

    # 5) Stufe 1: Kursfilter -----------------------------------------------
    in_uni = last.index.isin(list(meta))
    s1 = last[in_uni & last["passes_stage1"].astype(bool)].sort_values("price_score", ascending=False)
    shortlist = list(s1.index[:C.SHORTLIST_N])
    log(f"Stufe 1: {len(s1)} bestehen, {len(shortlist)} auf Shortlist")

    # 6) Stufe 2: Analysten -------------------------------------------------
    if C.SYNTHETIC:
        from .synthetic import fake_info
        infos = {s: fake_info(s, last.loc[s, "close"]) for s in shortlist}
    else:
        infos = F.yahoo_info(shortlist)
    cands = []
    for s in shortlist:
        r = last.loc[s].to_dict()
        inf = infos.get(s, {}) or {}
        price = r["close"]
        tgt = num(inf.get("targetMeanPrice"))
        rec = num(inf.get("recommendationMean"))
        n_an = num(inf.get("numberOfAnalystOpinions"))
        upside = (tgt / price - 1) if tgt and price else None
        checks = {
            "rec": rec is not None and rec <= C.MAX_RECOMMENDATION_MEAN,
            "n": n_an is not None and n_an >= C.MIN_ANALYSTS,
            "upside": upside is not None and upside >= C.MIN_TARGET_UPSIDE,
        }
        strength = None
        if rec is not None and upside is not None:
            strength = 0.5 * min(max(upside, 0), 0.6) / 0.6 + 0.5 * min(max((3 - rec) / 2, 0), 1)
        score = r["price_score"] * (0.7 + 0.3 * (strength if strength is not None else 0))
        cands.append({
            "symbol": s, "name": inf.get("longName") or inf.get("shortName") or meta[s].get("name") or s,
            "region": r["region"], "index": meta[s].get("index", []),
            "currency": inf.get("currency") or currency_of(s),
            "price": price, "price_date": r["price_date"], "target_mean": tgt,
            "target_median": num(inf.get("targetMedianPrice")),
            "target_high": num(inf.get("targetHighPrice")), "target_low": num(inf.get("targetLowPrice")),
            "rec_mean": rec, "rec_key": inf.get("recommendationKey"), "n_analysts": n_an,
            "target_upside": upside, "checks": checks, "passes_stage2": all(checks.values()),
            "fails": sum(not v for v in checks.values()), "analyst_strength": strength,
            "score": float(score), "info": inf,
            **{k: (None if pd.isna(r.get(k)) else float(r[k])) for k in
               ("price_score", "vol_prob", "base_all", "base_all_n", "base_cond", "base_cond_n",
                "drawdown", "high52", "low52", "vol60", "rsi14", "turn_score", "ret5", "ret20",
                "ret60", "ret_1y", "sma20", "sma50", "sma200", "turnover_eur")},
        })
    passed = sorted([c for c in cands if c["passes_stage2"]], key=lambda c: -c["score"])
    top = passed[:C.TOP_N]
    rest = passed[C.TOP_N:] + sorted([c for c in cands if not c["passes_stage2"] and c["fails"] == 1
                                      and c["rec_mean"] is not None], key=lambda c: -c["score"])
    watch = rest[:C.WATCH_N]
    log(f"Stufe 2: {len(passed)} bestehen; Top {len(top)}, Beobachtung {len(watch)}")

    # 7) Details für Top + Beobachtung ---------------------------------------
    fh = F.Finnhub()
    ecal = {} if C.SYNTHETIC else (fh.earnings_calendar() if C.FINNHUB_KEY else {})
    horizon_end = (pd.Timestamp(today) + pd.tseries.offsets.BDay(C.HORIZON_DAYS)).date().isoformat()
    for i, c in enumerate(top + watch):
        s = c["symbol"]
        d = {}
        if not C.SYNTHETIC:
            d.update(F.yahoo_details(s))
            d.update(fh.details(s))
            if i < C.FMP_MAX_SYMBOLS:
                d.update(F.fmp_details(s))
            if i < min(C.TOP_N, C.ALPHAVANTAGE_MAX_CALLS):
                d.update(F.alphavantage_sentiment(s))
            d.update(F.sec_form4_count(s))
        if s in ecal and not d.get("earnings_date"):
            d["earnings_date"], d["earnings_src"] = ecal[s], "Finnhub"
        c["details"] = d
        ed = d.get("earnings_date")
        ein = ed if (ed and today <= ed <= horizon_end) else None
        c["assessment"] = probability.assess(c, calib, ein)
        f = feats[s]
        tail = f["close"].iloc[-252:]
        c["chart"] = {"dates": [x.date().isoformat() for x in tail.index[::2]],
                      "close": [round(float(x), 4) for x in tail.values[::2]]}
        if tail.index[-1] != pd.Timestamp(c["chart"]["dates"][-1]):
            c["chart"]["dates"].append(tail.index[-1].date().isoformat())
            c["chart"]["close"].append(round(float(tail.iloc[-1]), 4))
    log("Details geladen")

    # 8) Markt, Bilanz, Historie ------------------------------------------
    fr = {} if C.SYNTHETIC else macro.fred()
    idx = macro.index_stats(prices)
    br = macro.breadth(last[in_uni])
    market = {"indices": idx, "fred": fr, "breadth": br, "assessment": macro.assess(idx, fr, br)}
    prev = tracking.previous(today)
    changes = tracking.diff(prev, top, watch)
    tracking.save_today(today, top, watch)
    record = tracking.track_record(close)

    # 9) Seite ------------------------------------------------------------
    ctx = {
        "generated": now_utc().isoformat(), "today": today,
        "data_date": close.index.max().date().isoformat(),
        "synthetic": C.SYNTHETIC, "universe_info": uinfo, "universe_n": len(universe),
        "n_with_data": int(in_uni.sum()), "n_stage1": len(s1), "n_stage2": len(passed),
        "top": top, "watch": watch, "changes": changes, "record": record,
        "market": market, "backtest": bt, "sources": LOG.to_dict(),
        "params": {k: getattr(C, k) for k in (
            "TARGET_GAIN", "HORIZON_DAYS", "DRAWDOWN_MIN", "DRAWDOWN_MAX", "MIN_VOL_ANN",
            "MIN_PRICE", "MIN_DOLLAR_VOLUME", "SHORTLIST_N", "MAX_RECOMMENDATION_MEAN",
            "MIN_ANALYSTS", "MIN_TARGET_UPSIDE")},
        "runtime_s": round(time.time() - t0),
    }
    write_json(C.DATA_DIR / "latest.json", {k: v for k, v in ctx.items() if k != "sources"} |
               {"sources": ctx["sources"]})
    render(ctx)
    log(f"Fertig in {ctx['runtime_s']} s")


if __name__ == "__main__":
    main()
