"""Lead-Suche (Betriebe ohne eigene Website) direkt auf dem Server - braucht den PC nicht.

Nur OpenStreetMap + Websuche; das Ergebnis kommt per Telegram (Liste + CSV). Briefe erstellen/drucken/hochladen bleibt am PC."""
from __future__ import annotations

import csv
import io
import re
import threading


def parameter(args: dict) -> tuple[list[str], str, float]:
    liste = [x.strip() for x in re.split(r",|;|\bund\b", str(args.get("branchen") or "")) if x.strip()]
    ort = str(args.get("ort") or "").strip() or "Göppingen"
    try:
        radius = max(1.0, min(40.0, float(args.get("radius_km") or 12)))
    except (TypeError, ValueError):
        radius = 12.0
    return liste, ort, radius


def suchen(liste: list[str], ort: str, radius: float, senden, datei) -> None:
    """Blockierend; meldet alles ueber senden(text) und datei(bytes, name, text)."""
    try:
        import osm_leads
        gefunden = osm_leads.suche(liste, ort, radius)
        ohne = osm_leads.websites_pruefen(gefunden)
        neu = osm_leads.speichern(ohne)
        kopf = f"🔎 Lead-Suche {', '.join(liste)} · {ort} ({radius:g} km)"
        if not gefunden:
            return senden(f"{kopf}\nIch habe in dem Umkreis keine passenden Betriebe gefunden.")
        if not ohne:
            return senden(f"{kopf}\n{len(gefunden)} Betriebe gefunden, aber alle haben schon eine Website.")
        zeilen = [f"• {l['name']} – {l.get('adresse') or 'ohne Adresse'}" + (f" · {l['telefon']}" if l.get("telefon") else "") for l in ohne[:25]]
        senden(f"{kopf}\n{len(ohne)} Betriebe ohne eigene Website, {neu} davon neu:\n\n" + "\n".join(zeilen) + ("\n…" if len(ohne) > 25 else ""))
        puffer = io.StringIO()
        w = csv.DictWriter(puffer, fieldnames=osm_leads.SPALTEN, extrasaction="ignore")
        w.writeheader()
        w.writerows(ohne)
        datei(puffer.getvalue().encode("utf-8-sig"), f"leads_{re.sub(r'[^A-Za-z0-9_-]', '_', ort)}.csv", "Alle Treffer als Tabelle")
    except Exception as e:   # Overpass down, kein Internet ... -> ehrlich melden
        print(f"[Server] Lead-Suche: {type(e).__name__}: {e}", flush=True)
        senden(f"Die Lead-Suche hat nicht geklappt: {str(e)[:150]}")


def starten(args: dict, senden, datei) -> str:
    liste, ort, radius = parameter(args)
    if not liste:
        return "Welche Branchen soll ich suchen, zum Beispiel Schreiner, Maler oder Friseure?"
    threading.Thread(target=suchen, args=(liste, ort, radius, senden, datei), daemon=True, name="lead-suche").start()
    return (f"Ich suche {', '.join(liste)} rund um {ort} ({radius:g} km) direkt auf dem Server. Das dauert ein paar Minuten, "
            "die Liste kommt als Nachricht. Sag dem Nutzer genau das.")
