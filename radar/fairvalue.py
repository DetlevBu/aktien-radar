"""Fair Value Calculator (fairvalue-calculator.com) einbinden.

Der Dienst ist über das Konto des Nutzers nur in Claude-Sitzungen erreichbar
(Connector), nicht aus GitHub Actions. Deshalb holt die tägliche Claude-
Aufgabe nach dem Radar-Lauf die Bewertungen für Top 10 + Beobachtungsliste
und legt sie unverändert in data/fairvalue.json ab. Dieses Modul
- hängt die Werte an die Kandidaten (beim Voll-Lauf und beim Nachtrag),
- rendert die Seite neu (python -m radar.enrich -> main()).

Format data/fairvalue.json:
{"date": "YYYY-MM-DD", "fetched_at": ISO, "items": {"<Radar-Symbol>": {
   "fvc_symbol", "valuation_status", "upside_band", "quality_score",
   "evidence_level", "fair_value", "fair_value_currency", "fair_value_range",
   "reasons", "ai_conclusion", "in_focus", "main_risk", "ai_note_date",
   "calculated_at", "deep_link"} | {"error": "..."} }}
"""
from __future__ import annotations

from .config import DATA_DIR
from .util import num, read_json, write_json

FV_FILE = DATA_DIR / "fairvalue.json"
SOURCE = "Fair Value Calculator"


def _fv_in_price_ccy(fv, fv_ccy, price_ccy):
    """Fairen Wert in die Kurswährung der Radar-Daten bringen (nur GBp/GBP)."""
    if fv is None:
        return None
    if price_ccy == "GBp" and fv_ccy in ("GBP", "£"):
        return fv * 100
    if price_ccy == "GBP" and fv_ccy == "GBp":
        return fv / 100
    if fv_ccy and price_ccy and fv_ccy.upper() != price_ccy.upper():
        return None          # andere Währung: kein Vergleich, statt falscher Zahl
    return fv


def attach(ctx):
    """Bewertungen an Top- und Beobachtungs-Kandidaten hängen; Quellenstatus setzen."""
    data = read_json(FV_FILE, None)
    src = ctx.setdefault("sources", {})
    entry = {"ok": 0, "fail": 0, "notes": [],
             "used_for": "Fairer Wert, Bewertungsstatus, Qualitätsnote, Stärken/Risiken "
                         "(Top 10 + Beobachtung; über dein Konto)"}
    if not data or not data.get("items"):
        entry["disabled"] = "Noch keine Daten abgerufen (holt die morgendliche Claude-Aufgabe nach dem Lauf)."
        src[SOURCE] = entry
        return ctx
    items = data["items"]
    missing = []
    for c in ctx.get("top", []) + ctx.get("watch", []):
        it = items.get(c["symbol"])
        if not it:
            c.pop("fairvalue", None)
            continue
        if it.get("error"):
            missing.append(c["symbol"])
            c["fairvalue"] = {"error": it["error"], "date": data.get("date")}
            continue
        entry["ok"] += 1
        fv = _fv_in_price_ccy(num(it.get("fair_value")), it.get("fair_value_currency"),
                              c.get("currency"))
        c["fairvalue"] = dict(it, date=data.get("date"), fair_value_local=fv,
                              upside=(fv / c["price"] - 1) if fv and c.get("price") else None)
    if missing:
        entry["notes"].append("Keine Bewertung vorhanden für: " + ", ".join(missing))
    if data.get("date") and data.get("date") != ctx.get("today"):
        entry["notes"].insert(0, f"Stand {data['date']} (heute noch nicht aktualisiert)")
    src[SOURCE] = entry
    return ctx


def main():
    """Nachtrag: Seite mit neuen Fair-Value-Daten neu erzeugen, ohne Neuberechnung."""
    from .render import render
    path = DATA_DIR / "latest.json"
    ctx = read_json(path, None)
    if not ctx:
        raise SystemExit("data/latest.json fehlt – erst einen Voll-Lauf ausführen.")
    attach(ctx)
    write_json(path, ctx)
    render(ctx)
    print(f"Fair-Value-Nachtrag: {ctx['sources'][SOURCE]['ok']} Bewertungen eingebunden.")


if __name__ == "__main__":
    main()
