"""Historie, Neuzugänge/Abgänge und Bilanz der bisherigen Empfehlungen.

Regel der Bilanz: Eine Empfehlung gilt als "Ziel erreicht", wenn ein
Schlusskurs innerhalb von 40 Handelstagen nach dem Empfehlungstag mindestens
+20 % über dem Schlusskurs des Empfehlungstags liegt. Nach 40 Handelstagen ohne
Treffer: "verfehlt". Davor: "läuft". Eine Aktie, die mehrere Tage in Folge in
den Top 10 steht, zählt nur einmal (ab dem ersten Tag). Erneute Aufnahme
zählt erst wieder, wenn die vorige Empfehlung abgeschlossen ist.
"""
from __future__ import annotations

import pandas as pd

from .config import HISTORY_DIR, HORIZON_DAYS, TARGET_GAIN
from .util import read_json, write_json


def history_files():
    return sorted(HISTORY_DIR.glob("*.json"))


def previous(today_iso):
    for p in reversed(history_files()):
        if p.stem < today_iso:
            return read_json(p)
    return None


def save_today(today_iso, top, watch):
    write_json(HISTORY_DIR / f"{today_iso}.json", {
        "date": today_iso,
        "top": [{"symbol": x["symbol"], "name": x.get("name"), "price": x["price"],
                 "price_date": x["price_date"], "score": x.get("score"),
                 "currency": x.get("currency")} for x in top],
        "watch": [x["symbol"] for x in watch],
    })


def diff(prev, top, watch):
    if not prev:
        return {"first_run": True}
    p_top = {x["symbol"] for x in prev.get("top", [])}
    p_watch = set(prev.get("watch", []))
    t_top = {x["symbol"] for x in top}
    t_watch = {x["symbol"] for x in watch}
    return {
        "first_run": False, "prev_date": prev.get("date"),
        "top_new": sorted(t_top - p_top), "top_out": sorted(p_top - t_top),
        "watch_new": sorted(t_watch - p_watch - p_top),
        "watch_out": sorted((p_watch | p_top) - t_watch - t_top),
        "promoted": sorted(t_top & p_watch), "demoted": sorted(t_watch & p_top),
    }


def all_pick_symbols():
    syms = set()
    for p in history_files():
        for x in (read_json(p) or {}).get("top", []):
            syms.add(x["symbol"])
    return sorted(syms)


def track_record(close: pd.DataFrame):
    picks, open_until = [], {}
    for p in history_files():
        h = read_json(p) or {}
        for x in h.get("top", []):
            s = x["symbol"]
            if s in open_until and h["date"] <= open_until[s]:
                continue
            entry_date = pd.Timestamp(x.get("price_date") or h["date"])
            entry = x["price"]
            rec = {"symbol": s, "name": x.get("name"), "date": h["date"], "entry": entry,
                   "currency": x.get("currency")}
            ser = close[s].dropna() if s in close.columns else pd.Series(dtype=float)
            after = ser[ser.index > entry_date].iloc[:HORIZON_DAYS]
            rec["days"] = int(len(after))
            if len(after) == 0 or not entry:
                rec.update(status="läuft", max_gain=None, last_gain=None)
                if len(ser) == 0:
                    rec["status"] = "keine Kursdaten"
            else:
                gains = after / entry - 1
                rec["max_gain"] = float(gains.max())
                rec["last_gain"] = float(gains.iloc[-1])
                hit = gains[gains >= TARGET_GAIN]
                if len(hit):
                    rec["status"] = "Ziel erreicht"
                    rec["hit_day"] = int(list(after.index).index(hit.index[0]) + 1)
                elif len(after) >= HORIZON_DAYS:
                    rec["status"] = "verfehlt"
                else:
                    rec["status"] = "läuft"
            # Sperre bis Abschluss
            if rec["status"] == "läuft":
                open_until[s] = "9999"
            else:
                end = after.index[-1].date().isoformat() if len(after) else h["date"]
                open_until[s] = end
            picks.append(rec)
    closed = [r for r in picks if r["status"] in ("Ziel erreicht", "verfehlt")]
    hits = [r for r in closed if r["status"] == "Ziel erreicht"]
    summary = {
        "total": len(picks), "closed": len(closed), "hits": len(hits),
        "open": sum(1 for r in picks if r["status"] == "läuft"),
        "hit_rate": (len(hits) / len(closed)) if closed else None,
        "open_hits": sum(1 for r in picks if r["status"] == "Ziel erreicht" and r["days"] < HORIZON_DAYS),
        "avg_end_gain_closed": (sum(r["last_gain"] for r in closed if r.get("last_gain") is not None) /
                                len(closed)) if closed else None,
    }
    return {"summary": summary, "picks": sorted(picks, key=lambda r: r["date"], reverse=True)}
