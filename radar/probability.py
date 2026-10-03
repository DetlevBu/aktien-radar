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
    """Hauptzahl = Trefferquote vergleichbarer Fälle im Backtest (viele Aktien,
    nur damals bekannte Daten). Die aktienspezifischen Quoten sind Kontext: Sie
    beruhen auf der eigenen Vergangenheit der Aktie und überschätzen nach
    starken Rallys die Chancen."""
    cal = calibrated_rate(calib, row.get("price_score"))
    main = cal["hit_rate"] if cal else None
    est = [x for x in (row.get("vol_prob"),
                       row.get("base_all") if (row.get("base_all_n") or 0) >= 100 else None,
                       row.get("base_cond") if (row.get("base_cond_n") or 0) >= 40 else None)
           if x is not None]
    context = sum(est) / len(est) if est else None

    upside = row.get("target_upside")
    reasons = []
    if main is None:
        verdict, cls = "Keine Einschätzung (Daten fehlen)", "na"
    elif main >= 0.35 and (upside or 0) >= TARGET_GAIN:
        verdict, cls = "Realistisch", "good"
    elif main >= 0.20:
        verdict, cls = "Möglich", "mid"
    else:
        verdict, cls = "Eher unwahrscheinlich", "low"
    if context is not None and main is not None and context > main + 0.15:
        reasons.append(f"Die eigene Kursgeschichte der Aktie spricht für {context*100:.0f} %, "
                       "das ist aber vermutlich durch eine frühere Rally überzeichnet")
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
    if cal and cal.get("worse_20") is not None:
        reasons.append(f"Kehrseite: In {cal['worse_20']*100:.0f} % der vergleichbaren Fälle lag der Kurs "
                       "zwischenzeitlich mind. 20 % im Minus")
    return {"combined": main, "context": context, "inputs": len(est), "calib": cal,
            "verdict": verdict, "cls": cls, "reasons": reasons, "horizon": HORIZON_DAYS}
