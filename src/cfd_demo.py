"""
Klaus - CFD-Handel auf dem DEMO-Konto von Capital.com (Spielgeld). Laeuft auf dem Server, alle 5 Minuten, ohne KI-Anfragen.
Wunsch Nikola (17.10.2026): CFDs mit Hebel, autonom - NUR Demo. Eine Live-Adresse steht absichtlich nirgends in diesem Modul.

    konto_text()                         Kontostand, Hebel, offene Positionen
    suchen("gold")                       Maerkte finden (epic fuer Strategien)
    testen(typ, epic, params)            Backtest auf Stundenkursen (bis 1000 Kerzen)
    anlegen(...) / liste() / pausieren(nr) / fortsetzen(nr) / loeschen(nr) / alle_stoppen() / alles_schliessen()
    starte(senden)                       Hintergrund-Schleife: Signale pruefen, Positionen oeffnen/schliessen, Meldung an Telegram

Strategie-Arten (feste Regeln, kein frei ausgefuehrter Code), richtung = beide | long | short:
    trend     kurzer SMA ueber langem -> long, darunter -> short
    rsi       RSI(14) unter `unter` -> long, ueber `ueber` -> short, zurueck ueber/unter 50 -> raus
    ausbruch  Schlusskurs ueber dem Hoch der letzten `fenster` Kerzen -> long, unter dem Tief -> short
Jede Position bekommt Stop-Loss (sl_proz) und Gewinnziel (tp_proz) beim Broker. Der Hebel ist der des Kontos
(EU-Grenzen fuer Privatkunden, z. B. Indizes 20:1, Devisen 30:1, Aktien 5:1, Krypto 2:1).

.env (Server): CAPITAL_API_KEY, CAPITAL_LOGIN (E-Mail), CAPITAL_PASSWORT (das eigene Passwort des API-Schluessels).
Per Telegram: /cfd_schluessel <API-Key> <E-Mail> <Passwort> (Nachricht wird sofort geloescht). Keine Anlageberatung.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

import numpy as np
import requests

DEMO = "https://demo-api-capital.backend-capital.com/api/v1"
BASE_DIR = Path(__file__).resolve().parent.parent
DATEI = BASE_DIR / "data" / "cfd_strategien.json"
TAKT_S = 300
FEHLER_PAUSE_S = 3600
TYPEN = ("trend", "rsi", "ausbruch")
AUFLOESUNGEN = ("MINUTE_15", "MINUTE_30", "HOUR", "HOUR_4", "DAY")
_sperre = threading.RLock()


class CfdFehler(RuntimeError):
    pass


# ---------------------------------------------------------------- Verbindung (nur Demo)
def konfiguriert() -> bool:
    return all(os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_LOGIN", "CAPITAL_PASSWORT"))


class _Sitzung:
    """Capital.com: POST /session -> CST + X-SECURITY-TOKEN (gelten 10 min nach der letzten Nutzung)."""

    def __init__(self) -> None:
        self.kopf: dict = {}
        self.zuletzt = 0.0
        self.lock = threading.Lock()

    def _anmelden(self, key: str | None = None, login: str | None = None, passwort: str | None = None) -> dict:
        key = key or os.getenv("CAPITAL_API_KEY", "").strip()
        r = requests.post(f"{DEMO}/session", timeout=20, headers={"X-CAP-API-KEY": key, "Content-Type": "application/json"},
                          json={"identifier": login or os.getenv("CAPITAL_LOGIN", "").strip(),
                                "password": passwort or os.getenv("CAPITAL_PASSWORT", "").strip(), "encryptedPassword": False})
        if r.status_code != 200 or not r.headers.get("CST"):
            raise CfdFehler(f"Anmeldung bei Capital.com (Demo) abgelehnt: HTTP {r.status_code} {r.text[:120]}")
        return {"X-CAP-API-KEY": key, "CST": r.headers["CST"], "X-SECURITY-TOKEN": r.headers.get("X-SECURITY-TOKEN", ""),
                "Content-Type": "application/json"}

    def anfrage(self, methode: str, pfad: str, **kw):
        if not konfiguriert():
            raise CfdFehler("Capital.com ist nicht eingerichtet (/cfd_schluessel <API-Key> <E-Mail> <Passwort>).")
        with self.lock:
            if not self.kopf or time.time() - self.zuletzt > 8 * 60:
                self.kopf = self._anmelden()
            kopf = dict(self.kopf)
        r = requests.request(methode, f"{DEMO}{pfad}", headers=kopf, timeout=25, **kw)
        if r.status_code == 401:   # Sitzung abgelaufen -> einmal neu anmelden
            with self.lock:
                self.kopf = self._anmelden()
                kopf = dict(self.kopf)
            r = requests.request(methode, f"{DEMO}{pfad}", headers=kopf, timeout=25, **kw)
        self.zuletzt = time.time()
        if r.status_code >= 400:
            raise CfdFehler(f"Capital.com: HTTP {r.status_code} {r.text[:160]}")
        return r.json() if r.content else {}


S = _Sitzung()


# ---------------------------------------------------------------- Konto, Maerkte, Kurse
def _zahl(x: float, nachkomma: int = 2) -> str:
    return f"{x:,.{nachkomma}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def positionen() -> list[dict]:
    aus = []
    for p in S.anfrage("GET", "/positions").get("positions", []):
        pos, markt = p.get("position", {}), p.get("market", {})
        aus.append({"deal_id": pos.get("dealId"), "epic": markt.get("epic"), "name": markt.get("instrumentName", markt.get("epic")),
                    "richtung": pos.get("direction"), "groesse": float(pos.get("size") or 0), "einstieg": float(pos.get("level") or 0),
                    "gv": float(pos.get("upl") or 0), "hebel": pos.get("leverage")})
    return aus


def konto_text() -> str:
    konten = S.anfrage("GET", "/accounts").get("accounts", [])
    konto = next((k for k in konten if k.get("preferred")), konten[0] if konten else {})
    b, w = konto.get("balance", {}), konto.get("currency", "")
    zeilen = [f"📊 Capital.com DEMO (Spielgeld): Guthaben {_zahl(float(b.get('balance') or 0))} {w}, "
              f"offener G/V {_zahl(float(b.get('profitLoss') or 0))} {w}, verfügbar {_zahl(float(b.get('available') or 0))} {w}"]
    try:
        hebel = S.anfrage("GET", "/accounts/preferences").get("leverages", {})
        if hebel:
            zeilen.append("Hebel: " + ", ".join(f"{k.title()} {v.get('current', v) if isinstance(v, dict) else v}:1" for k, v in hebel.items()))
    except CfdFehler:
        pass
    pos = positionen()
    zeilen.append("Positionen:" if pos else "Keine offenen Positionen.")
    zeilen += [f"• {p['name']} {p['richtung']} {p['groesse']:g} @ {p['einstieg']:g} → {'+' if p['gv'] >= 0 else ''}{_zahl(p['gv'])} {w}"
               for p in pos[:15]]
    return "\n".join(zeilen) + "\nAlles Spielgeld (Demo)."


def suchen(begriff: str) -> list[dict]:
    d = S.anfrage("GET", "/markets", params={"searchTerm": begriff.strip()[:40]})
    return [{"epic": m.get("epic"), "name": m.get("instrumentName"), "typ": m.get("instrumentType"), "status": m.get("marketStatus"),
             "kurs": m.get("offer")} for m in d.get("markets", [])[:10]]


def kurse(epic: str, aufloesung: str = "HOUR", anzahl: int = 300) -> np.ndarray:
    d = S.anfrage("GET", f"/prices/{epic}", params={"resolution": aufloesung, "max": max(20, min(1000, int(anzahl)))})
    preise = d.get("prices", [])
    mitte = [((p["closePrice"].get("bid") or 0) + (p["closePrice"].get("ask") or 0)) / 2 for p in preise if p.get("closePrice")]
    if len(mitte) < 30:
        raise CfdFehler(f"Zu wenig Kursdaten für {epic} ({len(mitte)}).")
    return np.array(mitte, dtype=float)


def _markt(epic: str) -> dict:
    return S.anfrage("GET", f"/markets/{epic}")


# ---------------------------------------------------------------- Signale (rein rechnerisch, testbar)
def _sma(x: np.ndarray, n: int) -> np.ndarray:
    aus = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        aus[n - 1:] = (c[n:] - c[:-n]) / n
    return aus


def _rsi(x: np.ndarray, n: int = 14) -> np.ndarray:
    aus = np.full(len(x), np.nan)
    if len(x) <= n:
        return aus
    d = np.diff(x)
    auf, ab = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    m_auf, m_ab = auf[:n].mean(), ab[:n].mean()
    for i in range(n, len(x)):
        if i > n:
            m_auf = (m_auf * (n - 1) + auf[i - 1]) / n
            m_ab = (m_ab * (n - 1) + ab[i - 1]) / n
        aus[i] = 100.0 if m_ab == 0 else 100 - 100 / (1 + m_auf / m_ab)
    return aus


def signale(typ: str, x: np.ndarray, p: dict, richtung: str = "beide") -> np.ndarray:
    """Gewuenschte Position je Kerze: +1 long, -1 short, 0 flach (aus der vorherigen Position fortgeschrieben)."""
    n = len(x)
    ziel = np.zeros(n)
    if typ == "trend":
        k, l = _sma(x, int(p.get("kurz") or 20)), _sma(x, int(p.get("lang") or 50))
        ziel = np.where(np.isnan(l), 0, np.where(k > l, 1, -1))
    elif typ == "rsi":
        r, stand = _rsi(x), 0
        for i in range(n):
            if np.isnan(r[i]):
                continue
            if r[i] < float(p.get("unter") or 30):
                stand = 1
            elif r[i] > float(p.get("ueber") or 70):
                stand = -1
            elif (stand == 1 and r[i] > 50) or (stand == -1 and r[i] < 50):
                stand = 0
            ziel[i] = stand
    elif typ == "ausbruch":
        f, stand = int(p.get("fenster") or 20), 0
        for i in range(f, n):
            hoch, tief = x[i - f:i].max(), x[i - f:i].min()
            if x[i] > hoch:
                stand = 1
            elif x[i] < tief:
                stand = -1
            ziel[i] = stand
    else:
        raise CfdFehler(f"Unbekannte Art {typ} (trend, rsi, ausbruch).")
    if richtung == "long":
        ziel = np.where(ziel > 0, 1, 0)
    elif richtung == "short":
        ziel = np.where(ziel < 0, -1, 0)
    return ziel.astype(int)


def backtest(typ: str, x: np.ndarray, p: dict, richtung: str, sl_proz: float, tp_proz: float) -> dict:
    """Einfacher Test auf Schlusskursen: Wechsel bei Signal, Stop/Ziel auf Schlusskursbasis. Ergebnis in % je Einheit Kapital
    OHNE Hebel (Hebel vervielfacht Gewinn und Verlust gleichermassen)."""
    ziel = signale(typ, x, p, richtung)
    stand, einstieg, trades, ergebnisse = 0, 0.0, 0, []
    for i in range(1, len(x)):
        if stand:
            veraenderung = (x[i] - einstieg) / einstieg * 100 * stand
            if veraenderung <= -sl_proz or veraenderung >= tp_proz or ziel[i] != stand:
                ergebnisse.append(max(-sl_proz, min(tp_proz, veraenderung)))
                stand = 0
        if not stand and ziel[i] and ziel[i] != ziel[i - 1]:
            stand, einstieg, trades = int(ziel[i]), x[i], trades + 1
    gesamt = float(np.sum(ergebnisse)) if ergebnisse else 0.0
    return {"trades": trades, "gesamt_proz": gesamt, "trefferquote": (sum(e > 0 for e in ergebnisse) / len(ergebnisse) * 100) if ergebnisse else 0.0,
            "halten_proz": float((x[-1] - x[0]) / x[0] * 100), "kerzen": len(x)}


# ---------------------------------------------------------------- Strategien verwalten
def _laden() -> dict:
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"strategien": []}


def _speichern(d: dict) -> None:
    DATEI.parent.mkdir(exist_ok=True)
    tmp = DATEI.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DATEI)


def _params(typ: str, p: dict) -> dict:
    erlaubt = {"trend": ("kurz", "lang"), "rsi": ("unter", "ueber"), "ausbruch": ("fenster",)}[typ]
    return {k: float(p[k]) for k in erlaubt if p.get(k) not in (None, "")}


def testen(typ: str, epic: str, p: dict, richtung: str = "beide", aufloesung: str = "HOUR",
           sl_proz: float = 2.0, tp_proz: float = 4.0) -> str:
    typ, aufloesung = (typ or "").lower(), (aufloesung or "HOUR").upper()
    if typ not in TYPEN or aufloesung not in AUFLOESUNGEN:
        raise CfdFehler(f"Art: {', '.join(TYPEN)}; Zeitraster: {', '.join(AUFLOESUNGEN)}.")
    x = kurse(epic, aufloesung, 1000)
    e = backtest(typ, x, _params(typ, p), richtung, float(sl_proz), float(tp_proz))
    return (f"🧪 Backtest {typ} auf {epic} ({aufloesung}, {e['kerzen']} Kerzen, {richtung}, Stop {sl_proz:g} %, Ziel {tp_proz:g} %): "
            f"{e['trades']} Trades, Summe {e['gesamt_proz']:+.1f} % (ohne Hebel), Trefferquote {e['trefferquote']:.0f} %. "
            f"Kaufen+Halten: {e['halten_proz']:+.1f} %. Vergangenheit, keine Garantie; mit Hebel x10 wären es ~{e['gesamt_proz'] * 10:+.0f} % "
            "– in beide Richtungen.")


def anlegen(typ: str, epic: str, p: dict, groesse: float, richtung: str = "beide", aufloesung: str = "HOUR",
            sl_proz: float = 2.0, tp_proz: float = 4.0, titel: str = "") -> str:
    typ, aufloesung, richtung = (typ or "").lower(), (aufloesung or "HOUR").upper(), (richtung or "beide").lower()
    if typ not in TYPEN or aufloesung not in AUFLOESUNGEN or richtung not in ("beide", "long", "short"):
        raise CfdFehler(f"Art: {', '.join(TYPEN)}; Zeitraster: {', '.join(AUFLOESUNGEN)}; Richtung: beide/long/short.")
    if not 0 < float(groesse) <= 1e6 or not 0.1 <= float(sl_proz) <= 50 or not 0.1 <= float(tp_proz) <= 200:
        raise CfdFehler("Größe > 0, Stop 0,1–50 %, Ziel 0,1–200 %.")
    test = testen(typ, epic, p, richtung, aufloesung, sl_proz, tp_proz)
    with _sperre:
        d = _laden()
        s = {"id": secrets.token_hex(3), "titel": (titel or f"{typ} {epic}")[:60], "epic": epic, "typ": typ, "p": _params(typ, p),
             "groesse": float(groesse), "richtung": richtung, "aufloesung": aufloesung, "sl_proz": float(sl_proz),
             "tp_proz": float(tp_proz), "aktiv": True, "erstellt": dt.date.today().isoformat(), "deal_id": None, "stand": 0,
             "pause_bis": 0, "trades": 0, "protokoll": []}
        d["strategien"].append(s)
        _speichern(d)
    return f"{test}\n\n✅ CFD-Strategie „{s['titel']}“ (Nr. {s['id']}) ist an – Demo-Konto, Größe {groesse:g}, alle 5 Minuten geprüft."


def _finde(d: dict, nr: str) -> dict:
    for s in d["strategien"]:
        if s["id"] == str(nr).strip():
            return s
    raise CfdFehler(f"Keine CFD-Strategie mit Nr. {nr}.")


def liste() -> str:
    d = _laden()
    if not d["strategien"]:
        return "Noch keine CFD-Strategien. Beispiel: „Teste einen Trend auf Gold (Stundenkerzen)“."
    return "🎯 CFD-Strategien (Demo):\n" + "\n".join(
        f"• {s['id']} {'▶' if s['aktiv'] else '⏸'} {s['titel']} – {s['typ']} {s['epic']} {s['aufloesung']}, {s['richtung']}, "
        f"Größe {s['groesse']:g}, Stop {s['sl_proz']:g} %, Ziel {s['tp_proz']:g} %, {s['trades']} Trades"
        + (f", gerade {'LONG' if s['stand'] > 0 else 'SHORT'}" if s.get("stand") else "") for s in d["strategien"])


def _setze_aktiv(nr: str, an: bool) -> str:
    with _sperre:
        d = _laden()
        s = _finde(d, nr)
        s["aktiv"], s["pause_bis"] = an, 0
        _speichern(d)
    return f"CFD-Strategie {s['titel']} ist {'wieder an' if an else 'pausiert (offene Position bleibt, Stop/Ziel gelten weiter)'}."


def pausieren(nr: str) -> str:
    return _setze_aktiv(nr, False)


def fortsetzen(nr: str) -> str:
    return _setze_aktiv(nr, True)


def loeschen(nr: str) -> str:
    with _sperre:
        d = _laden()
        s = _finde(d, nr)
        d["strategien"].remove(s)
        _speichern(d)
    return f"CFD-Strategie {s['titel']} gelöscht" + (" – ihre offene Position läuft weiter (alles schließen: /cfd schliessen)." if s.get("deal_id") else ".")


def alle_stoppen() -> str:
    with _sperre:
        d = _laden()
        for s in d["strategien"]:
            s["aktiv"] = False
        _speichern(d)
    return "⏸ Alle CFD-Strategien angehalten. Offene Positionen bleiben (mit Stop/Ziel); alles schließen: /cfd schliessen."


def alles_schliessen() -> str:
    pos = positionen()
    fehler = 0
    for p in pos:
        try:
            S.anfrage("DELETE", f"/positions/{p['deal_id']}")
        except CfdFehler:
            fehler += 1
    with _sperre:
        d = _laden()
        for s in d["strategien"]:
            s["aktiv"], s["deal_id"], s["stand"] = False, None, 0
        _speichern(d)
    return f"🧹 {len(pos) - fehler} Demo-Position(en) geschlossen" + (f", {fehler} Fehler" if fehler else "") + ", alle Strategien angehalten."


# ---------------------------------------------------------------- Handeln (nur Demo)
def _oeffnen(s: dict, richtung: int, kurs: float) -> str:
    r = S.anfrage("POST", "/positions", json={
        "epic": s["epic"], "direction": "BUY" if richtung > 0 else "SELL", "size": s["groesse"], "guaranteedStop": False,
        "stopDistance": round(kurs * s["sl_proz"] / 100, 5), "profitDistance": round(kurs * s["tp_proz"] / 100, 5)})
    ref = r.get("dealReference", "")
    time.sleep(0.5)
    best = S.anfrage("GET", f"/confirms/{ref}") if ref else {}
    if best.get("dealStatus") not in (None, "ACCEPTED"):
        raise CfdFehler(f"Broker lehnt ab: {best.get('reason') or best.get('dealStatus')}")
    betroffen = best.get("affectedDeals") or []
    return (betroffen[0].get("dealId") if betroffen else None) or best.get("dealId") or ref


def _runde(s: dict, offene: dict, senden) -> None:
    if not s["aktiv"] or time.time() < s.get("pause_bis", 0):
        return
    if s.get("deal_id") and s["deal_id"] not in offene:   # vom Broker per Stop/Ziel geschlossen
        senden(f"🎯 CFD-Demo: {s['titel']} – Position wurde per Stop-Loss oder Gewinnziel geschlossen.")
        s["protokoll"].append(f"{dt.datetime.now():%d.%m. %H:%M} durch Stop/Ziel geschlossen")
        s["deal_id"], s["stand"] = None, 0
    markt = _markt(s["epic"]).get("snapshot", {})
    if markt.get("marketStatus", "TRADEABLE") != "TRADEABLE":
        return
    x = kurse(s["epic"], s["aufloesung"], 300)
    ziel = int(signale(s["typ"], x, s["p"], s["richtung"])[-1])
    vorher, s["letztes_signal"] = s.get("letztes_signal", 0), ziel
    if s.get("deal_id") and ziel != s["stand"]:   # Signal gedreht oder weg -> raus
        S.anfrage("DELETE", f"/positions/{s['deal_id']}")
        senden(f"↩️ CFD-Demo: {s['titel']} – {'LONG' if s['stand'] > 0 else 'SHORT'} geschlossen (Signal gedreht).")
        s["deal_id"], s["stand"] = None, 0
    # Einstieg nur bei einem NEUEN Signal - nach Stop/Ziel nicht sofort wieder in dieselbe Richtung (wie im Backtest)
    if ziel and not s.get("deal_id") and ziel != vorher:
        s["deal_id"] = _oeffnen(s, ziel, float(x[-1]))
        s["stand"], s["trades"] = ziel, s["trades"] + 1
        senden(f"📈 CFD-Demo: {s['titel']} – {'LONG' if ziel > 0 else 'SHORT'} {s['groesse']:g} {s['epic']} @ ~{x[-1]:g} "
               f"(Stop {s['sl_proz']:g} %, Ziel {s['tp_proz']:g} %). Spielgeld.")
        s["protokoll"].append(f"{dt.datetime.now():%d.%m. %H:%M} {'LONG' if ziel > 0 else 'SHORT'} @ {x[-1]:g}")
        s["protokoll"] = s["protokoll"][-50:]


def runde(senden) -> None:
    if not konfiguriert():
        return
    with _sperre:
        d = _laden()
        if not any(s["aktiv"] for s in d["strategien"]):
            return
        offene = {p["deal_id"] for p in positionen()}
        for s in d["strategien"]:
            try:
                _runde(s, offene, senden)
            except Exception as e:
                s["pause_bis"] = time.time() + FEHLER_PAUSE_S
                senden(f"⚠️ CFD-Demo: {s['titel']} – {str(e)[:160]}. Ich versuche es in einer Stunde wieder.")
        _speichern(d)


def starte(senden) -> None:
    def schleife() -> None:
        while True:
            try:
                runde(senden)
            except Exception as e:
                print(f"[CFD] {str(e)[:150]}", flush=True)
            time.sleep(TAKT_S)
    threading.Thread(target=schleife, daemon=True, name="klaus-cfd-demo").start()


# ---------------------------------------------------------------- Telegram
def schluessel_setzen(eingabe: str, speichern) -> str:
    """/cfd_schluessel <API-Key> <E-Mail> <Passwort> - wird vorher gegen die DEMO-Anmeldung geprueft."""
    teile = eingabe.split()
    if len(teile) != 4:
        return "So: /cfd_schluessel <API-Key> <E-Mail> <API-Passwort> (aus Capital.com → Einstellungen → API). Ich lösche die Nachricht sofort."
    key, login, passwort = teile[1], teile[2], teile[3]
    if not re.fullmatch(r"[A-Za-z0-9]{8,64}", key) or "@" not in login:
        return "Das sieht nicht richtig aus (API-Key, E-Mail, Passwort) – nichts gespeichert."
    try:
        S._anmelden(key, login, passwort)
    except (CfdFehler, requests.RequestException) as e:
        return f"Die Demo-Anmeldung klappt damit nicht ({str(e)[:100]}) – nichts gespeichert."
    speichern("CAPITAL_API_KEY", key)
    speichern("CAPITAL_LOGIN", login)
    speichern("CAPITAL_PASSWORT", passwort)
    S.kopf = {}
    return "🔑 Capital.com-Demo verbunden, deine Nachricht ist gelöscht.\n\n" + konto_text()


def befehl(eingabe: str) -> str:
    """/cfd [stop | schliessen | strategien]"""
    arg = eingabe.split(maxsplit=1)[1].strip().lower() if len(eingabe.split()) > 1 else ""
    try:
        if arg.startswith("stop"):
            return alle_stoppen()
        if arg.startswith(("schliess", "schließ")):
            return alles_schliessen()
        if arg.startswith("strateg"):
            return liste()
        return konto_text() + "\n\n" + liste()
    except (CfdFehler, requests.RequestException) as e:
        return f"CFD-Demo: {str(e)[:200]}"
