"""
Klaus - Markt-Analyse (nur lesend) + Papier-Depot mit Spielgeld. KEINE echten Orders, keine Anlageberatung.

    markt.symbol("Nvidia")        -> "NVDA" (Yahoo-Suche)
    markt.analyse("NVDA")         Kursverlauf 6 Monate, RSI(14), SMA20/50, MACD, Trend, Nachrichten-Stimmung
    markt.papier("kaufen", "NVDA", betrag_eur=1000)   Spielgeld-Depot (data/depot.json), Startkapital 10.000 EUR
    markt.depot()                 Stand des Papier-Depots in EUR

Echte Trades (Phase I, spaeter): nur ueber einen regulierten Broker und nur ueber das Freigabe-Gate.
Hinweis aus Nikolas Notizen: Gewinnversprechen von KI-Trading-Bots sind meist Hype - erst lange mit Spielgeld testen.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET

import numpy as np
import requests

import daten

DEPOT = daten.BASE_DIR / "data" / "depot.json"
START_KAPITAL = 10_000.0
MAX_ANTEIL = 0.25          # eine Papier-Order hoechstens 25 % des Depotwerts (Uebung fuer echte Limits)
HINWEIS = "Nur Analyse, keine Anlageberatung."


# ------------------------------------------------------------------ Kurse
def symbol(name: str) -> str:
    """Name oder Kuerzel -> Yahoo-Symbol (z. B. "Nvidia" -> NVDA, "Dax" -> ^GDAXI, "Bitcoin" -> BTC-EUR)."""
    n = name.strip()
    fest = {"dax": "^GDAXI", "nasdaq": "^IXIC", "s&p 500": "^GSPC", "s&p": "^GSPC", "bitcoin": "BTC-EUR", "ethereum": "ETH-EUR",
            "gold": "GC=F", "öl": "CL=F", "oel": "CL=F", "euro": "EURUSD=X"}
    if n.lower() in fest:
        return fest[n.lower()]
    if re.fullmatch(r"[\^A-Z0-9.=\-]{1,12}", n):
        return n
    r = requests.get("https://query1.finance.yahoo.com/v1/finance/search", params={"q": n, "quotesCount": 5, "newsCount": 0},
                     headers=daten.UA, timeout=10)
    treffer = [q for q in r.json().get("quotes", []) if q.get("symbol") and q.get("quoteType") in ("EQUITY", "ETF", "INDEX", "CRYPTOCURRENCY")]
    if not treffer:
        raise LookupError(f"Ich finde kein Börsenkürzel für „{name}“.")
    return treffer[0]["symbol"]


def _verlauf(sym: str, bereich: str = "1y") -> dict:
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}",
                     params={"range": bereich, "interval": "1d"}, headers=daten.UA, timeout=12)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    zeiten = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    schluss, hoch, tief, vol = q.get("close") or [], q.get("high") or [], q.get("low") or [], q.get("volume") or []
    zeilen = [(t, c, hoch[i] if i < len(hoch) else None, tief[i] if i < len(tief) else None, vol[i] if i < len(vol) else None)
              for i, (t, c) in enumerate(zip(zeiten, schluss)) if c is not None]
    return {"meta": res["meta"], "tage": [dt.datetime.fromtimestamp(z[0]).strftime("%Y-%m-%d") for z in zeilen],
            "kurse": [float(z[1]) for z in zeilen],
            "hoch": [float(z[2]) if z[2] is not None else float(z[1]) for z in zeilen],
            "tief": [float(z[3]) if z[3] is not None else float(z[1]) for z in zeilen],
            "volumen": [float(z[4]) if z[4] else 0.0 for z in zeilen]}


def kurs(sym: str) -> tuple[float, str]:
    m = _verlauf(sym, "5d")["meta"]
    return float(m.get("regularMarketPrice")), m.get("currency", "")


def _in_eur(betrag: float, waehrung: str) -> float:
    if waehrung in ("EUR", ""):
        return betrag
    kurs_eur = kurs(f"EUR{waehrung}=X")[0]  # z. B. EURUSD=X: 1 EUR = x USD
    return betrag / kurs_eur


# ------------------------------------------------------------------ Indikatoren
def _sma(x: np.ndarray, n: int) -> np.ndarray:
    aus = np.full(len(x), np.nan)
    if len(x) >= n:
        aus[n - 1:] = np.convolve(x, np.ones(n) / n, mode="valid")
    return aus


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    k, aus = 2 / (n + 1), np.empty(len(x))
    aus[0] = x[0]
    for i in range(1, len(x)):
        aus[i] = x[i] * k + aus[i - 1] * (1 - k)
    return aus


def _rsi(x: np.ndarray, n: int = 14) -> np.ndarray:
    d = np.diff(x)
    auf, ab = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    aus = np.full(len(x), np.nan)
    if len(d) < n:
        return aus
    ma, mb = auf[:n].mean(), ab[:n].mean()
    for i in range(n, len(d) + 1):
        if i > n:
            ma, mb = (ma * (n - 1) + auf[i - 1]) / n, (mb * (n - 1) + ab[i - 1]) / n
        aus[i] = 100 - 100 / (1 + ma / mb) if mb else 100.0
    return aus


def indikatoren(kurse: list[float]) -> dict:
    x = np.array(kurse, dtype=float)
    sma20, sma50, rsi = _sma(x, 20), _sma(x, 50), _rsi(x)
    macd = _ema(x, 12) - _ema(x, 26)
    signal = _ema(macd, 9)
    letzter = lambda a: None if np.isnan(a[-1]) else round(float(a[-1]), 2)
    r = letzter(rsi)
    trend = "seitwärts"
    if letzter(sma20) and letzter(sma50):
        trend = "aufwärts" if x[-1] > sma20[-1] > sma50[-1] else "abwärts" if x[-1] < sma20[-1] < sma50[-1] else "seitwärts"
    return {"rsi": r, "rsi_zone": "überkauft" if r and r > 70 else "überverkauft" if r and r < 30 else "neutral",
            "sma20": letzter(sma20), "sma50": letzter(sma50), "macd": round(float(macd[-1]), 3), "macd_signal": round(float(signal[-1]), 3),
            "macd_kreuz": "bullisch" if macd[-1] > signal[-1] and macd[-2] <= signal[-2] else
                          "bärisch" if macd[-1] < signal[-1] and macd[-2] >= signal[-2] else "",
            "trend": trend, "veraenderung_1m": round((x[-1] / x[-22] - 1) * 100, 2) if len(x) > 22 else None,
            "verlauf_sma20": [None if np.isnan(v) else round(float(v), 4) for v in sma20],
            "verlauf_sma50": [None if np.isnan(v) else round(float(v), 4) for v in sma50],
            "verlauf_rsi": [None if np.isnan(v) else round(float(v), 1) for v in rsi]}


# ------------------------------------------------------------------ Chart-Analyse
def _de(z: float, stellen: int = 2) -> str:
    """12345.6 -> 12.345,60 (Punkt nur als Tausendertrenner, Komma als Dezimalzeichen)."""
    return f"{z:,.{stellen}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _rollend_std(x: np.ndarray, n: int) -> np.ndarray:
    aus = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        aus[i] = x[i - n + 1:i + 1].std()
    return aus


def _niveaus(schluss: np.ndarray, hoch: np.ndarray, tief: np.ndarray, fenster: int = 5, tage: int = 150) -> list[dict]:
    """Unterstuetzungen/Widerstaende: Umkehrpunkte der letzten Monate, nahe beieinanderliegende zu einem Niveau zusammengefasst
    (mehr Beruehrungen = staerker)."""
    start = max(fenster, len(schluss) - tage)
    punkte = []
    for i in range(start, len(schluss) - fenster):
        if hoch[i] >= hoch[i - fenster:i + fenster + 1].max():
            punkte.append(float(hoch[i]))
        if tief[i] <= tief[i - fenster:i + fenster + 1].min():
            punkte.append(float(tief[i]))
    gruppen: list[list[float]] = []
    for pkt in sorted(punkte):
        if gruppen and pkt <= gruppen[-1][-1] * 1.015:
            gruppen[-1].append(pkt)
        else:
            gruppen.append([pkt])
    letzter = float(schluss[-1])
    return [{"preis": round(float(np.mean(g)), 4), "beruehrungen": len(g), "art": "widerstand" if np.mean(g) > letzter else "unterstuetzung"}
            for g in gruppen]


def chart_analyse(v: dict) -> dict:
    """Bollinger-Baender, Schwankung (ATR), Unterstuetzung/Widerstand, Volumen, Golden/Death Cross, 52-Wochen-Spanne."""
    x, h, t = (np.array(v[k], dtype=float) for k in ("kurse", "hoch", "tief"))
    vol = np.array(v.get("volumen") or [], dtype=float)
    n = len(x)
    out: dict = {}
    signale: list[str] = []
    if n >= 20:
        mitte, sd = _sma(x, 20), _rollend_std(x, 20)
        oben, unten = mitte + 2 * sd, mitte - 2 * sd
        spanne = oben[-1] - unten[-1]
        pos = float((x[-1] - unten[-1]) / spanne * 100) if spanne else 50.0
        breite = float(spanne / mitte[-1] * 100)
        out["bollinger"] = {"oben": round(float(oben[-1]), 4), "mitte": round(float(mitte[-1]), 4), "unten": round(float(unten[-1]), 4),
                            "position_proz": round(pos, 1), "breite_proz": round(breite, 1)}
        out["verlauf_bb_oben"] = [None if np.isnan(a) else round(float(a), 4) for a in oben]
        out["verlauf_bb_unten"] = [None if np.isnan(a) else round(float(a), 4) for a in unten]
        if pos >= 95:
            signale.append("Der Kurs liegt am oberen Bollinger-Band – kurzfristig überdehnt, Rücksetzer möglich.")
        elif pos <= 5:
            signale.append("Der Kurs liegt am unteren Bollinger-Band – kurzfristig überverkauft, Erholung möglich.")
        if len(x) >= 120:
            weit = [b for b in ((oben - unten) / mitte * 100)[-120:] if not np.isnan(b)]
            if weit and breite <= np.percentile(weit, 10):
                signale.append("Die Bollinger-Bänder sind ungewöhnlich eng (Squeeze) – oft folgt eine größere Bewegung, die Richtung ist offen.")
    if n >= 15:
        wahr = np.maximum(h[1:] - t[1:], np.maximum(abs(h[1:] - x[:-1]), abs(t[1:] - x[:-1])))
        atr = float(wahr[-14:].mean())
        out["atr_proz"] = round(atr / float(x[-1]) * 100, 2)
        signale.append(f"Typische Tagesschwankung: etwa {_de(out['atr_proz'])} Prozent (ATR 14).")
    niv = _niveaus(x, h, t)
    letzter = float(x[-1])
    stuetz = [a for a in niv if a["art"] == "unterstuetzung"]
    widerst = [a for a in niv if a["art"] == "widerstand"]
    u = max(stuetz, key=lambda a: a["preis"]) if stuetz else None
    w = min(widerst, key=lambda a: a["preis"]) if widerst else None
    out["unterstuetzung"], out["widerstand"] = u, w
    out["niveaus"] = (sorted(stuetz, key=lambda a: -a["preis"])[:2] + sorted(widerst, key=lambda a: a["preis"])[:2])
    dist = lambda a: abs(a["preis"] / letzter - 1) * 100
    if u:
        signale.append(f"Nächste Unterstützung bei {_de(u['preis'])} ({_de(dist(u), 1)} % entfernt, {u['beruehrungen']}x getestet).")
    if w:
        signale.append(f"Nächster Widerstand bei {_de(w['preis'])} ({_de(dist(w), 1)} % entfernt, {w['beruehrungen']}x getestet).")
    if len(vol) >= 50 and vol[-50:].mean() > 0:
        verh = float(vol[-10:].mean() / vol[-50:].mean())
        out["volumen_verhaeltnis"] = round(verh, 2)
        if verh >= 1.3:
            signale.append("Das Handelsvolumen ist zuletzt deutlich höher als üblich – die Bewegung hat Gewicht.")
        elif verh <= 0.7:
            signale.append("Das Handelsvolumen ist zuletzt dünn – Bewegungen sind weniger verlässlich.")
    if n >= 200:
        s50, s200 = _sma(x, 50), _sma(x, 200)
        diff = s50 - s200
        gueltig = np.where(~np.isnan(diff))[0]
        wechsel = [i for i in gueltig[1:] if diff[i] * diff[i - 1] < 0]
        if wechsel and n - 1 - wechsel[-1] <= 30:
            art = "Golden Cross (SMA 50 über SMA 200)" if diff[-1] > 0 else "Death Cross (SMA 50 unter SMA 200)"
            out["kreuz"] = art
            signale.append(f"Vor {n - 1 - wechsel[-1]} Handelstagen gab es ein {art}.")
        else:
            out["langfristtrend"] = "aufwärts" if diff[-1] > 0 else "abwärts"
    jahr = x[-252:]
    out["hoch52"], out["tief52"] = round(float(jahr.max()), 4), round(float(jahr.min()), 4)
    abstand = (letzter / float(jahr.max()) - 1) * 100
    out["abstand_hoch52_proz"] = round(abstand, 1)
    if abstand >= -2:
        signale.append("Der Kurs steht nahe am 52-Wochen-Hoch.")
    elif abstand <= -30:
        signale.append(f"Der Kurs liegt {abs(abstand):.0f} % unter dem 52-Wochen-Hoch.")
    out["signale"] = signale
    return out


# ------------------------------------------------------------------ Nachrichten-Stimmung
POSITIV = ("steigt", "rekord", "gewinn", "plus", "übertrifft", "kaufempfehlung", "hochgestuft", "wachstum", "durchbruch", "rally",
           "beats", "surge", "upgrade", "record", "growth")
NEGATIV = ("fällt", "verlust", "minus", "einbruch", "warnung", "klage", "herabgestuft", "kurssturz", "rückgang", "ermittlung",
           "misses", "plunge", "downgrade", "lawsuit", "probe", "cut")


def _schlagzeilen(name: str, anzahl: int = 8) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(name + ' Aktie')}&hl=de&gl=DE&ceid=DE:de"
    try:
        r = requests.get(url, headers=daten.UA, timeout=10)
        items = list(ET.fromstring(r.content).iter("item"))[:anzahl]
        return [{"titel": i.findtext("title", "").rsplit(" - ", 1)[0].strip(), "link": i.findtext("link", ""),
                 "alter": daten._alter(daten._zeit(i.findtext("pubDate")))} for i in items]
    except Exception as e:
        print(f"[Markt] Nachrichten {name}: {str(e)[:60]}")
        return []


def _yahoo_news(sym: str, anzahl: int = 8) -> list[dict]:
    try:
        r = requests.get("https://feeds.finance.yahoo.com/rss/2.0/headline", params={"s": sym, "region": "US", "lang": "en-US"},
                         headers=daten.UA, timeout=10)
        return [{"titel": i.findtext("title", "").strip(), "link": i.findtext("link", ""),
                 "alter": daten._alter(daten._zeit(i.findtext("pubDate"))), "quelle": "Yahoo Finance",
                 "_zeit": daten._zeit(i.findtext("pubDate"))} for i in list(ET.fromstring(r.content).iter("item"))[:anzahl]]
    except Exception as e:
        print(f"[Markt] Yahoo-News {sym}: {str(e)[:60]}")
        return []


def _newsapi(name: str, anzahl: int = 8) -> list[dict]:
    """Optional: NewsAPI.org (NEWSAPI_KEY in der .env). Ohne Schluessel nichts."""
    import os

    key = os.getenv("NEWSAPI_KEY", "").strip()
    if not key:
        return []
    try:
        r = requests.get("https://newsapi.org/v2/everything", params={"q": f'"{name}"', "sortBy": "publishedAt", "pageSize": anzahl,
                                                                      "language": "de"}, headers={"X-Api-Key": key}, timeout=10)
        return [{"titel": a["title"].rsplit(" - ", 1)[0].strip(), "link": a["url"], "quelle": (a.get("source") or {}).get("name", "NewsAPI"),
                 "alter": daten._alter(daten._zeit(a.get("publishedAt"))), "_zeit": daten._zeit(a.get("publishedAt"))}
                for a in r.json().get("articles", []) if a.get("title") and a["title"] != "[Removed]"]
    except Exception as e:
        print(f"[Markt] NewsAPI {name}: {str(e)[:60]}")
        return []


def nachrichten(name: str, sym: str, anzahl: int = 8) -> list[dict]:
    """Google News + Yahoo Finance (+ NewsAPI, wenn Schluessel da), ohne Doppelte, neueste zuerst."""
    gesehen, aus = set(), []
    google = _schlagzeilen(name, anzahl)
    for m in google:
        m.setdefault("quelle", "Google News")
    quellen = [google, _yahoo_news(sym, anzahl), _newsapi(name, anzahl)]   # jede Quelle ist schon nach Aktualitaet/Relevanz sortiert
    for i in range(anzahl):   # abwechselnd je Quelle, damit keine alle anderen verdraengt
        for liste in quellen:
            if i < len(liste):
                m = liste[i]
                schluessel = re.sub(r"\W+", "", m["titel"].lower())[:50]
                if schluessel and schluessel not in gesehen:
                    gesehen.add(schluessel)
                    m.pop("_zeit", None)
                    aus.append(m)
    return aus[:anzahl]


def stimmung(name: str, meldungen: list[dict]) -> dict:
    """-1 (negativ) .. +1 (positiv). Erst Gemini (kostenloses Textmodell), sonst Wortliste."""
    if not meldungen:
        return {"wert": 0.0, "text": "keine aktuellen Meldungen", "quelle": "-"}
    titel = "\n".join(f"- {m['titel']}" for m in meldungen)
    try:
        import recherche

        antwort = recherche.gemini(f"Schlagzeilen zu {name}:\n{titel}\n\nWie ist die Nachrichtenlage fuer die Aktie? Antworte NUR "
                                   'als JSON: {"wert": Zahl von -1 bis 1, "text": "ein kurzer deutscher Satz"}. Keine Kursprognose.',
                                   "Du bewertest Nachrichten nuechtern. Nur JSON.")
        d = json.loads(re.search(r"\{.*\}", antwort, re.S).group(0))
        return {"wert": max(-1.0, min(1.0, float(d.get("wert", 0)))), "text": str(d.get("text", ""))[:160], "quelle": "Gemini"}
    except Exception:
        t = titel.lower()
        p, n = sum(t.count(w) for w in POSITIV), sum(t.count(w) for w in NEGATIV)
        wert = 0.0 if p + n == 0 else (p - n) / (p + n)
        return {"wert": round(wert, 2), "text": f"{p} positive, {n} negative Signalwörter", "quelle": "Wortliste"}


def analyse(name_oder_symbol: str) -> dict:
    sym = symbol(name_oder_symbol)
    v = _verlauf(sym)
    if len(v["kurse"]) < 30:
        raise ValueError(f"Zu wenig Kursdaten für {sym}.")
    m = v["meta"]
    name = " ".join((m.get("shortName") or m.get("longName") or daten.AKTIEN_NAMEN.get(sym, sym)).split())
    ind = indikatoren(v["kurse"])
    chart = chart_analyse(v)
    meldungen = nachrichten(daten.SPRECH_NAMEN.get(sym, name), sym)
    st = stimmung(name, meldungen)
    preis, vortag = float(m.get("regularMarketPrice") or v["kurse"][-1]), float(m.get("chartPreviousClose") or v["kurse"][-2])
    tag_proz = round((preis / v["kurse"][-2] - 1) * 100, 2) if v["kurse"][-2] else 0.0
    K = 130   # das Panel zeichnet ~6 Monate, gerechnet wird mit dem vollen Jahr
    kuerze = lambda liste: liste[-K:] if isinstance(liste, list) else liste
    d = {"symbol": sym, "name": name, "preis": round(preis, 4), "waehrung": m.get("currency", ""), "tag": tag_proz,
         "tage": v["tage"][-K:], "kurse": [round(k, 4) for k in v["kurse"][-K:]],
         **{k: (kuerze(val) if k.startswith("verlauf_") else val) for k, val in {**ind, **chart}.items()},
         "stimmung": st, "meldungen": meldungen, "hinweis": HINWEIS}
    d["text"] = analyse_text(d)
    return d


def analyse_text(d: dict) -> str:
    komma = lambda z: f"{z:.2f}".replace(".", ",")
    teile = [f"{daten.SPRECH_NAMEN.get(d['symbol'], d['name'])} steht bei {komma(d['preis'])} {d['waehrung']}, heute "
             f"{'plus' if d['tag'] >= 0 else 'minus'} {komma(abs(d['tag']))} Prozent."]
    teile.append(f"Trend {d['trend']}" + (f", ein Monat {'plus' if d['veraenderung_1m'] >= 0 else 'minus'} "
                                          f"{komma(abs(d['veraenderung_1m']))} Prozent" if d.get("veraenderung_1m") is not None else "") + ".")
    if d.get("rsi"):
        teile.append(f"RSI {round(d['rsi'])}, also {d['rsi_zone']}.")
    if d.get("macd_kreuz"):
        teile.append(f"Der MACD hat gerade ein {d['macd_kreuz']}es Kreuz gebildet.")
    if d.get("signale"):   # Chart-Analyse: die zwei wichtigsten Punkte genuegen fuers Vorlesen (alles steht im Fenster)
        teile.append("Chart: " + " ".join(d["signale"][:3]))
    s = d["stimmung"]
    teile.append(f"Nachrichtenlage {'positiv' if s['wert'] > 0.25 else 'negativ' if s['wert'] < -0.25 else 'gemischt'}: {s['text']}")
    teile.append(HINWEIS)
    return " ".join(t.strip() for t in teile if t)


# ------------------------------------------------------------------ Papier-Depot (Spielgeld)
def _depot_laden() -> dict:
    try:
        return json.loads(DEPOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"start": START_KAPITAL, "bargeld": START_KAPITAL, "positionen": {}, "historie": [],
                "angelegt": dt.datetime.now().strftime("%d.%m.%Y")}


def _depot_speichern(d: dict) -> None:
    DEPOT.parent.mkdir(parents=True, exist_ok=True)
    DEPOT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def depot() -> dict:
    d = _depot_laden()
    positionen, wert = [], d["bargeld"]
    for sym, p in d["positionen"].items():
        try:
            preis, waehrung = kurs(sym)
            jetzt_eur = _in_eur(preis, waehrung) * p["stueck"]
        except Exception:
            jetzt_eur = p["einstand_eur"]
        wert += jetzt_eur
        positionen.append({"symbol": sym, "stueck": round(p["stueck"], 4), "einstand_eur": round(p["einstand_eur"], 2),
                           "wert_eur": round(jetzt_eur, 2), "gv_proz": round((jetzt_eur / p["einstand_eur"] - 1) * 100, 2)})
    return {"bargeld": round(d["bargeld"], 2), "wert": round(wert, 2), "start": d["start"],
            "gv_proz": round((wert / d["start"] - 1) * 100, 2), "positionen": positionen, "historie": d["historie"][-10:],
            "angelegt": d.get("angelegt", ""), "hinweis": "Spielgeld - keine echten Orders."}


def papier(aktion: str, name_oder_symbol: str, betrag_eur: float | None = None, stueck: float | None = None) -> str:
    """Kauf/Verkauf im Papier-Depot zum aktuellen Kurs. Limit: hoechstens 25 % des Depotwerts je Order."""
    sym = symbol(name_oder_symbol)
    preis, waehrung = kurs(sym)
    preis_eur = _in_eur(preis, waehrung)
    d = _depot_laden()
    wert = depot()["wert"]
    if aktion == "kaufen":
        betrag = betrag_eur if betrag_eur else (stueck or 0) * preis_eur
        if betrag <= 0:
            return "Wie viel soll ich kaufen? Nenn einen Betrag in Euro oder eine Stückzahl."
        if betrag > MAX_ANTEIL * wert:
            return f"Abgelehnt: höchstens {int(MAX_ANTEIL * 100)} Prozent des Depots pro Order, also {MAX_ANTEIL * wert:.0f} Euro."
        if betrag > d["bargeld"]:
            return f"Nicht genug Spielgeld: {d['bargeld']:.0f} Euro frei."
        n = betrag / preis_eur
        p = d["positionen"].setdefault(sym, {"stueck": 0.0, "einstand_eur": 0.0})
        p["stueck"] += n
        p["einstand_eur"] += betrag
        d["bargeld"] -= betrag
    elif aktion == "verkaufen":
        p = d["positionen"].get(sym)
        if not p:
            return f"{sym} ist nicht im Papier-Depot."
        n = min(p["stueck"], stueck or (betrag_eur / preis_eur if betrag_eur else p["stueck"]))
        anteil = n / p["stueck"]
        betrag = n * preis_eur
        d["bargeld"] += betrag
        p["einstand_eur"] *= (1 - anteil)
        p["stueck"] -= n
        if p["stueck"] < 1e-9:
            del d["positionen"][sym]
    else:
        return "Aktion muss kaufen oder verkaufen sein."
    d["historie"].append({"zeit": dt.datetime.now().strftime("%d.%m. %H:%M"), "aktion": aktion, "symbol": sym,
                          "stueck": round(n, 4), "kurs_eur": round(preis_eur, 2), "betrag_eur": round(betrag, 2)})
    _depot_speichern(d)
    return f"Papier-Depot: {round(n, 4)} {sym} {'gekauft' if aktion == 'kaufen' else 'verkauft'} für {betrag:.0f} Euro (Spielgeld)."


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    a = analyse(" ".join(sys.argv[1:]) or "Nvidia")
    print(a["symbol"], a["name"], a["preis"], a["waehrung"], "| RSI", a["rsi"], a["rsi_zone"], "| Trend", a["trend"],
          "| MACD-Kreuz", a["macd_kreuz"] or "-", "| Tage", len(a["tage"]))
    print("Stimmung:", a["stimmung"])
    print(a["text"])
