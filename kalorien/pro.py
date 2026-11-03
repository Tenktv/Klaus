"""Fit-App - Pro-Plan: wer Pro ist, was er mehr darf, eigener KI-Schluessel (nur Pro) und Einloese-Codes.

Bezahlung ist NICHT eingebaut (dafuer braucht es einen Zahlungsanbieter wie Stripe + Rechnungen/Steuer). Bis dahin vergibt der
Betreiber Pro von Hand: Admin erstellt einen Code (oder setzt Pro direkt), der Nutzer loest ihn in der App ein.
Der Betreiber (KALORIEN_ADMINS) ist immer Pro."""
from __future__ import annotations

import os
import secrets

from . import db, ki

# Grenzen je Tag und Nutzer. KI-Schaetzungen ueber den Server-Schluessel kosten den Betreiber Geld -> frei knapp, Pro grosszuegiger.
# Mit eigenem Schluessel (nur Pro) zahlt der Nutzer selbst: dann kein Server-Limit.
FREI = {"ki": 8, "reels": 3, "rezept_ki": 0, "coach": 0}
PRO = {"ki": 60, "reels": 20, "rezept_ki": 20, "coach": 30}


class ProFehler(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(text)
        self.status, self.text = status, text


def admins() -> set[str]:
    return {a.strip().lower() for a in os.getenv("KALORIEN_ADMINS", "").split(",") if a.strip()}


def ist_admin(z) -> bool:
    return z["name"].lower() in admins()


def ist_pro(z) -> bool:
    return ist_admin(z) or (z["pro_bis"] or 0) > db.jetzt()


def grenzen(z) -> dict:
    g = dict(PRO if ist_pro(z) else FREI)
    frei_ki = os.getenv("KALORIEN_KI_PRO_TAG")   # aeltere Einstellung: Tageslimit fuer freie Nutzer
    if frei_ki and frei_ki.isdigit() and not ist_pro(z):
        g["ki"] = int(frei_ki)
    return g


def plan(z) -> dict:
    return {"pro": ist_pro(z), "bis": 0 if ist_admin(z) else int(z["pro_bis"] or 0), "admin": ist_admin(z), "grenzen": grenzen(z)}


def verlangen(z, was: str = "Das") -> None:
    if not ist_pro(z):
        raise ProFehler(402, f"{was} gibt es nur mit Pro.")


# ------------------------------------------------------------------ Eigene KI (nur Pro)
def eigene_ki(c, z) -> dict | None:
    """Konfiguration der eigenen KI (mit Schluessel!) - nur serverintern verwenden, nie an die App schicken."""
    if not ist_pro(z):
        return None
    r = c.execute("SELECT anbieter, schluessel, modell FROM nutzer_ki WHERE nutzer=?", (z["id"],)).fetchone()
    return dict(r) if r else None


def ki_status(c, z) -> dict:
    r = c.execute("SELECT anbieter, schluessel, modell FROM nutzer_ki WHERE nutzer=?", (z["id"],)).fetchone()
    return {"anbieter": ki.ANBIETER_LISTE(),
            "eigene": {"anbieter": r["anbieter"], "modell": r["modell"], "schluessel": ki.maskiert(r["schluessel"]),
                       "aktiv": ist_pro(z)} if r else None}


def ki_speichern(c, z, d: dict) -> dict:
    verlangen(z, "Eine eigene KI")
    try:
        k = ki.konfig_pruefen(str(d.get("anbieter") or ""), str(d.get("schluessel") or ""), str(d.get("modell") or ""))
    except ki.KiFehler as e:
        raise ProFehler(400, str(e))
    c.execute("INSERT INTO nutzer_ki(nutzer, anbieter, schluessel, modell, erstellt) VALUES (?,?,?,?,?) "
              "ON CONFLICT(nutzer) DO UPDATE SET anbieter=excluded.anbieter, schluessel=excluded.schluessel, modell=excluded.modell",
              (z["id"], k["anbieter"], k["schluessel"], k["modell"], db.jetzt()))
    return {"text": "Deine KI ist gespeichert. Der Schlüssel bleibt auf dem Server und wird nie wieder angezeigt.",
            "schluessel": ki.maskiert(k["schluessel"])}


def ki_loeschen(c, z) -> dict:
    c.execute("DELETE FROM nutzer_ki WHERE nutzer=?", (z["id"],))
    return {"text": "Deine KI ist entfernt, der Schlüssel gelöscht."}


def ki_testen(c, z) -> dict:
    k = eigene_ki(c, z)
    if not k:
        raise ProFehler(400, "Du hast noch keine eigene KI eingetragen.")
    try:
        ki.testen(k)
    except ki.KiFehler as e:
        raise ProFehler(502, str(e))
    return {"text": "Läuft: Dein Schlüssel funktioniert."}


# ------------------------------------------------------------------ Codes und Vergabe
def pro_verlaengern(c, nutzer: int, tage: int) -> int:
    jetzt = db.jetzt()
    alt = c.execute("SELECT pro_bis FROM nutzer WHERE id=?", (nutzer,)).fetchone()["pro_bis"] or 0
    neu = max(alt, jetzt) + tage * 86400
    c.execute("UPDATE nutzer SET pro_bis=? WHERE id=?", (neu, nutzer))
    return neu


def code_erstellen(c, z, tage: int) -> dict:
    if not ist_admin(z):
        raise ProFehler(403, "Nur für Admins.")
    if not 1 <= tage <= 3650:
        raise ProFehler(400, "Tage: 1 bis 3650.")
    code = "FIT-" + "-".join(secrets.token_hex(2).upper() for _ in range(3))
    c.execute("INSERT INTO pro_code(code, tage, erstellt) VALUES (?,?,?)", (code, tage, db.jetzt()))
    return {"code": code, "tage": tage}


def code_einloesen(c, z, code: str) -> dict:
    code = (code or "").strip().upper()
    r = c.execute("SELECT * FROM pro_code WHERE code=?", (code,)).fetchone()
    if not r or r["benutzt_von"]:
        raise ProFehler(400, "Dieser Code gilt nicht (mehr).")
    c.execute("UPDATE pro_code SET benutzt_von=?, benutzt_am=? WHERE code=?", (z["id"], db.jetzt(), code))
    return {"bis": pro_verlaengern(c, z["id"], r["tage"]), "text": f"Pro ist freigeschaltet für {r['tage']} Tage. Viel Spaß!"}


def vergeben(c, z, name: str, tage: int) -> dict:
    if not ist_admin(z):
        raise ProFehler(403, "Nur für Admins.")
    n = c.execute("SELECT id FROM nutzer WHERE name=?", (name,)).fetchone()
    if not n:
        raise ProFehler(404, "Nutzer nicht gefunden.")
    if not -3650 <= tage <= 3650 or tage == 0:
        raise ProFehler(400, "Tage: -3650 bis 3650 (negativ = entziehen).")
    if tage < 0:
        c.execute("UPDATE nutzer SET pro_bis=0 WHERE id=?", (n["id"],))
        return {"text": f"Pro für {name} beendet."}
    return {"bis": pro_verlaengern(c, n["id"], tage), "text": f"{name} hat jetzt {tage} Tage Pro."}


def nutzerliste(c, z) -> list[dict]:
    if not ist_admin(z):
        raise ProFehler(403, "Nur für Admins.")
    return [{"name": r["name"], "seit": r["erstellt"], "pro_bis": r["pro_bis"] or 0, "gesperrt": bool(r["gesperrt"]),
             "beitraege": r["b"], "eintraege": r["e"]} for r in c.execute(
        "SELECT n.*, (SELECT COUNT(*) FROM beitrag WHERE nutzer=n.id) AS b, (SELECT COUNT(*) FROM eintrag WHERE nutzer=n.id) AS e "
        "FROM nutzer n ORDER BY n.id DESC LIMIT 200")]
