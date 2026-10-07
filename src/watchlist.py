"""
Klaus - Watchlist und Kurs-Alarme (laeuft auf dem Server, ohne KI-Anfragen).

    /watchlist                      Kurse der Watchlist
    /watchlist add Nvidia           aufnehmen          /watchlist weg Tesla     entfernen
    /alarm                          offene Alarme      /alarm Nvidia unter 200  /alarm Bitcoin ueber 80000
    /alarm weg 2                    Alarm Nr. 2 loeschen

Alle 10 Minuten werden die Kurse geholt (Yahoo, ein Abruf je Wert). Ein Alarm loest EINMAL aus und ist danach erledigt.
Zusaetzlich: Meldung, wenn ein Wert der Watchlist an einem Tag um 5 % oder mehr springt (einmal je Wert und Tag).
Nur Information - keine Anlageberatung, keine Orders. Daten: data/watchlist.json (liegt im Server-Backup).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATEI = BASE_DIR / "data" / "watchlist.json"
TAKT_S = 600
SPRUNG_PROZ = 5.0
_sperre = threading.Lock()


def _leer() -> dict:
    return {"werte": {}, "alarme": [], "sprung_gemeldet": {}}


def laden() -> dict:
    try:
        return {**_leer(), **json.loads(DATEI.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return _leer()


def speichern(d: dict) -> None:
    DATEI.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DATEI)


def _de(z: float, stellen: int = 2) -> str:
    return f"{z:,.{stellen}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _zahl(text: str) -> float:
    """200 | 200,5 | 1.234,5 | 1.234 | 200.5 -> float"""
    t = text.strip().replace(" ", "").replace("€", "").replace("$", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    return float(t)


# ------------------------------------------------------------------ Kurse
def kurse_holen(symbole: list[str]) -> dict[str, dict]:
    """{symbol: {preis, waehrung, tag_proz, name}} - parallel, Fehler einzelner Werte werden uebersprungen."""
    import markt

    def eins(sym: str):
        try:
            m = markt._verlauf(sym, "5d")["meta"]
            preis = float(m["regularMarketPrice"])
            vortag = float(m.get("chartPreviousClose") or m.get("previousClose") or preis)
            return sym, {"preis": preis, "waehrung": m.get("currency", ""), "tag_proz": round((preis / vortag - 1) * 100, 2) if vortag else 0.0,
                         "name": m.get("shortName") or sym}
        except Exception as e:
            print(f"[Watchlist] Kurs {sym}: {str(e)[:60]}", flush=True)
            return sym, None

    if not symbole:
        return {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        return {s: k for s, k in pool.map(eins, sorted(set(symbole))) if k}


def _sprechname(sym: str, d: dict) -> str:
    return d["werte"].get(sym, {}).get("name") or sym


# ------------------------------------------------------------------ Watchlist
def hinzu(name: str) -> str:
    import markt

    try:
        sym = markt.symbol(name)
    except Exception as e:
        return str(e)[:120]
    k = kurse_holen([sym]).get(sym)
    with _sperre:
        d = laden()
        neu = sym not in d["werte"]
        d["werte"][sym] = {"name": (k or {}).get("name") or name.strip().title(), "seit": dt.date.today().isoformat()}
        speichern(d)
    zeile = f" ({_de(k['preis'])} {k['waehrung']}, {'+' if k['tag_proz'] >= 0 else ''}{_de(k['tag_proz'])} % heute)" if k else ""
    return f"{'Auf die Watchlist gesetzt' if neu else 'Schon auf der Watchlist'}: {d['werte'][sym]['name']} [{sym}]{zeile}."


def weg(name: str) -> str:
    import markt

    d = laden()
    n = name.strip().lower()
    treffer = [s for s, w in d["werte"].items() if n in (s.lower(), w["name"].lower()) or n in w["name"].lower()]
    if not treffer:
        try:
            treffer = [markt.symbol(name)] if markt.symbol(name) in d["werte"] else []
        except Exception:
            pass
    if not treffer:
        return f"„{name}“ ist nicht auf der Watchlist."
    with _sperre:
        d = laden()
        for s in treffer:
            d["werte"].pop(s, None)
        d["alarme"] = [a for a in d["alarme"] if a["symbol"] not in treffer]   # Alarme dazu verfallen mit
        speichern(d)
    return f"Von der Watchlist genommen: {', '.join(treffer)} (Alarme dazu gelöscht)."


def liste() -> str:
    d = laden()
    if not d["werte"]:
        return "Deine Watchlist ist leer. Zum Beispiel: /watchlist add Nvidia"
    k = kurse_holen(list(d["werte"]))
    zeilen = ["📊 Watchlist"]
    for sym, w in d["werte"].items():
        q = k.get(sym)
        zeilen.append(f"  {w['name'][:22]} [{sym}]  " + (f"{_de(q['preis'], 0 if q['preis'] > 1000 else 2)} {q['waehrung']}  "
                      f"{'▲' if q['tag_proz'] >= 0 else '▼'} {_de(abs(q['tag_proz']))} %" if q else "Kurs gerade nicht abrufbar"))
    return "\n".join(zeilen) + "\n\nNur Information, keine Anlageberatung."


def briefing_block() -> str:
    """Eine Zeile fuers Morgen-Briefing (leer, wenn die Watchlist leer ist)."""
    d = laden()
    if not d["werte"]:
        return ""
    k = kurse_holen(list(d["werte"]))
    teile = [f"{sym} {_de(q['preis'], 0 if q['preis'] > 1000 else 2)} ({'+' if q['tag_proz'] >= 0 else ''}{_de(q['tag_proz'], 1)} %)"
             for sym, q in ((s, k.get(s)) for s in d["werte"]) if q]
    return ("📊 Watchlist: " + " · ".join(teile)) if teile else ""


# ------------------------------------------------------------------ Alarme
def alarm_setzen(name: str, richtung: str, preis: float) -> str:
    import markt

    r = "unter" if richtung.lower() in ("unter", "<", "faellt", "fällt", "fallen") else "ueber"
    try:
        sym = markt.symbol(name)
    except Exception as e:
        return str(e)[:120]
    k = kurse_holen([sym]).get(sym)
    if not k:
        return f"Ich kann den Kurs von {name} gerade nicht abrufen, deshalb setze ich keinen Alarm."
    with _sperre:
        d = laden()
        d["werte"].setdefault(sym, {"name": k["name"], "seit": dt.date.today().isoformat()})   # Alarm nimmt den Wert auf die Watchlist
        d["alarme"].append({"symbol": sym, "richtung": r, "preis": float(preis), "waehrung": k["waehrung"],
                            "angelegt": dt.datetime.now().strftime("%d.%m. %H:%M")})
        speichern(d)
    schon = (r == "unter" and k["preis"] <= preis) or (r == "ueber" and k["preis"] >= preis)
    hinweis = (f"\n⚠️ Achtung: {k['name']} steht schon bei {_de(k['preis'])} {k['waehrung']} – der Alarm löst deshalb gleich aus."
               if schon else f"\nAktuell: {_de(k['preis'])} {k['waehrung']}.")
    return f"🔔 Alarm gesetzt: {k['name']} [{sym}] {'fällt unter' if r == 'unter' else 'steigt über'} {_de(preis)} {k['waehrung']}.{hinweis}"


def alarme_text() -> str:
    d = laden()
    offen = [a for a in d["alarme"] if not a.get("ausgeloest")]
    erledigt = [a for a in d["alarme"] if a.get("ausgeloest")][-3:]
    if not offen and not erledigt:
        return "Keine Alarme. Zum Beispiel: /alarm Nvidia unter 200"
    zeilen = ["🔔 Alarme"]
    for i, a in enumerate(d["alarme"], 1):
        if not a.get("ausgeloest"):
            zeilen.append(f"  {i}. {_sprechname(a['symbol'], d)} [{a['symbol']}] {'fällt unter' if a['richtung'] == 'unter' else 'steigt über'} "
                          f"{_de(a['preis'])} {a['waehrung']}  (seit {a['angelegt']})")
    for a in erledigt:
        zeilen.append(f"  ✔ {_sprechname(a['symbol'], d)} {'unter' if a['richtung'] == 'unter' else 'über'} {_de(a['preis'])} – ausgelöst {a['ausgeloest']}")
    return "\n".join(zeilen) + "\n\nLöschen: /alarm weg <Nr>"


def alarm_loeschen(nummer: int) -> str:
    with _sperre:
        d = laden()
        if not 1 <= nummer <= len(d["alarme"]):
            return f"Alarm {nummer} gibt es nicht. /alarm zeigt die Liste."
        a = d["alarme"].pop(nummer - 1)
        speichern(d)
    return f"Alarm gelöscht: {_sprechname(a['symbol'], d)} {'unter' if a['richtung'] == 'unter' else 'über'} {_de(a['preis'])}."


def pruefen(senden) -> int:
    """Einmal alle Alarme und Sprung-Meldungen pruefen. -> Anzahl gesendeter Meldungen."""
    d = laden()
    offen = [a for a in d["alarme"] if not a.get("ausgeloest")]
    symbole = {a["symbol"] for a in offen} | set(d["werte"])
    if not symbole:
        return 0
    k = kurse_holen(list(symbole))
    gesendet, geaendert = 0, False
    for a in offen:
        q = k.get(a["symbol"])
        if not q:
            continue
        if (a["richtung"] == "unter" and q["preis"] <= a["preis"]) or (a["richtung"] == "ueber" and q["preis"] >= a["preis"]):
            senden(f"🔔 {_sprechname(a['symbol'], d)} [{a['symbol']}] ist {'unter' if a['richtung'] == 'unter' else 'über'} "
                   f"{_de(a['preis'])} {a['waehrung']} {'gefallen' if a['richtung'] == 'unter' else 'gestiegen'}: jetzt {_de(q['preis'])} {q['waehrung']} "
                   f"({'+' if q['tag_proz'] >= 0 else ''}{_de(q['tag_proz'])} % heute).\nDer Alarm ist damit erledigt. "
                   f"Neuer Alarm: /alarm {_sprechname(a['symbol'], d).split()[0]} {'unter' if a['richtung'] == 'unter' else 'ueber'} <Preis>\n"
                   "Nur Information, keine Anlageberatung.")
            a["ausgeloest"] = dt.datetime.now().strftime("%d.%m. %H:%M")
            gesendet += 1
            geaendert = True
    heute = dt.date.today().isoformat()
    for sym in d["werte"]:
        q = k.get(sym)
        if q and abs(q["tag_proz"]) >= SPRUNG_PROZ and d["sprung_gemeldet"].get(sym) != heute:
            senden(f"{'📈' if q['tag_proz'] > 0 else '📉'} {_sprechname(sym, d)} [{sym}] bewegt sich heute stark: "
                   f"{'+' if q['tag_proz'] >= 0 else ''}{_de(q['tag_proz'])} % auf {_de(q['preis'])} {q['waehrung']}.\nNur Information, keine Anlageberatung.")
            d["sprung_gemeldet"][sym] = heute
            gesendet += 1
            geaendert = True
    if geaendert:
        with _sperre:   # frisch laden, damit zwischenzeitliche Aenderungen (neuer Alarm) nicht verloren gehen
            frisch = laden()
            for a in offen:
                for b in frisch["alarme"]:
                    if b["symbol"] == a["symbol"] and b["preis"] == a["preis"] and b["richtung"] == a["richtung"] and a.get("ausgeloest"):
                        b["ausgeloest"] = a["ausgeloest"]
            frisch["sprung_gemeldet"] = d["sprung_gemeldet"]
            speichern(frisch)
    return gesendet


def schleife(senden) -> None:
    time.sleep(60)
    while True:
        try:
            pruefen(senden)
        except Exception as e:
            print(f"[Watchlist] {e}", flush=True)
        time.sleep(TAKT_S)


def starte(senden) -> None:
    threading.Thread(target=schleife, args=(senden,), daemon=True, name="klaus-watchlist").start()


# ------------------------------------------------------------------ Telegram-Befehle
ALARM_MUSTER = re.compile(r"^(?P<name>.+?)\s+(?P<r>unter|ueber|über|<|>|faellt unter|fällt unter|steigt ueber|steigt über)\s+(?P<preis>[\d.,]+)\s*(?:€|\$|euro|dollar|usd|eur)?\s*$", re.I)


def watchlist_befehl(eingabe: str) -> str:
    teile = eingabe.strip().split(maxsplit=2)
    if len(teile) == 1:
        return liste()
    aktion, name = teile[1].lower(), (teile[2] if len(teile) > 2 else "")
    if aktion in ("add", "+", "neu", "hinzu", "rein") and name:
        return hinzu(name)
    if aktion in ("weg", "-", "del", "entfernen", "raus") and name:
        return weg(name)
    return "So geht's: /watchlist · /watchlist add Nvidia · /watchlist weg Tesla"


def alarm_befehl(eingabe: str) -> str:
    rest = eingabe.strip().split(maxsplit=1)
    arg = rest[1].strip() if len(rest) > 1 else ""
    if not arg:
        return alarme_text()
    m = re.match(r"^(weg|del|loeschen|löschen)\s+(\d+)$", arg, re.I)
    if m:
        return alarm_loeschen(int(m.group(2)))
    m = ALARM_MUSTER.match(arg)
    if not m:
        return "So geht's: /alarm Nvidia unter 200 · /alarm Bitcoin über 80000 · /alarm (Liste) · /alarm weg 2"
    try:
        return alarm_setzen(m.group("name"), m.group("r"), _zahl(m.group("preis")))
    except ValueError:
        return "Den Preis habe ich nicht verstanden (zum Beispiel 200 oder 1.234,50)."
