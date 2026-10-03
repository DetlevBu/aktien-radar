"""Zentrale Einstellungen des Aktien-Radars.

Alle Schwellenwerte stehen hier, damit sie auf der Webseite transparent
angezeigt und leicht angepasst werden können.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
SITE_DIR = ROOT / "docs"          # GitHub Pages liest aus /docs

# --- Ziel ---------------------------------------------------------------
TARGET_GAIN = 0.20                # +20 % = Faktor 1,2
HORIZON_DAYS = 40                 # 40 Handelstage ≈ 8 Wochen
TOP_N = 10
WATCH_N = 20

# --- Stufe 1: Kursfilter (für das gesamte Universum) ---------------------
DRAWDOWN_MIN = 0.20               # mind. 20 % unter 52-Wochen-Hoch
DRAWDOWN_MAX = 0.65               # max. 65 % (sonst oft fundamentale Krise)
MIN_VOL_ANN = 0.28                # mind. 28 % annualisierte Volatilität
MIN_PRICE = 3.0                   # keine Pennystocks (Lokalwährung)
MIN_DOLLAR_VOLUME = 5_000_000     # Median-Tagesumsatz 20 Tage, Lokalwährung
SHORTLIST_N = 100                 # so viele gehen in die teure Stufe 2

# --- Stufe 2: Analystenfilter -------------------------------------------
MAX_RECOMMENDATION_MEAN = 2.3     # Yahoo-Skala 1 = Strong Buy … 5 = Sell
MIN_ANALYSTS = 5
MIN_TARGET_UPSIDE = 0.20          # Konsens-Kursziel mind. 20 % über Kurs

# --- API-Schlüssel (aus GitHub Secrets) ----------------------------------
FINNHUB_KEY = os.getenv("FINNHUB_KEY", "")
FMP_KEY = os.getenv("FMP_KEY", "")
ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_KEY", "")
FRED_KEY = os.getenv("FRED_KEY", "")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "")

# Gratis-Kontingente schonen
FINNHUB_MAX_CALLS = 55            # pro Minute erlaubt: 60
FMP_MAX_SYMBOLS = 30              # Gratis: 250 Abrufe/Tag
ALPHAVANTAGE_MAX_CALLS = 12       # Gratis: 25 Abrufe/Tag

# Für Tests ohne Internet: RADAR_SYNTHETIC=1
SYNTHETIC = os.getenv("RADAR_SYNTHETIC") == "1"
