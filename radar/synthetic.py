"""NUR FÜR TESTS: erzeugt Zufallsdaten, damit die Pipeline ohne Internet
geprüft werden kann. Die Webseite zeigt dann ein rotes Warnbanner."""
import numpy as np
import pandas as pd


def fake_universe(n=300):
    rng = np.random.default_rng(1)
    rows = []
    for i in range(n):
        reg = rng.choice(["US", "DE", "EU"], p=[0.6, 0.2, 0.2])
        sym = f"T{i:03d}" + {"US": "", "DE": ".DE", "EU": ".PA"}[reg]
        rows.append({"symbol": sym, "name": f"Testfirma {i}", "sector": "Test",
                     "region": reg, "index": ["Test"]})
    return rows, {"Test": {"count": n, "source": "synthetisch", "as_of": None}}


def fake_prices(symbols, days=1500):
    rng = np.random.default_rng(2)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    close, vol = {}, {}
    for s in symbols:
        sig = rng.uniform(0.15, 0.7) / np.sqrt(252)
        r = rng.normal(0.0002, sig, days)
        p = 50 * np.exp(np.cumsum(r))
        if s.endswith("=X"):
            p = np.full(days, 0.9)
        close[s] = p
        vol[s] = rng.integers(200_000, 5_000_000, days).astype(float)
    c = pd.DataFrame(close, index=idx)
    return {"close": c, "high": c * 1.01, "low": c * 0.99, "volume": pd.DataFrame(vol, index=idx)}


def fake_info(sym, price):
    rng = np.random.default_rng(abs(hash(sym)) % 2**32)
    return {"longName": f"Testfirma {sym}", "currency": "USD",
            "targetMeanPrice": price * rng.uniform(0.9, 1.7),
            "recommendationMean": rng.uniform(1.3, 3.2),
            "numberOfAnalystOpinions": int(rng.integers(2, 30)),
            "longBusinessSummary": "Synthetische Testdaten."}
