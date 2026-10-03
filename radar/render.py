"""Erzeugt die statische Webseite docs/index.html (GitHub Pages)."""
from __future__ import annotations

import html
from datetime import datetime

from .config import SITE_DIR

NA = '<span class="na">k. A.</span>'
E = html.escape


# ------------------------------------------------------------ Formatierung -
def de(x, d=2):
    if x is None:
        return None
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def n(x, d=2, suf=""):
    v = de(x, d)
    return NA if v is None else v + suf


def pct(x, d=1, sign=False):
    if x is None:
        return NA
    s = f"{x*100:+.{d}f}" if sign else f"{x*100:.{d}f}"
    return s.replace(".", ",") + " %"


def big(x):
    if x is None:
        return NA
    for div, s in ((1e12, " Bio."), (1e9, " Mrd."), (1e6, " Mio.")):
        if abs(x) >= div:
            return de(x / div, 1) + s
    return de(x, 0)


def ccy(c):
    return {"USD": "$", "EUR": "€", "GBp": "GBp", "GBP": "£", "CHF": "CHF", "SEK": "SEK",
            "DKK": "DKK", "NOK": "NOK"}.get(c or "", c or "")


def price(x, c):
    return NA if x is None else f"{de(x, 2)} {ccy(c)}"


def sgn_cls(x):
    return "" if x is None else ("pos" if x > 0 else "neg" if x < 0 else "")


# ------------------------------------------------------------------ Grafik --
def chart_svg(c, w=640, h=220):
    ys = c["chart"]["close"]
    if len(ys) < 5:
        return f"<p>{NA} Kursverlauf</p>"
    target20 = c["price"] * 1.2
    lines = [("52W-Hoch", c.get("high52"), "var(--muted)"),
             ("+20 %", target20, "var(--accent)"),
             ("Analystenziel", c.get("target_mean"), "var(--good)")]
    vals = ys + [v for _, v, _ in lines if v]
    lo, hi = min(vals) * 0.97, max(vals) * 1.03
    pl, pr, pt, pb = 8, 92, 10, 22
    X = lambda i: pl + i * (w - pl - pr) / (len(ys) - 1)
    Y = lambda v: pt + (hi - v) * (h - pt - pb) / (hi - lo)
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(ys))
    area = f"{X(0):.1f},{h-pb} " + pts + f" {X(len(ys)-1):.1f},{h-pb}"
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" '
           f'aria-label="Kursverlauf 12 Monate {E(c["symbol"])}">',
           f'<polygon points="{area}" class="area"/>',
           f'<polyline points="{pts}" class="line"/>']
    used = []
    for label, v, col in lines:
        if not v:
            continue
        y = Y(v)
        ty = y + 4
        for u in used:
            if abs(ty - u) < 12:
                ty = u + 12 if ty >= u else u - 12
        used.append(ty)
        out.append(f'<line x1="{pl}" x2="{w-pr}" y1="{y:.1f}" y2="{y:.1f}" stroke="{col}" '
                   f'stroke-dasharray="4 4" stroke-width="1.2"/>')
        out.append(f'<text x="{w-pr+4}" y="{ty:.1f}" fill="{col}" class="lbl">{label} {de(v, 2)}</text>')
    ly = Y(ys[-1])
    out.append(f'<circle cx="{X(len(ys)-1):.1f}" cy="{ly:.1f}" r="3.5" class="dot"/>')
    d = c["chart"]["dates"]
    out.append(f'<text x="{pl}" y="{h-6}" class="ax">{d[0][:7]}</text>')
    out.append(f'<text x="{w-pr}" y="{h-6}" class="ax" text-anchor="end">{d[-1]}</text>')
    out.append("</svg>")
    return "".join(out)


def spark(vals, w=120, h=32):
    if not vals or len(vals) < 3:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i*(w-2)/(len(vals)-1)+1:.1f},{(hi-v)*(h-4)/rng+2:.1f}" for i, v in enumerate(vals))
    cls = "pos" if vals[-1] >= vals[0] else "neg"
    return f'<svg viewBox="0 0 {w} {h}" class="spark {cls}"><polyline points="{pts}"/></svg>'


def bar(counts):
    keys = [("strongBuy", "Strong Buy", "sb"), ("buy", "Buy", "b"), ("hold", "Hold", "h"),
            ("sell", "Sell", "s"), ("strongSell", "Strong Sell", "ss")]
    tot = sum((counts.get(k) or 0) for k, _, _ in keys)
    if not tot:
        return NA
    segs = "".join(f'<span class="seg {c}" style="width:{(counts.get(k) or 0)/tot*100:.1f}%" '
                   f'title="{l}: {counts.get(k) or 0}"></span>' for k, l, c in keys if counts.get(k))
    legend = " · ".join(f"{l} {counts.get(k) or 0}" for k, l, _ in keys)
    return f'<div class="recbar">{segs}</div><div class="small">{legend}</div>'


# ------------------------------------------------------------- Bausteine ----
def verdict_badge(a):
    comb = a.get("combined")
    p = f" · {pct(comb, 0)}" if comb is not None else ""
    return f'<span class="badge {a["cls"]}">{E(a["verdict"])}{p}</span>'


def news_list(d):
    items, seen = [], set()
    for it in (d.get("news") or []) + (d.get("news_fh") or []):
        t = (it.get("title") or "").strip()
        key = t.lower()[:60]
        if not t or key in seen:
            continue
        seen.add(key)
        items.append(it)
    items.sort(key=lambda x: x.get("date") or "", reverse=True)
    if not items:
        return f"<p>{NA} Keine aktuellen Nachrichten gefunden.</p>"
    lis = "".join(
        f'<li><a href="{E(i.get("url") or "#")}" target="_blank" rel="noopener">{E(i["title"])}</a>'
        f'<span class="small"> {E(i.get("date") or "")} · {E(i.get("source") or "")} (via {i["via"]})</span></li>'
        for i in items[:7])
    return f"<ul class='news'>{lis}</ul>"


def detail(c):
    d, inf, a = c.get("details", {}), c.get("info", {}), c["assessment"]
    cur = c["currency"]
    # Analysten
    counts = d.get("rec_counts") or d.get("finnhub_rec") or {}
    src = "Yahoo" if d.get("rec_counts") else ("Finnhub" if d.get("finnhub_rec") else None)
    ana = [f"<h4>Analysten</h4><dl class='kv'>",
           f"<dt>Konsens (1 = Strong Buy … 5 = Sell)</dt><dd>{n(c['rec_mean'], 2)} "
           f"<span class='small'>{E(c.get('rec_key') or '')}</span></dd>",
           f"<dt>Anzahl Analysten</dt><dd>{n(c['n_analysts'], 0)}</dd>",
           f"<dt>Kursziel Ø / Median</dt><dd>{price(c['target_mean'], cur)} / {price(c['target_median'], cur)}</dd>",
           f"<dt>Kursziel Spanne</dt><dd>{price(c['target_low'], cur)} – {price(c['target_high'], cur)}</dd>",
           f"<dt>Abstand Kurs → Ø-Ziel</dt><dd class='{sgn_cls(c['target_upside'])}'>{pct(c['target_upside'], 1, True)}</dd>",
           "</dl>", f"<div class='small'>Verteilung der Empfehlungen ({src or 'k. A.'}):</div>", bar(counts)]
    tr = d.get("finnhub_rec_trend")
    if tr:
        ana.append(f"<p class='small'>Kauf-Anteil laut Finnhub: {pct(tr['now_buy_share'], 0)} heute vs. "
                   f"{pct(tr['3m_ago_buy_share'], 0)} ({E(str(tr.get('period_old')))}).</p>")
    fmp = d.get("fmp_target")
    if fmp:
        ana.append(f"<p class='small'>Zweitquelle FMP: Kursziel-Konsens {price(fmp.get('consensus'), cur)} "
                   f"(Spanne {price(fmp.get('low'), cur)} – {price(fmp.get('high'), cur)}).</p>")
    rc = d.get("rating_changes_90d")
    if rc:
        ana.append(f"<p class='small'>Rating-Änderungen 90 Tage: {rc['up']} Hochstufungen, "
                   f"{rc['down']} Abstufungen, {rc['total']} Meldungen gesamt.</p>")
    if d.get("rating_actions"):
        ana.append("<ul class='small acts'>" + "".join(
            f"<li>{E(x['date'])} {E(str(x.get('firm') or ''))}: {E(str(x.get('from') or '–'))} → "
            f"{E(str(x.get('to') or ''))}" + (f", Ziel {de(x['target'], 2)}" if x.get("target") else "") +
            "</li>" for x in d["rating_actions"]) + "</ul>")

    # +20 %-Einschätzung
    cal = a.get("calib")
    prob = ["<h4>Wie realistisch sind +20 % in 40 Handelstagen?</h4>", verdict_badge(a),
            "<table class='mini'><tr><th>Messgröße</th><th>Wert</th></tr>",
            f"<tr><td>Modell aus Volatilität ({pct(c.get('vol60'), 0)} p. a.)</td><td>{pct(c.get('vol_prob'), 0)}</td></tr>",
            f"<tr><td>Trefferquote dieser Aktie, alle Tage (n = {n(c.get('base_all_n'), 0)})</td><td>{pct(c.get('base_all'), 0)}</td></tr>",
            f"<tr><td>… nur in ähnlicher Lage, 20–65 % unter Hoch (n = {n(c.get('base_cond_n'), 0)})</td><td>{pct(c.get('base_cond'), 0)}</td></tr>",
            (f"<tr><td>Backtest-Fälle mit ähnlichem Score {de(cal['lo'],2)}–{de(cal['hi'],2)} (n = {cal['n']})</td>"
             f"<td>{pct(cal['hit_rate'], 0)}</td></tr>" if cal else
             "<tr><td>Backtest-Fälle mit ähnlichem Score</td><td>" + NA + "</td></tr>"),
            f"<tr class='sum'><td>Mittelwert der verfügbaren Werte ({a['inputs']})</td><td>{pct(a.get('combined'), 0)}</td></tr>",
            "</table>"]
    if a["reasons"]:
        prob.append("<ul class='small'>" + "".join(f"<li>{E(r)}</li>" for r in a["reasons"]) + "</ul>")

    # Kennzahlen
    kz = [("Börsenwert", big(inf.get("marketCap")) + (" " + ccy(cur) if inf.get("marketCap") else "")),
          ("KGV (trailing / erwartet)", f"{n(inf.get('trailingPE'), 1)} / {n(inf.get('forwardPE'), 1)}"),
          ("EV/EBITDA", n(inf.get("enterpriseToEbitda"), 1)),
          ("Kurs-Buchwert", n(inf.get("priceToBook"), 2)),
          ("Umsatzwachstum (J/J)", pct(inf.get("revenueGrowth"), 1, True)),
          ("Gewinnwachstum (J/J)", pct(inf.get("earningsGrowth"), 1, True)),
          ("Nettomarge", pct(inf.get("profitMargins"), 1)),
          ("Verschuldung (Debt/Equity, %)", n(inf.get("debtToEquity"), 0)),
          ("Leerverkaufsquote", pct(inf.get("shortPercentOfFloat"), 1)),
          ("Beta", n(inf.get("beta"), 2)),
          ("Abstand 52W-Hoch", pct(-c.get("drawdown") if c.get("drawdown") is not None else None, 1)),
          ("Rendite 5 / 20 / 60 Tage", f"{pct(c.get('ret5'), 1, True)} / {pct(c.get('ret20'), 1, True)} / {pct(c.get('ret60'), 1, True)}"),
          ("RSI(14)", n(c.get("rsi14"), 0)),
          ("Wende-Signale", f"{round((c.get('turn_score') or 0)*5)} von 5"),
          ("Ø Tagesumsatz (20 T., EUR)", big(c.get("turnover_eur"))),
          ("Nächste Quartalszahlen", E(d.get("earnings_date") or "") + (f" <span class='small'>({d['earnings_src']})</span>" if d.get("earnings_date") else NA))]
    ins = d.get("insider_90d")
    if ins:
        kz.append(("Insider 90 T. (Finnhub)", f"{ins['buys']} Käufe ({big(ins['buy_value'])}) / "
                   f"{ins['sells']} Verkäufe ({big(ins['sell_value'])})"))
    if d.get("sec_form4_90d") is not None:
        kz.append(("Insider-Meldungen SEC Form 4 (90 T.)",
                   f"<a href='{E(d['sec_url'])}' target='_blank' rel='noopener'>{d['sec_form4_90d']}</a>"))
    if "av_sentiment" in d:
        s = d.get("av_sentiment")
        kz.append(("News-Stimmung Alpha Vantage (−1 … +1)",
                   (n(s, 2) + f" <span class='small'>({d.get('av_articles')} Artikel)</span>") if s is not None else NA))
    kzh = "<h4>Kennzahlen</h4><dl class='kv'>" + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in kz) + "</dl>"

    summ = inf.get("longBusinessSummary")
    firm = (f"<h4>Unternehmen</h4><p class='small'>{E(inf.get('sector') or '')} · {E(inf.get('industry') or '')}"
            f" · {E(inf.get('country') or '')} · Indizes: {E(', '.join(c.get('index', [])))}</p>" +
            (f"<p class='summary'>{E(summ[:420])}{'…' if len(summ) > 420 else ''} "
             f"<span class='small'>(Yahoo, englisch)</span></p>" if summ else f"<p>{NA} Beschreibung</p>"))
    return (f"<div class='detail'>{chart_svg(c)}<div class='cols'>"
            f"<div>{''.join(prob)}</div><div>{''.join(ana)}</div></div>"
            f"<div class='cols'><div>{kzh}</div><div>{firm}<h4>Aktuelle Nachrichten</h4>{news_list(d)}</div></div></div>")


def card(c, rank, changes):
    new = c["symbol"] in (changes.get("top_new") or []) and not changes.get("first_run")
    tag = "<span class='tag new'>neu</span>" if new else ""
    return (f"<details class='card'><summary><span class='rank'>{rank}</span>"
            f"<span class='nm'><b>{E(c['name'])}</b> <span class='sym'>{E(c['symbol'])}</span>{tag}"
            f"<span class='meta'>{price(c['price'], c['currency'])} · {pct(-c['drawdown'], 0)} vom Hoch · "
            f"Ziel {pct(c['target_upside'], 0, True)} · {n(c['n_analysts'], 0)} Analysten</span></span>"
            f"{verdict_badge(c['assessment'])}</summary>{detail(c)}</details>")


def chips(lst, cls):
    return " ".join(f"<span class='tag {cls}'>{E(s)}</span>" for s in lst) or "<span class='small'>keine</span>"


# ------------------------------------------------------------------ Seite ---
def render(ctx):
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    ch, rec, bt, mk = ctx["changes"], ctx["record"], ctx["backtest"], ctx["market"]
    P = ctx["params"]
    gen = datetime.fromisoformat(ctx["generated"]).strftime("%d.%m.%Y %H:%M UTC")

    # Änderungen
    if ch.get("first_run"):
        chg = "<p>Erster Lauf: noch kein Vortag zum Vergleich.</p>"
    else:
        chg = (f"<p class='small'>Vergleich mit {E(ch['prev_date'])}</p><dl class='kv'>"
               f"<dt>Neu in Top 10</dt><dd>{chips(ch['top_new'], 'new')}</dd>"
               f"<dt>Aus Top 10 raus</dt><dd>{chips(ch['top_out'], 'out')}</dd>"
               f"<dt>Neu auf Beobachtungsliste</dt><dd>{chips(ch['watch_new'], 'new')}</dd>"
               f"<dt>Ganz herausgefallen</dt><dd>{chips(ch['watch_out'], 'out')}</dd></dl>")

    # Bilanz
    s = rec["summary"]
    rows = "".join(
        f"<tr><td>{E(r['date'])}</td><td><b>{E(r['symbol'])}</b><br><span class='small'>{E((r.get('name') or '')[:28])}</span></td>"
        f"<td>{de(r['entry'], 2)}</td><td>{r['days']}/40</td><td class='{sgn_cls(r.get('max_gain'))}'>{pct(r.get('max_gain'), 1, True)}</td>"
        f"<td class='{sgn_cls(r.get('last_gain'))}'>{pct(r.get('last_gain'), 1, True)}</td>"
        f"<td><span class='st {('hit' if r['status']=='Ziel erreicht' else 'miss' if r['status']=='verfehlt' else 'open')}'>"
        f"{E(r['status'])}{(' (Tag ' + str(r['hit_day']) + ')') if r.get('hit_day') else ''}</span></td></tr>"
        for r in rec["picks"][:60])
    record_html = (
        f"<div class='tiles'><div><b>{s['total']}</b><span>Empfehlungen</span></div>"
        f"<div><b>{s['hits']}</b><span>Ziel erreicht</span></div>"
        f"<div><b>{s['closed'] - s['hits']}</b><span>verfehlt</span></div>"
        f"<div><b>{s['open']}</b><span>laufen noch</span></div>"
        f"<div><b>{pct(s['hit_rate'], 0) if s['hit_rate'] is not None else '–'}</b><span>Trefferquote (abgeschlossen)</span></div></div>"
        + (f"<div class='scroll'><table class='tbl'><tr><th>Datum</th><th>Aktie</th><th>Einstieg</th><th>Tage</th>"
           f"<th>Max.</th><th>Aktuell</th><th>Status</th></tr>{rows}</table></div>" if rows else
           "<p>Noch keine Empfehlungen in der Historie. Die Bilanz füllt sich ab dem ersten Tag; "
           "aussagekräftig wird sie erst nach einigen Wochen (jede Empfehlung braucht bis zu 40 Handelstage).</p>"))

    # Backtest
    if bt.get("error"):
        bt_html = f"<p>{E(bt['error'])}</p>"
    else:
        srows = "".join(
            f"<tr{' class=sum' if 'Radar' in k else ''}><td>{E(k)}</td><td>{v['n']:,}".replace(",", ".") +
            f"</td><td><b>{pct(v['hit_rate'], 1)}</b></td><td class='{sgn_cls(v['avg_ret'])}'>{pct(v['avg_ret'], 1, True)}</td>"
            f"<td>{pct(v['median_ret'], 1, True)}</td><td>{pct(v['loss_share'], 0)}</td><td>{pct(v['share_worse_20'], 0)}</td></tr>"
            for k, v in bt["strategies"].items() if v)
        yrows = "".join(f"<tr><td>{y['year']}</td><td>{y['n']}</td><td><b>{pct(y['hit_rate'], 1)}</b></td>"
                        f"<td>{pct(y['base_hit_rate'], 1)}</td><td class='{sgn_cls(y['avg_ret'])}'>{pct(y['avg_ret'], 1, True)}</td></tr>"
                        for y in bt["by_year"])
        rrows = "".join(f"<tr><td>{E(r['region'])}</td><td>{r['n']}</td><td>{pct(r['hit_rate'], 1)}</td>"
                        f"<td>{pct(r['avg_ret'], 1, True)}</td></tr>" for r in bt["by_region"])
        crows = "".join(f"<tr><td>{de(c['lo'],2)} – {de(c['hi'],2)}</td><td>{c['n']:,}".replace(",", ".") +
                        f"</td><td>{pct(c['hit_rate'], 1)}</td><td>{pct(c['avg_ret'], 1, True)}</td></tr>"
                        for c in bt["calibration"])
        main = bt["strategies"].get("Top 10 nach Kurs-Score (Radar-Regel)") or {}
        base = bt["strategies"].get("Alle Aktien im Universum (Basisrate)") or {}
        lift = (main.get("hit_rate") or 0) / base["hit_rate"] if base.get("hit_rate") else None
        bt_html = (
            f"<p>Zeitraum {E(bt['period'][0])} bis {E(bt['period'][1])}, {bt['rebalance_dates']} wöchentliche Stichtage, "
            f"{bt['universe_size']} Aktien. Treffer = Schlusskurs innerhalb von 40 Handelstagen ≥ +20 %.</p>"
            f"<div class='tiles'><div><b>{pct(main.get('hit_rate'), 1)}</b><span>Trefferquote Radar-Regel</span></div>"
            f"<div><b>{pct(base.get('hit_rate'), 1)}</b><span>Basisrate alle Aktien</span></div>"
            f"<div><b>{('×' + de(lift, 1)) if lift else '–'}</b><span>Faktor ggü. Zufall</span></div>"
            f"<div><b>{pct(bt.get('weeks_with_hit'), 0)}</b><span>Wochen mit ≥ 1 Treffer in Top 10</span></div></div>"
            f"<div class='scroll'><table class='tbl'><tr><th>Variante</th><th>Fälle</th><th>Treffer</th><th>Ø Rendite 40 T.</th>"
            f"<th>Median</th><th>Verlust-Anteil</th><th>Zwischen&shy;zeitlich ≤ −20 %</th></tr>{srows}</table></div>"
            f"<h4>Radar-Regel nach Jahr</h4><div class='scroll'><table class='tbl'><tr><th>Jahr</th><th>Fälle</th>"
            f"<th>Treffer</th><th>Basisrate</th><th>Ø Rendite</th></tr>{yrows}</table></div>"
            f"<h4>Nach Region</h4><div class='scroll'><table class='tbl'><tr><th>Region</th><th>Fälle</th><th>Treffer</th>"
            f"<th>Ø Rendite</th></tr>{rrows}</table></div>"
            f"<h4>Kalibrierung: Trefferquote nach Kurs-Score (alle Aktien mit Kursfilter)</h4>"
            f"<p class='small'>Zeigt, ob ein höherer Score tatsächlich häufiger zu +20 % geführt hat. Steigt die Quote "
            f"mit dem Score, trennt der Score sinnvoll.</p><div class='scroll'><table class='tbl'><tr><th>Score</th><th>Fälle</th>"
            f"<th>Treffer</th><th>Ø Rendite</th></tr>{crows}</table></div>"
            "<div class='warn'><b>Grenzen dieses Backtests</b><ul>"
            "<li><b>Ohne Analystenfilter:</b> Kostenlose Quellen liefern keine Analysten-Einschätzungen zu vergangenen "
            "Stichtagen. Getestet sind nur die Kursregeln (Stufe 1 und Kurs-Score).</li>"
            "<li><b>Survivorship-Bias</b> (Überlebenden-Verzerrung): Das Universum sind heutige Indexmitglieder. Firmen, die "
            "abgestürzt und aus Indizes geflogen sind, fehlen. Das schönt die Ergebnisse.</li>"
            "<li><b>Überlappung:</b> Wöchentliche Auswahl, 8-Wochen-Horizont. Dieselbe Aktie kann mehrfach zählen; die Fälle "
            "sind nicht unabhängig.</li>"
            "<li>Keine Kosten, Steuern oder Ausführungsverluste. Vergangene Treffer garantieren keine künftigen.</li></ul></div>")

    # Markt
    a = mk["assessment"]
    idx_rows = "".join(
        f"<tr><td>{E(v['name'])}</td><td>{de(v['value'], 2)}</td><td class='{sgn_cls(v['chg_1m'])}'>{pct(v['chg_1m'], 1, True)}</td>"
        f"<td class='{sgn_cls(v['chg_3m'])}'>{pct(v['chg_3m'], 1, True)}</td><td>{pct(v['vs_sma200'], 1, True)}</td>"
        f"<td>{spark(v['spark'])}</td></tr>" for v in mk["indices"].values())
    fred_rows = "".join(f"<tr><td>{E(v['label'])}</td><td>{de(v['value'], 2)}</td><td>"
                        f"{(de(v['chg_1m'], 2) + ' Pp.') if v.get('chg_1m') is not None else '–'}</td><td>{E(v['date'])}</td></tr>"
                        for v in mk["fred"].values())
    market_html = (f"<p class='verdict r{min(a['risk_points'], 3)}'>{E(a['verdict'])}</p>"
                   "<ul>" + "".join(f"<li>{E(l)}</li>" for l in a["lines"]) + "</ul>"
                   f"<div class='scroll'><table class='tbl'><tr><th>Index</th><th>Stand</th><th>1 Mon.</th><th>3 Mon.</th>"
                   f"<th>ggü. 200-T.</th><th>6 Mon.</th></tr>{idx_rows}</table></div>" +
                   (f"<div class='scroll'><table class='tbl'><tr><th>Zinsen &amp; Risiko (FRED)</th><th>Wert</th><th>30 Tage</th>"
                    f"<th>Stand</th></tr>{fred_rows}</table></div>" if fred_rows else
                    f"<p class='small'>{NA} FRED-Daten (Zinsen, Risikoaufschläge) nicht verfügbar.</p>"))

    # Beobachtungsliste
    watch_html = "".join(card(c, i + 1, {"top_new": [], "first_run": True}) for i, c in enumerate(ctx["watch"])) \
        or "<p>Keine weiteren Kandidaten.</p>"
    watch_note = ("<p class='small'>Beobachtungsliste: Aktien, die alle Regeln erfüllen, aber nicht in die Top 10 kamen, "
                  "sowie Aktien, die genau ein Analystenkriterium knapp verfehlen. Der Grund steht jeweils im Detail.</p>")
    for c in ctx["watch"]:
        miss = [k for k, v in c["checks"].items() if not v]
        if miss:
            c["assessment"]["reasons"].insert(0, "Nicht in Top 10, weil: " + ", ".join(
                {"rec": f"Analysten-Konsens schwächer als {de(P['MAX_RECOMMENDATION_MEAN'],1)}",
                 "n": f"weniger als {P['MIN_ANALYSTS']} Analysten",
                 "upside": f"Kursziel weniger als {int(P['MIN_TARGET_UPSIDE']*100)} % über Kurs"}[m] for m in miss))
    watch_html = "".join(card(c, i + 1, {"top_new": [], "first_run": True}) for i, c in enumerate(ctx["watch"])) \
        or "<p>Keine weiteren Kandidaten.</p>"

    # Quellen
    src_rows = "".join(
        f"<tr><td>{E(k)}</td><td class='small'>{E(v.get('used_for') or '')}</td><td>{v['ok']}</td>"
        f"<td class='{'neg' if v['fail'] else ''}'>{v['fail']}</td><td class='small'>{E('; '.join(v['notes']))}</td></tr>"
        for k, v in sorted(ctx["sources"].items()))
    uni_rows = "".join(f"<tr><td>{E(k)}</td><td>{v['count']}</td><td class='small'>{E(v['source'])}</td>"
                       f"<td>{E(v.get('as_of') or '–')}</td></tr>" for k, v in ctx["universe_info"].items())

    top_html = "".join(card(c, i + 1, ch) for i, c in enumerate(ctx["top"])) or \
        "<p>Heute erfüllt keine Aktie alle Regeln.</p>"
    synth = ("<div class='synth'>TESTLAUF MIT ERFUNDENEN ZUFALLSDATEN. Keine echten Kurse, nur zur Funktionsprüfung.</div>"
             if ctx["synthetic"] else "")

    page = TEMPLATE.format(
        synth=synth, gen=gen, data_date=E(ctx["data_date"]), n_uni=ctx["universe_n"],
        n_data=ctx["n_with_data"], n1=ctx["n_stage1"], n2=ctx["n_stage2"],
        market_verdict=E(a["verdict"]), mrisk=min(a["risk_points"], 3),
        top=top_html, watch=watch_note + watch_html, changes=chg, record=record_html,
        backtest=bt_html, market=market_html, src_rows=src_rows, uni_rows=uni_rows,
        dd_min=int(P["DRAWDOWN_MIN"] * 100), dd_max=int(P["DRAWDOWN_MAX"] * 100),
        vol_min=int(P["MIN_VOL_ANN"] * 100), turnover=de(P["MIN_DOLLAR_VOLUME"] / 1e6, 0),
        rec_max=de(P["MAX_RECOMMENDATION_MEAN"], 1), n_an=P["MIN_ANALYSTS"],
        up_min=int(P["MIN_TARGET_UPSIDE"] * 100), runtime=ctx["runtime_s"])
    (SITE_DIR / "index.html").write_text(page, encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")


TEMPLATE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aktien-Radar</title>
<meta name="robots" content="noindex">
<style>
:root{{--bg:#f6f5f1;--card:#fff;--ink:#1b1d21;--muted:#6b6f78;--line:#e4e2dc;--accent:#c2410c;
--good:#15803d;--mid:#b45309;--low:#b91c1c;--chip:#efede7;--areaf:rgba(194,65,12,.08)}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121316;--card:#1b1d21;--ink:#e9e7e2;--muted:#9a9ea7;
--line:#2c2f35;--accent:#fb923c;--good:#4ade80;--mid:#fbbf24;--low:#f87171;--chip:#26292f;--areaf:rgba(251,146,60,.10)}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:980px;margin:0 auto;padding:16px}}
header h1{{font-size:26px;margin:4px 0 2px;letter-spacing:-.02em}}
header .sub{{color:var(--muted);font-size:13px}}
nav{{position:sticky;top:0;background:var(--bg);z-index:5;padding:8px 0;margin:8px 0 4px;border-bottom:1px solid var(--line);
display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}}
nav a{{flex:none;color:var(--ink);text-decoration:none;font-size:13px;padding:5px 10px;border-radius:99px;background:var(--chip)}}
section{{margin:26px 0}} h2{{font-size:19px;margin:0 0 10px}} h4{{margin:14px 0 6px;font-size:14px}}
.funnel{{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}} .funnel span{{background:var(--chip);border-radius:8px;padding:4px 10px;font-size:13px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:8px 0}}
.card summary{{list-style:none;cursor:pointer;display:flex;gap:10px;align-items:center;padding:12px}}
.card summary::-webkit-details-marker{{display:none}}
.card[open] summary{{border-bottom:1px solid var(--line)}}
.rank{{flex:none;width:28px;height:28px;border-radius:50%;background:var(--chip);display:grid;place-items:center;font-weight:700;font-size:13px}}
.nm{{flex:1;min-width:0}} .nm b{{font-size:15px}} .sym{{color:var(--muted);font-size:12px;font-family:ui-monospace,monospace}}
.meta{{display:block;color:var(--muted);font-size:12.5px;margin-top:2px}}
.badge{{flex:none;font-size:12px;font-weight:600;padding:4px 8px;border-radius:99px;white-space:nowrap;border:1px solid}}
.badge.good{{color:var(--good)}} .badge.mid{{color:var(--mid)}} .badge.low{{color:var(--low)}} .badge.na{{color:var(--muted)}}
.detail{{padding:12px}} .cols{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
@media (max-width:720px){{.cols{{grid-template-columns:1fr}} .card summary{{flex-wrap:wrap}} .badge{{margin-left:38px}}}}
.chart{{width:100%;height:auto;display:block}} .chart .line{{fill:none;stroke:var(--accent);stroke-width:1.8}}
.chart .area{{fill:var(--areaf)}} .chart .dot{{fill:var(--accent)}} .chart .lbl{{font-size:11px}} .chart .ax{{font-size:11px;fill:var(--muted)}}
.spark{{width:110px;height:28px}} .spark polyline{{fill:none;stroke-width:1.5}} .spark.pos polyline{{stroke:var(--good)}} .spark.neg polyline{{stroke:var(--low)}}
dl.kv{{display:grid;grid-template-columns:auto 1fr;gap:3px 12px;margin:0;font-size:13.5px}} dl.kv dt{{color:var(--muted)}} dl.kv dd{{margin:0;text-align:right}}
.small{{font-size:12.5px;color:var(--muted)}} .na{{color:var(--muted);font-style:italic}}
.pos{{color:var(--good)}} .neg{{color:var(--low)}}
.recbar{{display:flex;height:9px;border-radius:5px;overflow:hidden;margin:6px 0 3px;background:var(--chip)}}
.seg.sb{{background:#15803d}} .seg.b{{background:#65a30d}} .seg.h{{background:#a8a29e}} .seg.s{{background:#ea580c}} .seg.ss{{background:#b91c1c}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--muted);font-weight:600;font-size:12px}} .mini td:last-child{{text-align:right;font-variant-numeric:tabular-nums}}
tr.sum td{{font-weight:700}} .tbl td{{font-variant-numeric:tabular-nums}} .scroll{{overflow-x:auto;margin:8px 0}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:10px 0}}
.tiles div{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}}
.tiles b{{display:block;font-size:20px}} .tiles span{{font-size:12px;color:var(--muted)}}
.tag{{display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:99px;margin:1px 2px;background:var(--chip)}}
.tag.new{{color:var(--good)}} .tag.out{{color:var(--low)}}
.st{{font-size:12px;font-weight:600}} .st.hit{{color:var(--good)}} .st.miss{{color:var(--low)}} .st.open{{color:var(--muted)}}
.news{{padding-left:18px;margin:4px 0}} .news li{{margin:4px 0;font-size:13.5px}} .news a{{color:var(--ink)}}
.acts{{padding-left:18px}} .summary{{font-size:13.5px}}
.verdict{{font-weight:600;padding:10px 12px;border-radius:10px;background:var(--card);border-left:4px solid var(--muted)}}
.verdict.r0{{border-color:var(--good)}} .verdict.r1,.verdict.r2{{border-color:var(--mid)}} .verdict.r3{{border-color:var(--low)}}
.warn{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--mid);border-radius:10px;padding:8px 14px;margin:12px 0;font-size:13.5px}}
.synth{{background:#b91c1c;color:#fff;font-weight:700;padding:10px;border-radius:8px;text-align:center}}
.disc{{font-size:12px;color:var(--muted);border-top:1px solid var(--line);padding-top:12px;margin-top:30px}}
details.gl summary{{cursor:pointer;font-weight:600}}
</style></head><body><div class="wrap">
{synth}
<header><h1>Aktien-Radar</h1>
<div class="sub">Stand {gen} · Kurse bis {data_date} (Schlusskurse) · Ziel: +20 % in 40 Handelstagen (≈ 8 Wochen)</div>
<div class="funnel"><span>{n_uni} Aktien im Universum</span><span>{n_data} mit aktuellen Kursen</span>
<span>{n1} bestehen Kursfilter</span><span>{n2} bestehen Analystenfilter</span></div>
<p class="verdict r{mrisk}">Markt: {market_verdict}</p></header>
<nav><a href="#top">Top 10</a><a href="#changes">Neu/Raus</a><a href="#watch">Beobachtung</a><a href="#record">Bilanz</a>
<a href="#backtest">Backtest</a><a href="#market">Markt</a><a href="#method">Methode</a><a href="#sources">Quellen</a></nav>

<section id="top"><h2>Top 10 Kandidaten</h2>
<p class="small">Antippen für Kursverlauf, Analysten, +20 %-Einschätzung, Kennzahlen und Nachrichten.</p>{top}</section>
<section id="changes"><h2>Neu dazugekommen / herausgefallen</h2>{changes}</section>
<section id="watch"><h2>Beobachtungsliste</h2>{watch}</section>
<section id="record"><h2>Bilanz der bisherigen Empfehlungen</h2>
<p class="small">Gezählt wird jede Aufnahme in die Top 10 (Schlusskurs am Empfehlungstag als Einstieg). Ziel erreicht = ein Schlusskurs
innerhalb von 40 Handelstagen ≥ +20 %. „Max.“ = höchster Stand im Zeitraum, „Aktuell“ = letzter Stand (bzw. nach 40 Tagen).</p>{record}</section>
<section id="backtest"><h2>Backtest: Wie gut hätten die Regeln früher funktioniert?</h2>{backtest}</section>
<section id="market"><h2>Marktlage</h2>{market}</section>

<section id="method"><h2>Methode</h2>
<ol>
<li><b>Universum:</b> S&amp;P 500, S&amp;P 400 (Mid Caps), Nasdaq 100, DAX, Euro Stoxx 50, dazu per Yahoo-Screener deutsche Werte
über 1 Mrd. € Börsenwert (deckt MDAX/TecDAX weitgehend ab) und große europäische Werte als Näherung an den Stoxx 600.</li>
<li><b>Stufe 1, Kursfilter:</b> {dd_min}–{dd_max} % unter dem 52-Wochen-Hoch, Volatilität ≥ {vol_min} % p. a., Kurs ≥ 3 €,
Median-Tagesumsatz ≥ {turnover} Mio. €.</li>
<li><b>Kurs-Score (0–1):</b> 45 % Modell-Wahrscheinlichkeit aus der Volatilität + 35 % historische Trefferquote der Aktie in ähnlicher
Lage + 20 % Wende-Signale (Kurs über 20-Tage-Schnitt, 20-Tage-Schnitt steigt, 10-Tage-Rendite positiv, RSI 40–70, kein neues Jahrestief in 10 Tagen).</li>
<li><b>Stufe 2, Analystenfilter:</b> Konsens ≤ {rec_max} (Kaufen-Bereich), mind. {n_an} Analysten, Ø-Kursziel ≥ {up_min} % über Kurs.</li>
<li><b>Rangfolge:</b> Kurs-Score × (0,7 + 0,3 × Analystenstärke). Analystenstärke = je zur Hälfte Kursziel-Abstand (bis 60 %) und Konsensnote.</li>
<li><b>+20 %-Einschätzung:</b> Mittelwert aus bis zu vier gemessenen Quoten (siehe je Aktie). „Realistisch“ ab 30 % und Kursziel ≥ +20 %,
„Möglich“ ab 15 %, darunter „Eher unwahrscheinlich“. Zum Vergleich: Für eine durchschnittliche Aktie liegt die Basisrate meist im
einstelligen Prozentbereich (siehe Backtest).</li></ol>
<details class="gl"><summary>Fachbegriffe</summary><dl class="kv" style="grid-template-columns:auto 1fr">
<dt>Drawdown</dt><dd style="text-align:left">Abstand zum 52-Wochen-Hoch in Prozent.</dd>
<dt>Volatilität p. a.</dt><dd style="text-align:left">Typische Schwankungsbreite der Tagesrenditen, aufs Jahr hochgerechnet. 30 % heißt: Innerhalb eines Jahres sind ±30 % eine normale Bewegung.</dd>
<dt>Spiegelungsprinzip</dt><dd style="text-align:left">Formel für die Wahrscheinlichkeit, dass ein zufällig schwankender Kurs eine Schwelle mindestens einmal berührt: 2·(1−Φ(ln 1,2 / (σ·√T))). Annahme: kein Trend.</dd>
<dt>Basisrate</dt><dd style="text-align:left">Wie oft etwas historisch ohne besondere Auswahl passiert ist. Maßstab, ob eine Regel überhaupt etwas bringt.</dd>
<dt>RSI(14)</dt><dd style="text-align:left">Relative-Stärke-Index über 14 Tage, 0–100. Unter 30 überverkauft, über 70 überkauft.</dd>
<dt>SMA</dt><dd style="text-align:left">Simple Moving Average, gleitender Durchschnitt der Schlusskurse.</dd>
<dt>KGV / EV/EBITDA</dt><dd style="text-align:left">Bewertung: Kurs je Gewinn bzw. Unternehmenswert je operativem Ergebnis vor Abschreibungen.</dd>
<dt>Leerverkaufsquote</dt><dd style="text-align:left">Anteil der frei handelbaren Aktien, auf deren Fall gewettet wird. Hoch = Potenzial für einen „Short Squeeze“, aber auch Skepsis.</dd>
<dt>Konsens 1–5</dt><dd style="text-align:left">Durchschnittliche Analystennote bei Yahoo: 1 Strong Buy, 2 Buy, 3 Hold, 4 Underperform, 5 Sell.</dd>
<dt>Survivorship-Bias</dt><dd style="text-align:left">Verzerrung, weil gescheiterte Firmen in heutigen Listen fehlen.</dd>
<dt>Form 4</dt><dd style="text-align:left">Pflichtmeldung bei der US-Börsenaufsicht SEC, wenn Insider Aktien kaufen oder verkaufen.</dd>
<dt>Sentiment-Score</dt><dd style="text-align:left">Stimmung in Nachrichtenartikeln, −1 sehr negativ bis +1 sehr positiv (Alpha Vantage).</dd>
</dl></details></section>

<section id="sources"><h2>Datenquellen heute</h2>
<p class="small">Erfolgreiche und fehlgeschlagene Abrufe. Fehlen Daten, steht auf der Seite „k. A.“ statt einer Schätzung.</p>
<div class="scroll"><table class="tbl"><tr><th>Quelle</th><th>Wofür</th><th>OK</th><th>Fehler</th><th>Hinweise</th></tr>{src_rows}</table></div>
<h4>Universum im Detail</h4>
<div class="scroll"><table class="tbl"><tr><th>Liste</th><th>Aktien</th><th>Quelle</th><th>Stand</th></tr>{uni_rows}</table></div></section>

<p class="disc">Keine Anlageberatung. Alle Angaben ohne Gewähr; automatisiert aus frei verfügbaren Quellen erstellt und nicht geprüft.
Kursziele und Empfehlungen geben Meinungen Dritter wieder. Hohe Volatilität bedeutet hohe Chancen <i>und</i> hohe Verlustrisiken.
Laufzeit des Datenabrufs: {runtime} s.</p>
</div></body></html>
"""
