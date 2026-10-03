"""Marktlage: Indizes (Yahoo), Zinsen/Risikoprämien (FRED), Marktbreite (eigene
Berechnung). Die Einordnung ist regelbasiert und nennt immer die Zahlen."""
from __future__ import annotations

import pandas as pd

from . import config as C
from .prices import INDEX_TICKERS
from .util import LOG, http_get, num

FRED_SERIES = {
    "DGS10": "Rendite 10-jährige US-Staatsanleihen (%)",
    "T10Y2Y": "Zinskurve USA: 10 J. minus 2 J. (Prozentpunkte)",
    "BAMLH0A0HYM2": "Risikoaufschlag US-Hochzinsanleihen (%)",
    "VIXCLS": "VIX laut FRED",
    "ECBDFR": "EZB-Einlagenzins (%)",
}


def fred():
    LOG.describe("FRED (US-Notenbank St. Louis)", "Zinsen, Zinskurve, Kredit-Risikoaufschläge")
    out = {}
    if not C.FRED_KEY:
        LOG.fail("FRED (US-Notenbank St. Louis)", "kein API-Schlüssel hinterlegt")
        return out
    start = (pd.Timestamp.today() - pd.Timedelta(days=120)).date().isoformat()
    for sid, label in FRED_SERIES.items():
        res = http_get("https://api.stlouisfed.org/fred/series/observations",
                       "FRED (US-Notenbank St. Louis)",
                       params={"series_id": sid, "api_key": C.FRED_KEY, "file_type": "json",
                               "observation_start": start})
        obs = [(o["date"], num(o["value"])) for o in (res or {}).get("observations", [])
               if num(o.get("value")) is not None]
        if not obs:
            continue
        last_d, last_v = obs[-1]
        ago = [v for d, v in obs if d <= (pd.Timestamp(last_d) - pd.Timedelta(days=30)).date().isoformat()]
        out[sid] = {"label": label, "value": last_v, "date": last_d,
                    "chg_1m": (last_v - ago[-1]) if ago else None}
    return out


def index_stats(prices):
    out = {}
    close = prices["close"]
    for t, name in INDEX_TICKERS.items():
        if t not in close.columns:
            continue
        s = close[t].dropna()
        if len(s) < 210:
            continue
        out[t] = {"name": name, "value": float(s.iloc[-1]), "date": s.index[-1].date().isoformat(),
                  "chg_1m": float(s.iloc[-1] / s.iloc[-22] - 1),
                  "chg_3m": float(s.iloc[-1] / s.iloc[-64] - 1),
                  "vs_sma200": float(s.iloc[-1] / s.rolling(200).mean().iloc[-1] - 1),
                  "dd_52w": float(1 - s.iloc[-1] / s.iloc[-252:].max()),
                  "spark": [round(float(x), 2) for x in s.iloc[-130:].values]}
    return out


def breadth(features_last: pd.DataFrame):
    """Marktbreite: Anteil der Aktien im Universum über ihrem 200-Tage-Schnitt."""
    f = features_last
    valid = f["sma200"].notna()
    by = {}
    for reg in ("US", "DE", "EU"):
        m = valid & (f["region"] == reg)
        if m.sum() > 20:
            by[reg] = {"above_sma200": float((f.loc[m, "close"] > f.loc[m, "sma200"]).mean()),
                       "dd_over_20": float((f.loc[m, "drawdown"] >= 0.2).mean()),
                       "n": int(m.sum())}
    return by


def assess(idx, fr, br):
    """Regelbasierte Kurz-Einordnung; jede Aussage nennt ihre Zahl."""
    lines, risk = [], 0
    sp = idx.get("^GSPC")
    if sp:
        trend = "über" if sp["vs_sma200"] > 0 else "unter"
        lines.append(f"S&P 500 liegt {abs(sp['vs_sma200'])*100:.1f} % {trend} seinem 200-Tage-Schnitt "
                     f"(1 Monat: {sp['chg_1m']*100:+.1f} %).")
        risk += 0 if sp["vs_sma200"] > 0 else 1
    dax = idx.get("^GDAXI")
    if dax:
        trend = "über" if dax["vs_sma200"] > 0 else "unter"
        lines.append(f"DAX liegt {abs(dax['vs_sma200'])*100:.1f} % {trend} seinem 200-Tage-Schnitt "
                     f"(1 Monat: {dax['chg_1m']*100:+.1f} %).")
        risk += 0 if dax["vs_sma200"] > 0 else 1
    vix = idx.get("^VIX")
    if vix:
        v = vix["value"]
        lvl = "niedrig (ruhiger Markt)" if v < 16 else "normal" if v < 22 else \
              "erhöht (nervöser Markt)" if v < 30 else "hoch (Stressphase)"
        lines.append(f"VIX bei {v:.1f}: {lvl}. Ein hoher VIX bedeutet größere Schwankungen, "
                     f"also mehr Chance und mehr Risiko für +20 %-Bewegungen.")
        risk += 1 if v >= 22 else 0
    hy = fr.get("BAMLH0A0HYM2")
    if hy:
        lines.append(f"Risikoaufschlag Hochzinsanleihen {hy['value']:.2f} % "
                     f"(30 Tage: {hy['chg_1m']:+.2f} Pp.)" if hy.get("chg_1m") is not None else
                     f"Risikoaufschlag Hochzinsanleihen {hy['value']:.2f} %.")
        risk += 1 if (hy.get("chg_1m") or 0) > 0.5 or hy["value"] > 5 else 0
    t10 = fr.get("DGS10")
    if t10:
        lines.append(f"10-jährige US-Rendite {t10['value']:.2f} %" +
                     (f" (30 Tage: {t10['chg_1m']:+.2f} Pp.)." if t10.get("chg_1m") is not None else "."))
    for reg, label in (("US", "USA"), ("DE", "Deutschland"), ("EU", "Europa")):
        b = br.get(reg)
        if b:
            lines.append(f"Marktbreite {label}: {b['above_sma200']*100:.0f} % der Aktien über dem "
                         f"200-Tage-Schnitt, {b['dd_over_20']*100:.0f} % mind. 20 % unter dem Jahreshoch "
                         f"(n = {b['n']}).")
    if risk <= 0:
        verdict = "Rückenwind: Trend intakt, wenig Stress. Erholungen einzelner Aktien gelingen in solchen Phasen häufiger."
    elif risk <= 2:
        verdict = "Gemischt: einzelne Warnsignale. Erholungen sind möglich, aber weniger verlässlich."
    else:
        verdict = "Gegenwind: mehrere Stresssignale. Rücksetzer setzen sich in solchen Phasen oft fort."
    return {"verdict": verdict, "risk_points": risk, "lines": lines}
