"""
Klaus - Analysen rund ums Alpaca-Depot (laeuft auf dem Server, nur lesend, keine Orders).

    analysen.depot_analyse()        Verteilung, Klumpenrisiko, Gewinner/Verlierer, Verlauf 1 Monat gegen den S&P 500
    analysen.scanner("alle")        sucht Signale in US-Standardwerten + Watchlist (ueberverkauft, Trendwechsel, 52-Wochen-Hoch ...)
    analysen.wochenbericht()        Woche: Depot gegen S&P 500, Strategien (Trades, Gewinn/Verlust), Signale
    analysen.starte(senden)         Wochenbericht automatisch freitags nach US-Boersenschluss (ab 22:30 Uhr)

Kurse fuer Scanner/Vergleich von Yahoo (wie markt.py), Konto von Alpaca. Nur Information, keine Anlageberatung.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

import alpaca_handel as alpaca

BASE_DIR = Path(__file__).resolve().parent.parent
DATEI = BASE_DIR / "data" / "analysen.json"
HINWEIS = "Nur Information, keine Anlageberatung."
KLUMPEN = 0.25          # ab diesem Anteil am Depot gilt eine Position als Klumpenrisiko
# Bekannte, liquide US-Werte (Alpaca-handelbar) + Krypto; dazu kommt die Watchlist
UNIVERSUM = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX",
             "ORCL", "CRM", "ADBE", "INTC", "QCOM", "PLTR", "UBER", "SHOP", "COIN", "JPM", "BAC", "GS", "V", "MA", "BRK-B",
             "JNJ", "LLY", "UNH", "PFE", "XOM", "CVX", "KO", "PEP", "WMT", "COST", "MCD", "NKE", "DIS", "BA", "CAT", "GLD",
             "BTC-USD", "ETH-USD", "SOL-USD"]
SIGNAL_NAMEN = {"ueberverkauft": "📉 Überverkauft (RSI unter 30)", "ueberkauft": "📈 Überkauft (RSI über 70)",
                "trend_auf": "🟢 Frischer Aufwärtstrend (SMA20 kreuzt SMA50 nach oben)",
                "trend_ab": "🔴 Abwärtstrend beginnt (SMA20 kreuzt SMA50 nach unten)",
                "hoch": "🚀 Neues 52-Wochen-Hoch", "tief": "⚠️ Neues 52-Wochen-Tief"}
_sperre = threading.Lock()


def _de(z: float, stellen: int = 1) -> str:
    return f"{z:,.{stellen}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _vz(z: float, stellen: int = 1) -> str:
    return ("+" if z >= 0 else "−") + _de(abs(z), stellen)


# ------------------------------------------------------------------ Vergleich mit dem Markt
def markt_veraenderung(bereich: str = "1mo", sym: str = "SPY") -> float | None:
    """Veraenderung in % ueber den Bereich (Yahoo: 5d, 1mo, 3mo ...)."""
    import markt

    try:
        k = markt._verlauf(sym, bereich)["kurse"]
        return (k[-1] / k[0] - 1) * 100 if len(k) > 1 else None
    except Exception:
        return None


def depot_verlauf(periode: str = "1M") -> dict | None:
    """Alpaca-Depotwert ueber die Periode (1W, 1M, 3M ...): Anfang, Ende, Veraenderung, groesster Rueckgang."""
    h = alpaca._api("GET", "/v2/account/portfolio/history", params={"period": periode, "timeframe": "1D"}) or {}
    werte = [float(x) for x in (h.get("equity") or []) if x]
    if len(werte) < 2:
        return None
    w = np.array(werte)
    spitze = np.maximum.accumulate(w)
    return {"anfang": w[0], "ende": w[-1], "proz": (w[-1] / w[0] - 1) * 100, "max_rueckgang": float(((w - spitze) / spitze).min() * 100)}


# ------------------------------------------------------------------ Depot-Analyse
def depot_kennzahlen(konto: dict, positionen: list[dict]) -> dict:
    wert = float(konto.get("equity") or 0)
    pos = []
    for p in positionen:
        mv = float(p.get("market_value") or 0)
        pos.append({"symbol": p["symbol"], "wert": mv, "anteil": mv / wert if wert else 0.0,
                    "gv": float(p.get("unrealized_pl") or 0), "gv_proz": float(p.get("unrealized_plpc") or 0) * 100,
                    "heute": float(p.get("unrealized_intraday_pl") or 0), "krypto": p.get("asset_class") == "crypto"})
    pos.sort(key=lambda x: -x["wert"])
    investiert = sum(p["wert"] for p in pos)
    gewichte = np.array([p["wert"] / investiert for p in pos]) if investiert else np.array([])
    return {"wert": wert, "bar": float(konto.get("cash") or 0), "positionen": pos, "investiert": investiert,
            "bar_anteil": (1 - investiert / wert) if wert else 1.0,
            "krypto_anteil": sum(p["wert"] for p in pos if p["krypto"]) / wert if wert else 0.0,
            "effektiv": float(1 / (gewichte ** 2).sum()) if len(gewichte) else 0.0,
            "klumpen": [p for p in pos if p["anteil"] >= KLUMPEN]}


def depot_analyse() -> str:
    try:
        k = depot_kennzahlen(alpaca.konto(), alpaca.positionen())
    except alpaca.HandelFehler as e:
        return str(e)
    z = [f"🔍 Depot-Analyse ({alpaca.modus()}-Konto): Wert {_de(k['wert'], 0)} $, davon {_de(k['bar_anteil'] * 100, 0)} % Bargeld."]
    if not k["positionen"]:
        z.append("Noch keine Positionen – nichts zu analysieren. Der Markt-Scanner (/scanner) zeigt, wo sich gerade etwas tut.")
        return "\n".join(z)
    z.append("Verteilung: " + ", ".join(f"{p['symbol']} {_de(p['anteil'] * 100, 0)} %" for p in k["positionen"][:8])
             + (" …" if len(k["positionen"]) > 8 else ""))
    n = len(k["positionen"])
    z.append(f"Streuung: {n} Position{'en' if n != 1 else ''}, wirkt wie {_de(k['effektiv'], 1)} gleich große"
             + (" – gut verteilt." if k["effektiv"] >= 5 else " – eher wenig gestreut."))
    for p in k["klumpen"]:
        z.append(f"⚠️ Klumpenrisiko: {p['symbol']} ist {_de(p['anteil'] * 100, 0)} % des Depots.")
    if k["krypto_anteil"] >= 0.2:
        z.append(f"⚠️ Krypto-Anteil {_de(k['krypto_anteil'] * 100, 0)} % – schwankt stark.")
    bester, schlechtester = max(k["positionen"], key=lambda p: p["gv_proz"]), min(k["positionen"], key=lambda p: p["gv_proz"])
    z.append(f"Bester: {bester['symbol']} {_vz(bester['gv_proz'])} % ({_vz(bester['gv'], 0)} $) · "
             f"Schwächster: {schlechtester['symbol']} {_vz(schlechtester['gv_proz'])} % ({_vz(schlechtester['gv'], 0)} $)")
    heute = sum(p["heute"] for p in k["positionen"])
    zieht = min(k["positionen"], key=lambda p: p["heute"])
    z.append(f"Heute: {_vz(heute, 0)} $" + (f", am meisten zieht {zieht['symbol']} runter ({_vz(zieht['heute'], 0)} $)." if zieht["heute"] < 0 else "."))
    try:
        v = depot_verlauf("1M")
    except alpaca.HandelFehler:
        v = None
    spy = markt_veraenderung("1mo")
    if v:
        z.append(f"Letzter Monat: Depot {_vz(v['proz'])} %" + (f", S&P 500 {_vz(spy)} %" if spy is not None else "")
                 + f", größter Rückgang {_de(v['max_rueckgang'])} %.")
    z.append(HINWEIS)
    return "\n".join(z)


# ------------------------------------------------------------------ Markt-Scanner
def signale(kurse: list[float]) -> dict:
    """Signale aus Tagesschlusskursen (letzter Wert = aktueller Kurs)."""
    import markt

    x = np.array(kurse, dtype=float)
    rsi = markt._rsi(x)[-1]
    s20, s50 = markt._sma(x, 20), markt._sma(x, 50)
    d = {"rsi": None if np.isnan(rsi) else float(rsi), "woche": (x[-1] / x[-6] - 1) * 100 if len(x) > 6 else 0.0, "treffer": []}
    if d["rsi"] is not None:
        if d["rsi"] < 30:
            d["treffer"].append("ueberverkauft")
        elif d["rsi"] > 70:
            d["treffer"].append("ueberkauft")
    if len(x) > 55 and not np.isnan(s50[-6]):
        ueber = s20 > s50
        if ueber[-1] and not ueber[-6]:
            d["treffer"].append("trend_auf")
        elif not ueber[-1] and ueber[-6]:
            d["treffer"].append("trend_ab")
    if len(x) > 200:
        vorher = x[-253:-1] if len(x) > 253 else x[:-1]
        if x[-1] >= vorher.max():
            d["treffer"].append("hoch")
        elif x[-1] <= vorher.min():
            d["treffer"].append("tief")
    return d


def _universum() -> list[str]:
    try:
        import watchlist

        eigene = list(watchlist.laden()["werte"])
    except Exception:
        eigene = []
    return list(dict.fromkeys(UNIVERSUM + [s for s in eigene if not s.startswith("^") and "=" not in s]))


def scan(symbole: list[str] | None = None) -> dict[str, dict]:
    import markt

    def eins(sym: str):
        try:
            return sym, signale(markt._verlauf(sym, "2y")["kurse"])
        except Exception as e:
            print(f"[Scanner] {sym}: {str(e)[:60]}", flush=True)
            return sym, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        return {s: d for s, d in pool.map(eins, symbole or _universum()) if d}


def scanner_text(ergebnis: dict[str, dict], art: str = "alle", je: int = 6) -> str:
    arten = list(SIGNAL_NAMEN) if art in ("", "alle") else [a for a in SIGNAL_NAMEN if a.startswith(art[:5])]
    if not arten:
        return "Scanner-Arten: alle, ueberverkauft, ueberkauft, trend_auf, trend_ab, hoch, tief."
    z = [f"🛰 Markt-Scanner ({len(ergebnis)} Werte geprüft):"]
    for a in arten:
        treffer = [(s, d) for s, d in ergebnis.items() if a in d["treffer"]]
        if not treffer:
            continue
        treffer.sort(key=lambda t: (t[1]["rsi"] or 50) * (1 if a == "ueberverkauft" else -1))
        z.append(SIGNAL_NAMEN[a] + ":")
        z += [f"• {s.replace('-USD', '')}: RSI {_de(d['rsi'] or 0, 0)}, Woche {_vz(d['woche'])} %" for s, d in treffer[:je]]
    if len(z) == 1:
        z.append("Gerade keine auffälligen Signale.")
    z.append("Signale sind keine Kaufempfehlung. Gefällt dir einer, kann ich ihn analysieren oder eine Strategie dafür testen.")
    return "\n".join(z)


def scanner(art: str = "alle") -> str:
    try:
        return scanner_text(scan(), (art or "alle").lower())
    except Exception as e:
        return f"Der Scanner ging nicht: {str(e)[:120]}"


# ------------------------------------------------------------------ Wochenbericht
def wochenbericht() -> str:
    import strategien

    heute = dt.date.today()
    seit = (heute - dt.timedelta(days=7)).isoformat()
    z = [f"🗓 Wochenbericht bis {heute:%d.%m.%Y}"]
    try:
        v = depot_verlauf("1W")
        spy = markt_veraenderung("5d")
        if v:
            z.append(f"Depot ({alpaca.modus()}): {_de(v['ende'], 0)} $, Woche {_vz(v['proz'])} % ({_vz(v['ende'] - v['anfang'], 0)} $)"
                     + (f" · S&P 500 {_vz(spy)} %" if spy is not None else "")
                     + ("  ✅ besser als der Markt" if spy is not None and v["proz"] > spy else "  · Markt war besser" if spy is not None else ""))
    except alpaca.HandelFehler as e:
        z.append(str(e))
    liste = strategien.laden()["strategien"]
    if liste:
        z.append("Strategien:")
        for s in liste:
            woche = [h for h in s.get("historie", []) if h["datum"] >= seit]
            realisiert = sum(h["gewinn"] for h in woche)
            offen = ""
            if s["stueck"]:
                try:
                    offen = f", offen {_vz((alpaca.kurs(s['symbol']) - s['einstand']) * s['stueck'], 0)} $"
                except alpaca.HandelFehler:
                    pass
            z.append(f"{'▶️' if s['aktiv'] else '⏸'} {s['titel']}: {len(woche)} Trade{'s' if len(woche) != 1 else ''}, "
                     f"realisiert {_vz(realisiert, 0)} $ (gesamt {_vz(s.get('realisiert', 0.0), 0)} $){offen}")
    else:
        z.append("Keine Strategien aktiv.")
    try:
        erg = scan()
        for art in ("ueberverkauft", "trend_auf", "hoch"):
            t = [s.replace("-USD", "") for s, d in erg.items() if art in d["treffer"]][:4]
            if t:
                z.append(f"{SIGNAL_NAMEN[art].split(' (')[0]}: {', '.join(t)}")
    except Exception:
        pass
    z.append(HINWEIS)
    return "\n".join(z)


def _zustand() -> dict:
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def faellig(jetzt: dt.datetime, zuletzt: str) -> bool:
    """Freitag ab 22:30 (nach US-Boersenschluss), einmal je Kalenderwoche."""
    woche = f"{jetzt.isocalendar()[0]}-{jetzt.isocalendar()[1]}"
    return jetzt.weekday() == 4 and (jetzt.hour, jetzt.minute) >= (22, 30) and zuletzt != woche


def schleife(senden) -> None:
    time.sleep(120)
    while True:
        try:
            jetzt = dt.datetime.now()
            z = _zustand()
            if alpaca.konfiguriert() and faellig(jetzt, z.get("wochenbericht", "")):
                senden(wochenbericht())
                z["wochenbericht"] = f"{jetzt.isocalendar()[0]}-{jetzt.isocalendar()[1]}"
                DATEI.parent.mkdir(exist_ok=True)
                DATEI.write_text(json.dumps(z), encoding="utf-8")
        except Exception as e:
            print(f"[Analysen] {e}", flush=True)
        time.sleep(600)


def starte(senden) -> None:
    threading.Thread(target=schleife, args=(senden,), daemon=True, name="klaus-analysen").start()
