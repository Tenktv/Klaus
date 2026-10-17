"""
Klaus - Handel ueber Alpaca (US-Aktien, ETFs, Krypto). Laeuft auf dem Server, Schluessel nur in dessen .env.

    alpaca_handel.konto_text()                      Kontostand, Positionen, offene Orders (nur lesend, ohne Freigabe)
    auftrag = alpaca_handel.vorbereiten("kaufen", "Nvidia", stueck=2)   prueft alles und baut die Zusammenfassung
    alpaca_handel.ausfuehren(token, auftrag)        nur mit Freigabe-Token (Art "handeln": Telegram-Knopf + PIN)

Standard ist das PAPIER-Konto von Alpaca (Spielgeld). Echtgeld nur, wenn in der .env des Servers ALPACA_LIVE=1 steht
UND dort Live-Schluessel eingetragen sind - das kann Klaus nicht selbst umstellen.
Schutz: Papier-Konto ohne Freigabe; Echtgeld-Orders einzeln freigeben (Knopf + PIN), Kaufkraft-Pruefung, optional Hoechstbetrag je Order (ALPACA_MAX_ORDER_USD), kein Leerverkauf, nur Verkauf von
Stuecken, die im Depot liegen. Keine Anlageberatung.
"""
from __future__ import annotations

import math
import os
import re
import secrets
from dataclasses import dataclass

import requests

import freigabe

ART = "handeln"
TRADING = {False: "https://paper-api.alpaca.markets", True: "https://api.alpaca.markets"}
DATEN = "https://data.alpaca.markets"
KRYPTO = {"bitcoin": "BTC/USD", "btc": "BTC/USD", "ethereum": "ETH/USD", "eth": "ETH/USD", "solana": "SOL/USD",
          "sol": "SOL/USD", "dogecoin": "DOGE/USD", "doge": "DOGE/USD"}


class HandelFehler(Exception):
    """Verstaendliche Meldung fuer Nikola (geht so an Telegram)."""


def live() -> bool:
    return os.getenv("ALPACA_LIVE", "").strip() == "1"


def konfiguriert() -> bool:
    return bool(os.getenv("ALPACA_API_KEY", "").strip() and os.getenv("ALPACA_SECRET_KEY", "").strip())


def max_order_usd() -> float | None:
    """Hoechstbetrag je Kauf-Order in USD - None = keine Grenze (Standard; die Kaufkraft begrenzt trotzdem)."""
    try:
        wert = float(os.getenv("ALPACA_MAX_ORDER_USD", "").strip() or 0)
    except ValueError:
        return None
    return wert if wert > 0 else None


def modus() -> str:
    return "ECHTGELD" if live() else "Papier"


def _api(methode: str, pfad: str, basis: str | None = None, **kw):
    if not konfiguriert():
        raise HandelFehler("Alpaca ist nicht eingerichtet: ALPACA_API_KEY und ALPACA_SECRET_KEY fehlen in der .env des Servers.")
    kopf = {"APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY", "").strip(),
            "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET_KEY", "").strip()}
    try:
        r = requests.request(methode, (basis or TRADING[live()]) + pfad, headers=kopf, timeout=15, **kw)
    except requests.RequestException as e:
        raise HandelFehler(f"Alpaca ist nicht erreichbar ({type(e).__name__}).") from e
    if r.status_code in (401, 403):
        raise HandelFehler(f"Alpaca lehnt die Schlüssel ab ({modus()}-Konto) – passen Schlüssel und ALPACA_LIVE zusammen?")
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        try:
            text = r.json().get("message", r.text)
        except ValueError:
            text = r.text
        raise HandelFehler(f"Alpaca: {str(text)[:160]}")
    return r.json() if r.content else {}


def _zahl(x, stellen: int = 2) -> str:
    return f"{float(x):,.{stellen}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _ist_krypto(sym: str) -> bool:
    return "/" in sym


# ------------------------------------------------------------------ Symbole + Kurse
def symbol(name: str) -> str:
    """Name oder Kuerzel -> Alpaca-Symbol (NVDA, SPY, BTC/USD). Prueft, dass Alpaca es handeln kann."""
    n = name.strip()
    if not n:
        raise HandelFehler("Welcher Wert? Mir fehlt der Name oder das Kürzel.")
    if n.lower() in KRYPTO:
        sym = KRYPTO[n.lower()]
    elif re.fullmatch(r"[A-Z]{1,5}([./][A-Z]{1,4})?", n) or re.fullmatch(r"[A-Z]{2,6}/USDT?", n):
        sym = n
    else:
        import markt

        try:
            y = markt.symbol(n)
        except LookupError as e:
            raise HandelFehler(str(e)) from e
        if m := re.fullmatch(r"([A-Z]{2,6})-(USD|EUR)", y):
            sym = f"{m.group(1)}/USD"
        elif re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", y):
            sym = y.replace("-", ".")
        else:
            raise HandelFehler(f"„{name}“ ({y}) ist kein US-Wert – über Alpaca gehen nur US-Aktien, ETFs und Krypto.")
    asset = _api("GET", "/v2/assets/" + requests.utils.quote(sym.replace("/", ""), safe=""))
    if not asset or not asset.get("tradable"):
        raise HandelFehler(f"{sym} ist bei Alpaca nicht handelbar.")
    return asset["symbol"]


def kurs(sym: str) -> float:
    """Letzter Preis in USD."""
    if _ist_krypto(sym):
        d = _api("GET", "/v1beta3/crypto/us/latest/trades", basis=DATEN, params={"symbols": sym}) or {}
        preis = ((d.get("trades") or {}).get(sym) or {}).get("p")
    else:
        d = _api("GET", f"/v2/stocks/{sym}/trades/latest", basis=DATEN, params={"feed": "iex"}) or {}
        preis = (d.get("trade") or {}).get("p")
    if not preis:
        raise HandelFehler(f"Ich bekomme gerade keinen Kurs für {sym}.")
    return float(preis)


# ------------------------------------------------------------------ Lesen (ohne Freigabe)
def konto() -> dict:
    return _api("GET", "/v2/account") or {}


def positionen() -> list[dict]:
    return _api("GET", "/v2/positions") or []


def offene_orders() -> list[dict]:
    return _api("GET", "/v2/orders", params={"status": "open", "limit": 20}) or []


def konto_text() -> str:
    k = konto()
    wert, vortag = float(k.get("equity") or 0), float(k.get("last_equity") or 0)
    tag = wert - vortag
    zeilen = [f"📊 Alpaca ({modus()}-Konto): Wert {_zahl(wert)} $, Bargeld {_zahl(k.get('cash') or 0)} $, "
              f"Kaufkraft {_zahl(k.get('buying_power') or 0)} $, heute {'+' if tag >= 0 else '−'}{_zahl(abs(tag))} $."]
    if k.get("trading_blocked") or k.get("account_blocked"):
        zeilen.append("⚠️ Das Konto ist für Handel gesperrt.")
    pos = positionen()
    if pos:
        zeilen.append("Positionen:")
        for p in pos[:15]:
            gv = float(p.get("unrealized_pl") or 0)
            zeilen.append(f"• {p['symbol']}: {_zahl(p['qty'], 4).rstrip('0').rstrip(',')} Stück, Wert {_zahl(p.get('market_value') or 0)} $, "
                          f"{'+' if gv >= 0 else '−'}{_zahl(abs(gv))} $ ({float(p.get('unrealized_plpc') or 0) * 100:+.1f} %)")
    else:
        zeilen.append("Keine Positionen.")
    orders = offene_orders()
    if orders:
        zeilen.append("Offene Orders:")
        for o in orders[:10]:
            menge = f"{o['qty']} Stück" if o.get("qty") else f"{o.get('notional')} $"
            limit = f" Limit {o['limit_price']} $" if o.get("limit_price") else ""
            zeilen.append(f"• {o['side']} {o['symbol']} {menge}{limit} ({o['status']}, Nr. {o['id'][:8]})")
    if not live():
        zeilen.append("Alles Spielgeld.")
    return "\n".join(zeilen)


# ------------------------------------------------------------------ Orders (nur mit Freigabe)
@dataclass
class Auftrag:
    seite: str                 # buy | sell | cancel
    symbol: str = ""
    stueck: float | None = None
    betrag_usd: float | None = None
    limit: float | None = None
    order_id: str = ""
    schaetzung_usd: float = 0.0
    live: bool = False
    text: str = ""

    def daten(self) -> dict:
        d = {"symbol": self.symbol, "side": self.seite, "client_order_id": f"klaus-{secrets.token_hex(8)}",
             "type": "limit" if self.limit else "market", "time_in_force": "gtc" if _ist_krypto(self.symbol) else "day"}
        if self.stueck is not None:
            d["qty"] = f"{self.stueck:g}"
        else:
            d["notional"] = f"{self.betrag_usd:.2f}"
        if self.limit:
            d["limit_price"] = f"{self.limit:g}"
        return d


def vorbereiten(aktion: str, name: str = "", stueck: float | None = None, betrag_usd: float | None = None,
                limit: float | None = None, order_nr: str = "") -> Auftrag:
    """Prueft die Order gegen Konto, Depot und Grenzen. -> Auftrag mit Zusammenfassung (noch nichts gesendet)."""
    a = (aktion or "").strip().lower()
    if a.startswith(("storn", "abbrech", "cancel", "loesch", "lösch")):
        return _storno_vorbereiten(order_nr)
    seite = "buy" if a.startswith(("kauf", "buy")) else "sell" if a.startswith(("verkauf", "sell")) else ""
    if not seite:
        raise HandelFehler("Soll ich kaufen, verkaufen oder eine Order stornieren?")
    stueck = float(stueck) if stueck not in (None, "", 0) else None
    betrag_usd = float(betrag_usd) if betrag_usd not in (None, "", 0) else None
    limit = float(limit) if limit not in (None, "", 0) else None
    if (stueck is None) == (betrag_usd is None):
        raise HandelFehler("Sag mir entweder die Stückzahl oder einen Betrag in Dollar.")
    if (stueck is not None and stueck < 0) or (betrag_usd is not None and betrag_usd < 0) or (limit is not None and limit <= 0):
        raise HandelFehler("Stückzahl, Betrag und Limit müssen positiv sein.")
    sym = symbol(name)
    preis = limit or kurs(sym)
    if limit and betrag_usd is not None:   # Limit-Orders gehen nur mit Stueckzahl (Aktien: ganze Stuecke)
        stueck = round(betrag_usd / limit, 6) if _ist_krypto(sym) else float(math.floor(betrag_usd / limit))
        betrag_usd = None
        if stueck < 1 and not _ist_krypto(sym):
            raise HandelFehler(f"Für den Betrag bekomme ich bei {_zahl(limit)} $ Limit nicht mal ein ganzes Stück {sym}.")
    schaetzung = stueck * preis if stueck is not None else betrag_usd
    if seite == "buy" and max_order_usd() and schaetzung > max_order_usd():   # Verkaufen ist nie begrenzt
        raise HandelFehler(f"Die Order wäre etwa {_zahl(schaetzung)} $ groß – mehr als die Grenze von {_zahl(max_order_usd())} $ "
                           "je Order (ALPACA_MAX_ORDER_USD in der .env des Servers).")
    k = konto()
    if k.get("trading_blocked") or k.get("account_blocked"):
        raise HandelFehler("Das Alpaca-Konto ist für Handel gesperrt.")
    if seite == "buy" and schaetzung > float(k.get("buying_power") or 0):
        raise HandelFehler(f"Nicht genug Kaufkraft: etwa {_zahl(schaetzung)} $ nötig, da sind {_zahl(k.get('buying_power') or 0)} $.")
    if seite == "sell":   # nie leerverkaufen: nur was im Depot liegt
        pos = _api("GET", "/v2/positions/" + requests.utils.quote(sym.replace("/", ""), safe="")) or {}
        hab = float(pos.get("qty_available") or pos.get("qty") or 0)
        noetig = stueck if stueck is not None else betrag_usd / kurs(sym)
        if hab <= 0:
            raise HandelFehler(f"Du hast kein {sym} im Depot – Leerverkäufe mache ich nicht.")
        if noetig > hab * 1.0001:
            raise HandelFehler(f"Du hast nur {hab:g} Stück {sym} frei, nicht {noetig:g}.")
    auftrag = Auftrag(seite, sym, stueck, betrag_usd, limit, schaetzung_usd=schaetzung, live=live())
    menge = f"{stueck:g} Stück" if stueck is not None else f"für {_zahl(betrag_usd)} $"
    art = f"Limit {_zahl(limit)} $" if limit else f"Marktpreis (zuletzt {_zahl(preis)} $)"
    warnung = "‼️ ECHTGELD ‼️ " if auftrag.live else "Papier-Konto · "
    auftrag.text = f"{warnung}{'KAUFEN' if seite == 'buy' else 'VERKAUFEN'} {sym} {menge}, {art}, ca. {_zahl(schaetzung)} $"
    return auftrag


def _storno_vorbereiten(order_nr: str) -> Auftrag:
    nr = (order_nr or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f\-]{6,36}", nr):
        raise HandelFehler("Welche Order soll ich stornieren? Ich brauche die Nummer aus der Übersicht.")
    treffer = [o for o in offene_orders() if o["id"].startswith(nr)]
    if len(treffer) != 1:
        raise HandelFehler(f"Ich finde keine eindeutige offene Order mit der Nummer {nr}.")
    o = treffer[0]
    menge = f"{o['qty']} Stück" if o.get("qty") else f"{o.get('notional')} $"
    return Auftrag("cancel", o["symbol"], order_id=o["id"], live=live(),
                   text=f"{'‼️ ECHTGELD ‼️ ' if live() else 'Papier-Konto · '}Order stornieren: {o['side']} {o['symbol']} {menge}")


def ausfuehren(token: str | None, auftrag: Auftrag) -> str:
    """Sendet die Order - nur mit gueltigem Freigabe-Token und unveraendertem Modus (Papier/Echtgeld)."""
    freigabe.pruefe(token, ART)
    if auftrag.live != live():
        raise HandelFehler("Der Modus (Papier/Echtgeld) hat sich seit der Freigabe geändert – ich sende nichts.")
    return _senden(auftrag)


def papier_direkt(auftrag: Auftrag) -> str:
    """Papier-Konto: Order (oder Storno) sofort, ohne Freigabe. Bei Echtgeld verweigert - dort nur ausfuehren(token, ...)."""
    if live() or auftrag.live:
        raise HandelFehler("Echtgeld-Orders gehen nur mit Freigabe (Knopf + PIN).")
    return _senden(auftrag)


def _senden(auftrag: Auftrag) -> str:
    if auftrag.seite == "cancel":
        _api("DELETE", f"/v2/orders/{auftrag.order_id}")
        return f"Order für {auftrag.symbol} storniert ({modus()}-Konto)."
    o = _api("POST", "/v2/orders", json=auftrag.daten()) or {}
    menge = f"{o.get('qty')} Stück" if o.get("qty") else f"{o.get('notional')} $"
    return (f"✅ Order an Alpaca ({modus()}-Konto): {'Kauf' if auftrag.seite == 'buy' else 'Verkauf'} {auftrag.symbol} {menge}, "
            f"Status {o.get('status', '?')}, Nr. {str(o.get('id', ''))[:8]}.")


def order(order_id: str) -> dict | None:
    return _api("GET", f"/v2/orders/{order_id}")


def papier_automatisch(auftrag: Auftrag) -> dict:
    """Nur fuer Strategien (strategien.py): Order OHNE Freigabe - ausschliesslich auf dem Papier-Konto."""
    if live() or auftrag.live or auftrag.seite == "cancel":
        raise HandelFehler("Automatische Orders gibt es nur auf dem Papier-Konto.")
    return _api("POST", "/v2/orders", json=auftrag.daten()) or {}


# ------------------------------------------------------------------ Schluessel per Telegram (nur Papier)
def schluessel_setzen(eingabe: str, speichern) -> str:
    """/alpaca_schluessel <KEY> <SECRET> - nur Paper-Schluessel (PK...), vorher gegen Alpaca geprueft.
    speichern(name, wert) schreibt in die .env und os.environ. Echtgeld laesst sich so bewusst NICHT einschalten."""
    teile = eingabe.split()
    if len(teile) != 3:
        return "So: /alpaca_schluessel <API-Key> <Secret> (Paper-Schlüssel von app.alpaca.markets). Die Nachricht lösche ich sofort."
    key, secret = teile[1].strip(), teile[2].strip()
    if not re.fullmatch(r"PK[A-Z0-9]{8,40}", key) or not re.fullmatch(r"[A-Za-z0-9/+=]{20,80}", secret):
        return ("Das sehen nicht nach Paper-Schlüsseln aus (Key beginnt mit PK). Per Telegram nehme ich nur Paper-Schlüssel – "
                "Echtgeld richtest du bewusst direkt auf dem Server ein.")
    if live():
        return "Auf dem Server ist ALPACA_LIVE=1 gesetzt – Schlüssel ändere ich dann nicht per Telegram."
    try:
        r = requests.get(TRADING[False] + "/v2/account", timeout=15,
                         headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
    except requests.RequestException as e:
        return f"Alpaca ist gerade nicht erreichbar ({type(e).__name__}) – nichts gespeichert."
    if r.status_code != 200:
        return f"Alpaca lehnt die Schlüssel ab (HTTP {r.status_code}) – nichts gespeichert. Tippfehler?"
    speichern("ALPACA_API_KEY", key)
    speichern("ALPACA_SECRET_KEY", secret)
    return "🔑 Alpaca-Paper-Schlüssel gespeichert und geprüft. Deine Nachricht ist gelöscht.\n\n" + konto_text()
