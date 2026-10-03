"""Backtest der Kursregeln mit historischen Daten.

Vorgehen: An jedem 5. Handelstag (wöchentlich) der letzten Jahre werden mit
den damals bekannten Daten die 10 Aktien mit dem höchsten Kurs-Score gewählt,
die den Kursfilter (Stufe 1) erfüllen. Gemessen wird, ob innerhalb von 40
Handelstagen ein Schlusskurs +20 % über dem Einstieg lag.

Grenzen (werden auf der Seite angezeigt):
- Analystendaten fließen NICHT ein: kostenlose Quellen liefern keine
  Analysten-Einschätzungen zu vergangenen Stichtagen.
- Survivorship-Bias: Das Universum besteht aus heutigen Indexmitgliedern.
  Firmen, die zwischenzeitlich abgestürzt und aus Indizes geflogen sind, fehlen.
  Das schönt die Ergebnisse tendenziell.
- Wöchentliche Auswahl mit 8-Wochen-Horizont überlappt: Die Einzelfälle sind
  nicht unabhängig, die effektive Stichprobe ist kleiner als die Fallzahl.
- Keine Transaktionskosten, Steuern, Slippage.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import HORIZON_DAYS, TOP_N

COLS = ["price_score", "passes_stage1", "fwd_hit", "fwd_ret", "fwd_min", "drawdown",
        "vol60", "turn_score"]


def build_panel(features: dict, regions: dict):
    parts = []
    for sym, f in features.items():
        if f is None or f.empty:
            continue
        d = f[COLS].copy()
        d["symbol"] = sym
        d["region"] = regions.get(sym, "US")
        parts.append(d)
    p = pd.concat(parts)
    p.index.name = "date"
    return p.reset_index()


def _stats(df):
    df = df.dropna(subset=["fwd_hit"])
    if df.empty:
        return None
    return {"n": int(len(df)), "hit_rate": float(df["fwd_hit"].mean()),
            "avg_ret": float(df["fwd_ret"].mean()), "median_ret": float(df["fwd_ret"].median()),
            "loss_share": float((df["fwd_ret"] < 0).mean()),
            "avg_worst": float(df["fwd_min"].mean()),
            "share_worse_20": float((df["fwd_min"] <= -0.2).mean())}


def run(panel: pd.DataFrame):
    p = panel.dropna(subset=["fwd_hit", "price_score"]).copy()
    if p.empty:
        return {"error": "zu wenig Kursdaten für einen Backtest"}
    dates = sorted(p["date"].unique())
    # Erstes Jahr ausschließen (Basisraten brauchen Vorlauf)
    dates = dates[252::5]
    p = p[p["date"].isin(dates)]
    stage1 = p[p["passes_stage1"].astype(bool)]

    def topn(df, col, asc=False):
        return df.sort_values(col, ascending=asc).groupby("date").head(TOP_N)

    strategies = {
        "Top 10 nach Kurs-Score (Radar-Regel)": topn(stage1, "price_score"),
        "Alle Aktien mit Kursfilter (Stufe 1)": stage1,
        "Top 10 mit größtem Abstand zum Hoch": topn(stage1, "drawdown"),
        "Top 10 mit höchster Volatilität": topn(stage1, "vol60"),
        "Alle Aktien im Universum (Basisrate)": p,
    }
    res = {k: _stats(v) for k, v in strategies.items()}

    main = strategies["Top 10 nach Kurs-Score (Radar-Regel)"].copy()
    main["year"] = pd.to_datetime(main["date"]).dt.year
    base = p.copy()
    base["year"] = pd.to_datetime(base["date"]).dt.year
    by_year = []
    for y, g in main.groupby("year"):
        b = base[base["year"] == y]
        by_year.append({"year": int(y), "n": int(len(g)), "hit_rate": float(g["fwd_hit"].mean()),
                        "avg_ret": float(g["fwd_ret"].mean()),
                        "base_hit_rate": float(b["fwd_hit"].mean())})
    by_region = []
    for r, g in main.groupby("region"):
        by_region.append({"region": r, "n": int(len(g)), "hit_rate": float(g["fwd_hit"].mean()),
                          "avg_ret": float(g["fwd_ret"].mean())})
    weekly = main.groupby("date")["fwd_hit"].agg(["sum", "count"])

    # Kalibrierung: tatsächliche Trefferquote je Score-Bereich (Stufe-1-Aktien)
    bins = [0, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 1.0]
    s1 = stage1.copy()
    s1["bucket"] = pd.cut(s1["price_score"], bins)
    calib = []
    for b, g in s1.groupby("bucket", observed=True):
        if len(g) >= 30:
            calib.append({"lo": float(b.left), "hi": float(b.right), "n": int(len(g)),
                          "hit_rate": float(g["fwd_hit"].mean()),
                          "avg_ret": float(g["fwd_ret"].mean()),
                          "worse_20": float((g["fwd_min"] <= -0.2).mean())})
    return {
        "period": [pd.Timestamp(dates[0]).date().isoformat(),
                   pd.Timestamp(dates[-1]).date().isoformat()],
        "rebalance_dates": len(dates), "universe_size": int(panel["symbol"].nunique()),
        "horizon_days": HORIZON_DAYS, "strategies": res, "by_year": by_year,
        "by_region": by_region,
        "weeks_with_hit": float((weekly["sum"] > 0).mean()) if len(weekly) else None,
        "avg_hits_per_week": float(weekly["sum"].mean()) if len(weekly) else None,
        "calibration": calib,
    }


def calibrated_rate(calib, score):
    if score is None or not calib or np.isnan(score):
        return None
    for c in calib:
        if c["lo"] < score <= c["hi"]:
            return c
    return None
