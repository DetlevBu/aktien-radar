# Aktien-Radar

Sucht täglich Aktien, die von Analysten zum Kauf empfohlen werden, deutlich unter
ihrem 52-Wochen-Hoch stehen und realistische Chancen auf **+20 % innerhalb von
40 Handelstagen** haben. Ergebnis: eine mobile Webseite unter
`https://detlevbu.github.io/aktien-radar/`.

**Keine Anlageberatung.**

## Ablauf
1. GitHub Actions startet `python -m radar.run` an jedem Werktag gegen 6:15 Uhr (Berlin).
2. Das Skript lädt Universum, Kurse, Analysten-, Unternehmens-, Nachrichten- und Makrodaten.
3. Es filtert in zwei Stufen, bewertet die Kandidaten und rechnet einen Backtest.
4. Es schreibt `docs/index.html` (Webseite) und `data/` (Historie, Bilanz) ins Repo.

## Einmalige Einrichtung
- Secrets (Settings → Secrets and variables → Actions): `FINNHUB_KEY`, `FMP_KEY`,
  `ALPHAVANTAGE_KEY`, `FRED_KEY`, optional `SEC_USER_AGENT` (z. B. `Aktien-Radar name@mail.de`).
- Settings → Pages → Source „Deploy from a branch“ → Branch `main`, Ordner `/docs`.

## Manuell starten
Actions → „Taeglicher Radar-Lauf“ → „Run workflow“.

## Regeln anpassen
Alle Schwellenwerte stehen in `radar/config.py`.

## Lokaler Test ohne Internet
`RADAR_SYNTHETIC=1 python -m radar.run` erzeugt eine Seite mit Zufallsdaten (rotes Warnbanner).

## Datenquellen
Yahoo Finance (inkl. Screener), Finnhub, Financial Modeling Prep, Alpha Vantage,
FRED, SEC EDGAR, Wikipedia, GitHub datasets, Stooq.
