"""Kennzahlen aus Kursdaten. Dieselbe Funktion dient dem Tageslauf und dem
Backtest, damit beide exakt dieselben Regeln verwenden.

Begriffe:
- Drawdown: Abstand des Kurses zum 52-Wochen-Hoch (Schlusskurse).
- Volatilität (annualisiert): Schwankungsbreite der Tagesrenditen der letzten
  60 Tage, hochgerechnet auf ein Jahr.
- RSI(14): Relative-Stärke-Index, 0–100; < 30 gilt als überverkauft.
- SMA20/50/200: gleitender Durchschnitt über 20/50/200 Handelstage.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import (DRAWDOWN_MAX, DRAWDOWN_MIN, HORIZON_DAYS, MIN_DOLLAR_VOLUME,
                     MIN_PRICE, MIN_VOL_ANN, TARGET_GAIN)

LN_TARGET = math.log(1 + TARGET_GAIN)
T_YEARS = HORIZON_DAYS / 252


def norm_cdf(x):
    return 0.5 * (1 + np.vectorize(math.erf)(np.asarray(x) / math.sqrt(2)))


def touch_prob(vol_ann):
    """Wahrscheinlichkeit, dass ein Kurs mit Volatilität σ innerhalb von T
    mindestens einmal +20 % erreicht (Spiegelungsprinzip, Drift 0).

    Formel: P = 2 · (1 − Φ( ln(1,2) / (σ·√T) )). Das ist eine Modellannahme
    (zufällige Kursbewegung ohne Trend), keine Prognose.
    """
    v = np.asarray(vol_ann, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = LN_TARGET / (v * math.sqrt(T_YEARS))
    p = 2 * (1 - norm_cdf(np.nan_to_num(z, nan=99)))
    return np.where(np.isfinite(v) & (v > 0), p, np.nan)


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def feature_frame(close: pd.Series, volume: pd.Series | None, eur_factor: float | None):
    """Berechnet alle Kennzahlen für jeden Tag (nur vergangenheitsbezogen)."""
    c = close.dropna()
    c = c[c > 0]
    f = pd.DataFrame(index=c.index)
    f["close"] = c
    f["high52"] = c.rolling(252, min_periods=200).max()
    f["low52"] = c.rolling(252, min_periods=200).min()
    f["drawdown"] = 1 - c / f["high52"]
    f["sma20"] = c.rolling(20).mean()
    f["sma50"] = c.rolling(50).mean()
    f["sma200"] = c.rolling(200).mean()
    f["rsi14"] = rsi(c)
    lr = np.log(c).diff()
    f["vol60"] = lr.rolling(60).std() * math.sqrt(252)
    for n in (5, 10, 20, 60):
        f[f"ret{n}"] = c / c.shift(n) - 1
    f["ret_1y"] = c / c.shift(252) - 1
    # Kein neues 52-Wochen-Tief in den letzten 10 Tagen?
    prior_low = c.shift(10).rolling(242, min_periods=150).min()
    f["no_new_low"] = (c.rolling(10).min() > prior_low).astype(float)

    if volume is not None and eur_factor:
        v = volume.reindex(c.index)
        f["turnover_eur"] = (c * v * eur_factor).rolling(20).median()
    else:
        f["turnover_eur"] = np.nan
    f["price_eur"] = c * eur_factor if eur_factor else np.nan

    # Wende-Signale (je 0/1), Mittelwert = turn_score 0..1
    sig = pd.DataFrame(index=c.index)
    sig["above_sma20"] = c > f["sma20"]
    sig["sma20_rising"] = f["sma20"] > f["sma20"].shift(5)
    sig["ret10_pos"] = f["ret10"] > 0
    sig["rsi_ok"] = f["rsi14"].between(40, 70)
    sig["no_new_low"] = f["no_new_low"] > 0
    f["turn_score"] = sig.astype(float).mean(axis=1)

    # Zukunftsbezogenes Ergebnis (NUR für Basisrate/Backtest, nie als Signal):
    fwd_max = c[::-1].rolling(HORIZON_DAYS, min_periods=HORIZON_DAYS).max()[::-1].shift(-1)
    f["fwd_hit"] = (fwd_max >= c * (1 + TARGET_GAIN)).astype(float)
    f.loc[fwd_max.isna(), "fwd_hit"] = np.nan
    f["fwd_ret"] = c.shift(-HORIZON_DAYS) / c - 1
    fwd_min = c[::-1].rolling(HORIZON_DAYS, min_periods=HORIZON_DAYS).min()[::-1].shift(-1)
    f["fwd_min"] = fwd_min / c - 1

    # Basisraten, die zum Zeitpunkt t bekannt waren: Ergebnisse müssen
    # mindestens HORIZON_DAYS+1 Tage zurückliegen (kein Blick in die Zukunft).
    known = f["fwd_hit"].shift(HORIZON_DAYS + 1)
    cond = (f["drawdown"].between(DRAWDOWN_MIN, DRAWDOWN_MAX)).shift(HORIZON_DAYS + 1)
    win = 1260  # max. 5 Jahre zurück
    n_all = known.notna().astype(float).rolling(win, min_periods=1).sum()
    h_all = known.fillna(0).rolling(win, min_periods=1).sum()
    ck = known.where(cond.fillna(False).astype(bool))
    n_c = ck.notna().astype(float).rolling(win, min_periods=1).sum()
    h_c = ck.fillna(0).rolling(win, min_periods=1).sum()
    f["base_all"] = h_all / n_all.replace(0, np.nan)
    f["base_all_n"] = n_all
    f["base_cond"] = h_c / n_c.replace(0, np.nan)
    f["base_cond_n"] = n_c
    f["vol_prob"] = touch_prob(f["vol60"].values)
    f["price_score"] = price_score(f)
    f["passes_stage1"] = stage1_mask(f)
    return f


def shrunk_cond(f):
    """Bedingte Basisrate, bei wenigen Fällen zur Gesamtbasisrate gezogen
    (Shrinkage mit Gewicht n/(n+60))."""
    w = f["base_cond_n"] / (f["base_cond_n"] + 60)
    return w * f["base_cond"].fillna(0) + (1 - w) * f["base_all"]


def price_score(f):
    """Kurs-Score 0..1: 45 % Volatilitäts-Wahrscheinlichkeit, 35 % historische
    Trefferquote der Aktie in ähnlicher Lage, 20 % Wende-Signale."""
    return 0.45 * f["vol_prob"] + 0.35 * shrunk_cond(f).fillna(f["base_all"]) \
        + 0.20 * f["turn_score"]


def stage1_mask(f):
    ok = f["drawdown"].between(DRAWDOWN_MIN, DRAWDOWN_MAX)
    ok &= f["vol60"] >= MIN_VOL_ANN
    ok &= f["high52"].notna() & f["sma200"].notna()
    ok &= (f["price_eur"].isna()) | (f["price_eur"] >= MIN_PRICE)
    ok &= (f["turnover_eur"].isna()) | (f["turnover_eur"] >= MIN_DOLLAR_VOLUME)
    return ok
