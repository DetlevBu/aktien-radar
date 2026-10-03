"""Hilfsfunktionen: HTTP mit Wiederholung, Quellen-Protokoll, sichere Zahlen."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone

import requests

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (aktien-radar; research)"})


class SourceLog:
    """Protokolliert pro Datenquelle Erfolge und Fehler.

    Wird auf der Webseite angezeigt, damit sichtbar ist, welche Daten heute
    tatsächlich geliefert wurden und wo etwas fehlt.
    """

    def __init__(self):
        self.entries: dict[str, dict] = {}

    def _e(self, name):
        return self.entries.setdefault(
            name, {"ok": 0, "fail": 0, "notes": [], "used_for": ""})

    def ok(self, name, n=1):
        self._e(name)["ok"] += n

    def fail(self, name, note=None):
        e = self._e(name)
        e["fail"] += 1
        if note and len(e["notes"]) < 5 and note not in e["notes"]:
            e["notes"].append(str(note)[:200])

    def describe(self, name, used_for):
        self._e(name)["used_for"] = used_for

    def to_dict(self):
        return self.entries


LOG = SourceLog()


def http_get(url, source, params=None, headers=None, timeout=20, retries=2,
             as_json=True):
    """GET mit Wiederholung. Gibt None zurück und protokolliert bei Fehler."""
    last = None
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 429:
                last = "429 Rate-Limit"
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code >= 400:
                last = f"HTTP {r.status_code}"
                if r.status_code in (401, 402, 403, 404):
                    break
                time.sleep(2)
                continue
            LOG.ok(source)
            return r.json() if as_json else r.text
        except Exception as ex:  # Netzwerk- oder JSON-Fehler
            last = type(ex).__name__ + ": " + str(ex)[:100]
            time.sleep(2)
    LOG.fail(source, last)
    return None


def num(x):
    """In float wandeln; None bei fehlenden/ungültigen Werten."""
    try:
        if x is None:
            return None
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def now_utc():
    return datetime.now(timezone.utc)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, default=_default)


def _default(o):
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "item"):
        return o.item()
    return str(o)
