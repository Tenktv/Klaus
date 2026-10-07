"""
Klaus - meldet per Telegram, dass der PC wieder da ist (wird von der Windows-Aufgabe "Klaus-Aufwecken" beim Wecken gestartet).

    pythonw src\aufgewacht.py            normale Meldung
    pythonw src\aufgewacht.py --test     Meldung mit "TEST" (zum Ausprobieren)

Sendet direkt an Telegram (nicht ueber den Tunnel, der erst nach dem Aufwachen wieder aufgebaut wird), wartet bis das Netzwerk da ist
und sagt dazu, ob Klaus' Tunnel zum Server schon wieder steht. Schreibt ausserdem data/aufgewacht.log.
"""
import datetime as dt
import socket
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values

BASIS = Path(__file__).resolve().parent.parent
LOG = BASIS / "data" / "aufgewacht.log"


def tunnel_steht() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 7702), timeout=2).close()   # lokaler Tunnel-Eingang zum Server
        return True
    except OSError:
        return False


def senden(token: str, nutzer: str, text: str) -> bool:
    for _ in range(40):   # Netzwerk braucht nach dem Aufwachen manchmal einige Sekunden
        try:
            if requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": nutzer, "text": text}, timeout=15).ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(8)
    return False


def main() -> None:
    test = "--test" in sys.argv
    env = dotenv_values(BASIS / ".env")
    jetzt = dt.datetime.now()
    for _ in range(18):   # bis 90 s auf den Tunnel warten, damit die Meldung gleich sagt, ob alles wieder verbunden ist
        if tunnel_steht():
            break
        time.sleep(5)
    status = "Klaus' Verbindung zum Server steht wieder." if tunnel_steht() else "Die Verbindung zum Server baut sich noch auf."
    text = (("🧪 TEST – " if test else "") + f"☀️ Der PC ist wieder da ({jetzt:%H:%M} Uhr). {status}\n"
            "Alle PC-Funktionen von Klaus sind einsatzbereit.")
    ok = bool(env.get("TELEGRAM_TOKEN") and env.get("TELEGRAM_NUTZER")) and senden(env["TELEGRAM_TOKEN"], env["TELEGRAM_NUTZER"], text)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{jetzt:%Y-%m-%dT%H:%M:%S} PC aufgewacht{' (TEST)' if test else ''} | Tunnel: {tunnel_steht()} | Telegram gesendet: {ok}\n")


if __name__ == "__main__":
    main()
