"""
Klaus - eigene Handelsstrategien fuer das Alpaca-PAPIER-Konto (laeuft auf dem Server, alle 5 Minuten, ohne KI-Anfragen).

    strategien.backtest(...)        Strategie mit den Tageskursen der letzten 2 Jahre durchspielen (nur Rechnen)
    strategien.anlegen(entwurf)     aktiv schalten (ohne Freigabe - nur Papier-Konto)
    strategien.starte(senden)       Hintergrund-Schleife: Signale pruefen, Papier-Orders, Meldung an Telegram

Strategie-Arten (feste Regeln, kein frei ausgefuehrter Code):
    trend      halten, solange der kurze gleitende Durchschnitt ueber dem langen liegt (kurz/lang Tage)
    rsi        kaufen, wenn RSI(14) unter `unter` faellt; verkaufen, wenn er ueber `ueber` steigt
    sparplan   alle `tage` Tage fuer betrag_usd kaufen, bis budget_usd investiert ist (verkauft nur per tp/sl)
Dazu optional Gewinnmitnahme (tp_proz) und Verlustbegrenzung (sl_proz) auf den Einstandspreis.

Sicherheit: handelt NUR, solange Alpaca im Papier-Modus ist (ALPACA_LIVE leer/0) - mit Echtgeld nie automatisch.
Grenzen (alle optional in der .env, Standard: keine): STRATEGIE_MAX_AKTIV, STRATEGIE_GESAMT_USD, STRATEGIE_MAX_ORDERS_TAG,
ALPACA_MAX_ORDER_USD. Immer: Kaufkraft des Kontos (inkl. Hebel/Margin), kein Leerverkauf, nach einer fehlgeschlagenen
Order 1 Stunde Pause fuer diese Strategie (kein Fehler-Spam).
`/strategien stop` haelt sofort alle an. Keine Anlageberatung. Daten: data/strategien.json (im Server-Backup).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import threading
import time
from pathlib import Path

import numpy as np

import alpaca_handel as alpaca

BASE_DIR = Path(__file__).resolve().parent.parent
DATEI = BASE_DIR / "data" / "strategien.json"
ART = "strategie"
TYPEN = ("trend", "rsi", "sparplan")
TAKT_S = 300
FEHLER_PAUSE_S = 3600
_sperre = threading.Lock()


class StrategieFehler(Exception):
    """Verstaendliche Meldung fuer Nikola."""


def _grenze(name: str) -> float | None:
    """Optionale Grenze aus der .env - leer/0/ungueltig = keine Grenze."""
    try:
        wert = float(os.getenv(name, "").strip() or 0)
    except ValueError:
        return None
    return wert if wert > 0 else None


def gesamt_usd() -> float | None:
    return _grenze("STRATEGIE_GESAMT_USD")


def max_aktiv() -> int | None:
    g = _grenze("STRATEGIE_MAX_AKTIV")
    return int(g) if g else None


def max_orders_tag() -> int | None:
    g = _grenze("STRATEGIE_MAX_ORDERS_TAG")
    return int(g) if g else None


# ------------------------------------------------------------------ Speicher
def laden() -> dict:
    try:
        d = json.loads(DATEI.read_text(encoding="utf-8"))
        return {"strategien": d.get("strategien", []), "live_gewarnt": d.get("live_gewarnt", "")}
    except (OSError, ValueError):
        return {"strategien": [], "live_gewarnt": ""}


def speichern(d: dict) -> None:
    DATEI.parent.mkdir(exist_ok=True)
    tmp = DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DATEI)


def _zahl(x: float, stellen: int = 2) -> str:
    return f"{x:,.{stellen}f}".replace(",", "_").replace(".", ",").replace("_", ".")


# ------------------------------------------------------------------ Regeln
def regeln_pruefen(typ: str, p: dict) -> dict:
    """Parameter mit Standardwerten auffuellen und auf sinnvolle Bereiche pruefen."""
    if typ not in TYPEN:
        raise StrategieFehler(f"Unbekannte Strategie-Art „{typ}“ – möglich: trend, rsi, sparplan.")
    zahl = lambda k, std: float(p[k]) if p.get(k) not in (None, "", 0) else std
    r = {"tp_proz": zahl("tp_proz", 0.0), "sl_proz": zahl("sl_proz", 0.0)}
    if typ == "trend":
        r.update(kurz=int(zahl("kurz", 20)), lang=int(zahl("lang", 50)))
        if not 2 <= r["kurz"] < r["lang"] <= 250:
            raise StrategieFehler("Trend: kurz muss kleiner als lang sein (2 bis 250 Tage).")
    elif typ == "rsi":
        r.update(unter=zahl("unter", 30), ueber=zahl("ueber", 70))
        if not 5 <= r["unter"] < r["ueber"] <= 95:
            raise StrategieFehler("RSI: unter muss kleiner als ueber sein (5 bis 95).")
    else:
        r.update(tage=int(zahl("tage", 7)))
        if not 1 <= r["tage"] <= 90:
            raise StrategieFehler("Sparplan: alle 1 bis 90 Tage.")
    if not (0 <= r["tp_proz"] <= 500 and 0 <= r["sl_proz"] <= 90):
        raise StrategieFehler("Gewinnmitnahme 0–500 %, Verlustbegrenzung 0–90 %.")
    return r


def soll_halten(typ: str, p: dict, kurse: np.ndarray, gehalten: bool) -> bool | None:
    """Signal aus abgeschlossenen Tageskursen. True = drin sein, False = raus, None = nichts aendern."""
    import markt

    if typ == "trend":
        k, l = markt._sma(kurse, p["kurz"]), markt._sma(kurse, p["lang"])
        if np.isnan(l[-1]):
            return None
        return bool(k[-1] > l[-1])
    if typ == "rsi":
        r = markt._rsi(kurse)[-1]
        if np.isnan(r):
            return None
        return True if r < p["unter"] else False if r > p["ueber"] else None
    return None   # sparplan: zeitgesteuert


def beschreibung(typ: str, p: dict) -> str:
    t = {"trend": f"Trend {p.get('kurz')}/{p.get('lang')} Tage", "rsi": f"RSI kaufen < {_zahl(p.get('unter', 0), 0)}, "
         f"verkaufen > {_zahl(p.get('ueber', 0), 0)}", "sparplan": f"Sparplan alle {p.get('tage')} Tage"}[typ]
    if p.get("tp_proz"):
        t += f", Gewinnmitnahme +{_zahl(p['tp_proz'], 0)} %"
    if p.get("sl_proz"):
        t += f", Stopp −{_zahl(p['sl_proz'], 0)} %"
    return t


# ------------------------------------------------------------------ Kurse
def _yahoo(sym: str) -> str:
    return sym.replace("/", "-") if "/" in sym else sym.replace(".", "-")


def tageskurse(sym: str, bereich: str = "2y") -> tuple[list[str], np.ndarray]:
    """Abgeschlossene Tagesschlusskurse (der laufende Tag zaehlt nicht)."""
    import markt

    v = markt._verlauf(_yahoo(sym), bereich)
    tage, kurse = v["tage"], v["kurse"]
    if tage and tage[-1] == dt.date.today().isoformat():
        tage, kurse = tage[:-1], kurse[:-1]
    if len(kurse) < 30:
        raise StrategieFehler(f"Zu wenig Kursdaten für {sym}.")
    return tage, np.array(kurse, dtype=float)


# ------------------------------------------------------------------ Backtest
def backtest(typ: str, sym: str, p: dict, betrag_usd: float, budget_usd: float, tage: list[str] | None = None,
             kurse: np.ndarray | None = None) -> dict:
    """Spielt die Strategie auf Tageskursen durch. Signal am Schluss von Tag i, ausgefuehrt zum Schluss von Tag i+1
    (kein Blick in die Zukunft). Keine Gebuehren/Slippage."""
    if kurse is None:
        tage, kurse = tageskurse(sym)
    start = max(60, p.get("lang", 0) + 1) if typ == "trend" else 30
    if len(kurse) <= start + 20:
        raise StrategieFehler(f"Zu wenig Kursdaten für einen Test mit {sym}.")
    bar, stueck, invest, einstand, gesperrt = budget_usd, 0.0, 0.0, 0.0, False
    trades, gewinne, verkaeufe, letzte_sparrate, werte = 0, 0, 0, -10 ** 9, []
    for i in range(start, len(kurse) - 1):
        preis = kurse[i + 1]
        gehalten = stueck > 0
        verkaufen = kaufen = False
        if gehalten and einstand:
            ver = (kurse[i] / einstand - 1) * 100
            if (p["tp_proz"] and ver >= p["tp_proz"]) or (p["sl_proz"] and ver <= -p["sl_proz"]):
                verkaufen, gesperrt = True, typ != "sparplan"
        if not verkaufen:
            if typ == "sparplan":
                kaufen = i - letzte_sparrate >= p["tage"] and invest + 1e-9 < budget_usd
            else:
                s = soll_halten(typ, p, kurse[: i + 1], gehalten)
                if s is False:
                    gesperrt = False
                    verkaufen = gehalten
                elif s is True and not gehalten and not gesperrt:
                    kaufen = True
        if verkaufen:
            erloes = stueck * preis
            gewinne += erloes > invest
            verkaeufe += 1
            bar, stueck, invest, einstand, trades = bar + erloes, 0.0, 0.0, 0.0, trades + 1
        elif kaufen:
            summe = min(betrag_usd, budget_usd - invest, bar)
            if summe > 1:
                neu = summe / preis
                einstand = (einstand * stueck + preis * neu) / (stueck + neu)
                stueck, invest, bar, trades = stueck + neu, invest + summe, bar - summe, trades + 1
                letzte_sparrate = i
        werte.append(bar + stueck * preis)
    w = np.array(werte)
    spitze = np.maximum.accumulate(w)
    return {"symbol": sym, "von": tage[start + 1] if tage else "", "bis": tage[-1] if tage else "",
            "rendite": (w[-1] / budget_usd - 1) * 100, "kaufen_halten": (kurse[-1] / kurse[start + 1] - 1) * 100,
            "max_verlust": float(((w - spitze) / spitze).min() * 100), "trades": trades,
            "trefferquote": gewinne / verkaeufe * 100 if verkaeufe else None, "endwert": float(w[-1])}


def backtest_text(typ: str, sym: str, p: dict, b: dict) -> str:
    t = (f"🧪 {sym} · {beschreibung(typ, p)} · {b['von']} bis {b['bis']}:\n"
         f"Strategie {b['rendite']:+.1f} % · einfach Kaufen+Halten {b['kaufen_halten']:+.1f} % · "
         f"größter Rückgang {b['max_verlust']:.1f} % · {b['trades']} Trades")
    if b["trefferquote"] is not None:
        t += f" · {b['trefferquote']:.0f} % Gewinner"
    return t.replace(".", ",") + "\nVergangenheit, ohne Gebühren – keine Garantie für die Zukunft."


def testen(typ: str, name: str, params: dict, betrag_usd: float | None = None, budget_usd: float | None = None) -> str:
    try:
        sym = alpaca.symbol(name)
        p = regeln_pruefen(typ, params)
        betrag = float(betrag_usd or 1000)
        b = backtest(typ, sym, p, betrag, float(budget_usd or (betrag * 10 if typ == "sparplan" else betrag)))
        return backtest_text(typ, sym, p, b)
    except (StrategieFehler, alpaca.HandelFehler, LookupError) as e:
        return str(e)
    except Exception as e:
        return f"Der Test ging nicht: {str(e)[:120]}"


# ------------------------------------------------------------------ Anlegen / Verwalten
def vorbereiten(typ: str, name: str, params: dict, betrag_usd: float, budget_usd: float | None, titel: str = "") -> dict:
    """Prueft alles und testet die Strategie. -> Entwurf (noch nicht aktiv)."""
    if alpaca.live():
        raise StrategieFehler("Alpaca steht auf ECHTGELD – automatische Strategien gibt es nur auf dem Papier-Konto.")
    sym = alpaca.symbol(name)
    p = regeln_pruefen(typ, params)
    betrag = float(betrag_usd or 0)
    grenze = alpaca.max_order_usd()
    if betrag < 1 or (grenze and betrag > grenze):
        raise StrategieFehler("Betrag je Order: ab 1 $" + (f" bis {_zahl(grenze, 0)} $ (ALPACA_MAX_ORDER_USD)." if grenze else "."))
    budget = float(budget_usd or (betrag * 10 if typ == "sparplan" else betrag))
    if budget < betrag:
        raise StrategieFehler("Das Budget muss mindestens so groß sein wie der Betrag je Order.")
    aktive = [s for s in laden()["strategien"] if s["aktiv"]]
    if max_aktiv() and len(aktive) >= max_aktiv():
        raise StrategieFehler(f"Es laufen schon {max_aktiv()} Strategien (STRATEGIE_MAX_AKTIV) – erst eine pausieren oder löschen.")
    if gesamt_usd() and sum(s["budget_usd"] for s in aktive) + budget > gesamt_usd():
        raise StrategieFehler(f"Zusammen wären es mehr als {_zahl(gesamt_usd(), 0)} $ Strategie-Budget (STRATEGIE_GESAMT_USD).")
    if any(s["symbol"] == sym and s["aktiv"] for s in aktive):
        raise StrategieFehler(f"Für {sym} läuft schon eine Strategie – je Wert nur eine.")
    b = backtest(typ, sym, p, betrag, budget)
    return {"id": secrets.token_hex(3), "titel": (titel or f"{sym} {typ}")[:40], "symbol": sym, "typ": typ, "p": p,
            "betrag_usd": betrag, "budget_usd": budget, "test": backtest_text(typ, sym, p, b)}


def anlegen(entwurf: dict) -> str:
    """Schaltet die Strategie ein (ohne Freigabe: Strategien handeln ohnehin nur Papiergeld)."""
    if alpaca.live():
        raise StrategieFehler("Alpaca steht inzwischen auf ECHTGELD – ich schalte nichts ein.")
    s = {**{k: entwurf[k] for k in ("id", "titel", "symbol", "typ", "p", "betrag_usd", "budget_usd")},
         "aktiv": True, "erstellt": dt.date.today().isoformat(), "stueck": 0.0, "investiert": 0.0, "einstand": 0.0,
         "offen": None, "gesperrt": False, "letzte_sparrate": "", "orders_tag": ["", 0], "protokoll": []}
    with _sperre:
        d = laden()
        d["strategien"].append(s)
        speichern(d)
    return f"▶️ Strategie {s['id']} „{s['titel']}“ läuft (Papier-Konto). Ich melde jede Order hier."


def _finden(d: dict, nummer: str) -> dict:
    nr = (nummer or "").strip().lower()
    treffer = [s for s in d["strategien"] if s["id"] == nr or s["titel"].lower() == nr]
    if len(treffer) != 1:
        raise StrategieFehler(f"Keine Strategie mit der Nummer „{nummer}“. Schau mit /strategien nach.")
    return treffer[0]


def pausieren(nummer: str) -> str:
    with _sperre:
        d = laden()
        s = _finden(d, nummer)
        s["aktiv"] = False
        speichern(d)
    return f"⏸ Strategie {s['id']} pausiert. Die Position ({s['stueck']:g} Stück {s['symbol']}) bleibt im Depot."


def alle_stoppen() -> str:
    with _sperre:
        d = laden()
        n = sum(1 for s in d["strategien"] if s["aktiv"])
        for s in d["strategien"]:
            s["aktiv"] = False
        speichern(d)
    return f"🛑 Alle Strategien angehalten ({n}). Positionen bleiben im Depot, offene Orders siehst du mit /alpaca."


def fortsetzen_pruefen(nummer: str) -> dict:
    d = laden()
    s = _finden(d, nummer)
    if s["aktiv"]:
        raise StrategieFehler(f"Strategie {s['id']} läuft schon.")
    if alpaca.live():
        raise StrategieFehler("Alpaca steht auf ECHTGELD – automatische Strategien nur mit Papier.")
    aktive = [x for x in d["strategien"] if x["aktiv"]]
    if (max_aktiv() and len(aktive) >= max_aktiv()) or (gesamt_usd() and sum(x["budget_usd"] for x in aktive) + s["budget_usd"] > gesamt_usd()):
        raise StrategieFehler("Dann wären es zu viele Strategien oder zu viel Budget.")
    return s


def fortsetzen(sid: str) -> str:
    fortsetzen_pruefen(sid)
    with _sperre:
        d = laden()
        s = _finden(d, sid)
        s["aktiv"] = True
        speichern(d)
    return f"▶️ Strategie {s['id']} läuft wieder."


def loeschen(nummer: str) -> str:
    with _sperre:
        d = laden()
        s = _finden(d, nummer)
        d["strategien"].remove(s)
        speichern(d)
    rest = f" {s['stueck']:g} Stück {s['symbol']} bleiben im Depot." if s["stueck"] else ""
    return f"🗑 Strategie {s['id']} gelöscht.{rest}"


def liste() -> str:
    d = laden()
    if not d["strategien"]:
        return "Noch keine Strategien. Sag z. B. „Entwirf mir eine Trend-Strategie für Nvidia und teste sie“."
    z = [f"🤖 Strategien ({'Papier' if not alpaca.live() else 'ECHTGELD-Modus: alle ruhen'}):"]
    for s in d["strategien"]:
        pos = f"{s['stueck']:g} Stück, Einstand {_zahl(s['einstand'])} $" if s["stueck"] else "keine Position"
        z.append(f"{'▶️' if s['aktiv'] else '⏸'} {s['id']} · {s['titel']} · {beschreibung(s['typ'], s['p'])} · "
                 f"{_zahl(s['betrag_usd'], 0)} $/Order, Budget {_zahl(s['budget_usd'], 0)} $ · {pos}")
        if s["protokoll"]:
            z.append(f"   zuletzt: {s['protokoll'][-1]}")
    z.append("Stoppen: /strategien stop")
    return "\n".join(z)


def befehl(eingabe: str) -> str:
    """/strategien [stop] - ohne KI"""
    teile = eingabe.strip().split()
    if len(teile) > 1 and teile[1].lower() in ("stop", "stopp", "aus", "halt"):
        return alle_stoppen()
    return liste()


# ------------------------------------------------------------------ Hintergrund
def _log(s: dict, text: str) -> None:
    s["protokoll"] = (s["protokoll"] + [f"{dt.datetime.now():%d.%m. %H:%M} {text}"])[-20:]


def _order(s: dict, seite: str, senden, grund: str, **menge) -> None:
    heute = dt.date.today().isoformat()
    if s["orders_tag"][0] != heute:
        s["orders_tag"] = [heute, 0]
    if max_orders_tag() and s["orders_tag"][1] >= max_orders_tag():
        return
    s["orders_tag"][1] += 1
    try:
        auftrag = alpaca.vorbereiten("kaufen" if seite == "buy" else "verkaufen", s["symbol"], **menge)
        o = alpaca.papier_automatisch(auftrag)
    except alpaca.HandelFehler as e:
        s["pause_bis"] = time.time() + FEHLER_PAUSE_S
        _log(s, f"Order ging nicht: {e}")
        senden(f"🤖 Strategie {s['id']} ({s['symbol']}): {grund}, aber die Order ging nicht: {str(e)[:160]} "
               "– ich versuche es in einer Stunde wieder.")
        return
    s["offen"] = {"id": o["id"], "seite": seite}
    _log(s, f"{'Kauf' if seite == 'buy' else 'Verkauf'} gesendet ({grund})")
    senden(f"🤖 Strategie {s['id']} „{s['titel']}“: {grund} → {auftrag.text.replace('Papier-Konto · ', '')}. Papier-Konto.")


def _offene_order_abgleichen(s: dict, senden) -> None:
    o = alpaca.order(s["offen"]["id"])
    if not o:
        s["offen"] = None
        return
    status = o.get("status", "")
    if status not in ("filled", "canceled", "expired", "rejected", "done_for_day"):
        return
    menge, preis = float(o.get("filled_qty") or 0), float(o.get("filled_avg_price") or 0)
    gewinn = (preis - s["einstand"]) * menge if s["offen"]["seite"] == "sell" and menge else 0.0
    if menge:   # fuer den Wochenbericht
        s["historie"] = (s.get("historie", []) + [{"datum": dt.date.today().isoformat(), "seite": s["offen"]["seite"],
                                                    "menge": menge, "preis": preis, "gewinn": round(gewinn, 2)}])[-200:]
        s["realisiert"] = round(s.get("realisiert", 0.0) + gewinn, 2)
    if s["offen"]["seite"] == "buy" and menge:
        s["einstand"] = (s["einstand"] * s["stueck"] + preis * menge) / (s["stueck"] + menge)
        s["stueck"] += menge
        s["investiert"] += menge * preis
    elif menge:
        s["stueck"] = max(0.0, round(s["stueck"] - menge, 9))
        s["investiert"] = s["einstand"] * s["stueck"]
        _staub_entfernen(s)
        if not s["stueck"]:
            s["einstand"] = 0.0
        _log(s, f"verkauft {menge:g} zu {_zahl(preis)} $ ({'+' if gewinn >= 0 else '−'}{_zahl(abs(gewinn))} $)")
        senden(f"🤖 Strategie {s['id']}: Verkauf ausgeführt, {menge:g} {s['symbol']} zu {_zahl(preis)} $, "
               f"{'Gewinn' if gewinn >= 0 else 'Verlust'} {_zahl(abs(gewinn))} $ (Papier).")
    if status != "filled" and not menge:
        _log(s, f"Order {status}")
    s["offen"] = None


STAUB = 1e-8   # Alpaca nimmt keine Order unter 1e-9 Stueck - so kleine Reste sind Rundungsstaub, keine Position


def _staub_entfernen(s: dict) -> None:
    """Rest wie 3e-17 Stueck nach einem Verkauf (Gleitkomma) gilt als "nichts mehr gehalten". Sonst meldet die Strategie
    stuendlich ein Verkaufssignal und Alpaca lehnt ab: "qty must be > 1e-9"."""
    if 0 < s["stueck"] < STAUB:
        _log(s, f"Rest von {s['stueck']:.1e} Stück ignoriert (Rundung)")
        s["stueck"], s["einstand"], s["investiert"] = 0.0, 0.0, 0.0


def schritt(s: dict, senden, markt_offen: bool, jetzt: float | None = None) -> None:
    """Eine Strategie einmal pruefen (aus der Schleife; testbar)."""
    if s["offen"]:
        _offene_order_abgleichen(s, senden)
        if s["offen"]:
            return
    _staub_entfernen(s)   # auch Staub aus frueheren Verkaeufen (gespeicherter Stand)
    if time.time() < s.get("pause_bis", 0):   # nach einer fehlgeschlagenen Order kurz Ruhe
        return
    krypto = "/" in s["symbol"]
    if not (krypto or markt_offen):
        return
    tage, kurse = tageskurse(s["symbol"], "1y")
    p, gehalten = s["p"], s["stueck"] > 0
    if gehalten and s["einstand"]:
        preis = alpaca.kurs(s["symbol"])
        ver = (preis / s["einstand"] - 1) * 100
        if p.get("tp_proz") and ver >= p["tp_proz"]:
            s["gesperrt"] = s["typ"] != "sparplan"
            return _order(s, "sell", senden, f"Gewinnmitnahme bei {ver:+.1f} %", stueck=s["stueck"])
        if p.get("sl_proz") and ver <= -p["sl_proz"]:
            s["gesperrt"] = s["typ"] != "sparplan"
            return _order(s, "sell", senden, f"Stopp bei {ver:+.1f} %", stueck=s["stueck"])
    if s["typ"] == "sparplan":
        heute = dt.date.today()
        letzte = dt.date.fromisoformat(s["letzte_sparrate"]) if s["letzte_sparrate"] else None
        rest = s["budget_usd"] - s["investiert"]
        if (letzte is None or (heute - letzte).days >= p["tage"]) and rest >= 1:
            s["letzte_sparrate"] = heute.isoformat()
            return _order(s, "buy", senden, "Sparrate", betrag_usd=round(min(s["betrag_usd"], rest), 2))
        return
    signal = soll_halten(s["typ"], p, kurse, gehalten)
    if signal is False:
        s["gesperrt"] = False
        if gehalten:
            return _order(s, "sell", senden, "Verkaufssignal", stueck=s["stueck"])
    elif signal is True and not gehalten and not s["gesperrt"]:
        summe = min(s["betrag_usd"], s["budget_usd"])
        return _order(s, "buy", senden, "Kaufsignal", betrag_usd=round(summe, 2))


def pruefen(senden) -> None:
    with _sperre:
        d = laden()
    aktive = [s for s in d["strategien"] if s["aktiv"] or s["offen"]]
    if not aktive:
        return
    if alpaca.live():   # Echtgeld: nie automatisch - einmal am Tag Bescheid sagen
        heute = dt.date.today().isoformat()
        if d["live_gewarnt"] != heute:
            senden("🤖 Alpaca steht auf ECHTGELD – deine Strategien ruhen, sie handeln nur auf dem Papier-Konto.")
            with _sperre:
                frisch = laden()
                frisch["live_gewarnt"] = heute
                speichern(frisch)
        return
    markt_offen = bool((alpaca._api("GET", "/v2/clock") or {}).get("is_open"))
    for s in aktive:
        try:
            if s["aktiv"]:
                schritt(s, senden, markt_offen)
            elif s["offen"]:
                _offene_order_abgleichen(s, senden)
        except Exception as e:
            print(f"[Strategien] {s['id']}: {e}", flush=True)
    with _sperre:   # nur die Laufdaten zurueckschreiben, Pausieren/Loeschen von zwischendurch gewinnt
        frisch = laden()
        neu = {s["id"]: s for s in aktive}
        for i, s in enumerate(frisch["strategien"]):
            if s["id"] in neu:
                n = neu[s["id"]]
                frisch["strategien"][i] = {**n, "aktiv": s["aktiv"]}
        speichern(frisch)


def schleife(senden) -> None:
    time.sleep(90)
    while True:
        try:
            if alpaca.konfiguriert():
                pruefen(senden)
        except Exception as e:
            print(f"[Strategien] {e}", flush=True)
        time.sleep(TAKT_S)


def starte(senden) -> None:
    threading.Thread(target=schleife, args=(senden,), daemon=True, name="klaus-strategien").start()
