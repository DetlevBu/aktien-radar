"""Einschätzung "Wie realistisch sind +20 % in 40 Handelstagen?".

Die Einschätzung stützt sich auf vier Zahlen, die alle auf der Seite stehen:
1. Modell-Wahrscheinlichkeit aus der Volatilität (Spiegelungsprinzip)
2. Historische Trefferquote DIESER Aktie (alle Tage der letzten bis zu 5 Jahre)
3. Historische Trefferquote dieser Aktie in ähnlicher Lage (Abstand zum Hoch 20–65 %)
4. Trefferquote aller Backtest-Fälle mit ähnlichem Kurs-Score

Hinzu kommen Analysten-Kursziel und Termin der nächsten Quartalszahlen.
"""
from __future__ import annotations

from .backtest import calibrated_rate
from .config import HORIZON_DAYS, TARGET_GAIN


def assess(row, calib, earnings_in_horizon):
    est = []
    vp = row.get("vol_prob")
    if vp is not None:
        est.append(vp)
    if row.get("base_all") is not None and (row.get("base_all_n") or 0) >= 100:
        est.append(row["base_all"])
    if row.get("base_cond") is not None and (row.get("base_cond_n") or 0) >= 40:
        est.append(row["base_cond"])
    cal = calibrated_rate(calib, row.get("price_score"))
    if cal:
        est.append(cal["hit_rate"])
    combined = sum(est) / len(est) if est else None

    upside = row.get("target_upside")
    reasons = []
    if combined is None:
        verdict, cls = "Keine Einschätzung (Daten fehlen)", "na"
    elif combined >= 0.30 and (upside or 0) >= TARGET_GAIN:
        verdict, cls = "Realistisch", "good"
    elif combined >= 0.15:
        verdict, cls = "Möglich", "mid"
    else:
        verdict, cls = "Eher unwahrscheinlich", "low"
    if upside is not None:
        if upside >= TARGET_GAIN:
            reasons.append(f"Konsens-Kursziel {upside*100:+.0f} % über Kurs stützt das Ziel")
        else:
            reasons.append(f"Konsens-Kursziel nur {upside*100:+.0f} % über Kurs, also unter +20 %")
    if earnings_in_horizon:
        reasons.append(f"Quartalszahlen am {earnings_in_horizon} liegen im Zeitfenster: "
                       "möglicher Auslöser, aber auch Risiko")
    if (row.get("vol60") or 0) < 0.3:
        reasons.append("Volatilität eher niedrig für +20 % in 8 Wochen")
    if (row.get("turn_score") or 0) >= 0.8:
        reasons.append("Mehrere Wende-Signale aktiv (Kurs dreht nach oben)")
    elif (row.get("turn_score") or 0) <= 0.4:
        reasons.append("Kaum Wende-Signale: Abwärtstrend noch nicht gebrochen")
    return {"combined": combined, "inputs": len(est), "calib": cal, "verdict": verdict,
            "cls": cls, "reasons": reasons, "horizon": HORIZON_DAYS}
