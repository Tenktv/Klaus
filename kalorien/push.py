"""Kalorien-App - Push-Benachrichtigungen (Web Push, RFC 8030/8291/8292) fuer die installierte Web-App (iPhone: ab iOS 16.4, "Zum Home-Bildschirm").

Ohne Fremdanbieter-Konto: eigener VAPID-Schluessel (data/kalorien_vapid.pem, nur auf dem Server), Nachrichten gehen verschluesselt ueber den Push-Dienst
von Apple/Google/Mozilla. Braucht das Paket "cryptography" - fehlt es, ist Push aus und alles andere laeuft weiter."""
from __future__ import annotations

import base64
import json
import os
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from . import db

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    VERFUEGBAR = True
except ImportError:   # pragma: no cover
    VERFUEGBAR = False

SCHLUESSEL = db.DATEI.parent / "kalorien_vapid.pem"
ABSENDER = os.getenv("KALORIEN_PUSH_KONTAKT") or "mailto:push@example.com"   # steht nur im Token an den Push-Dienst; keine echten Daten noetig
ZEITZONE = ZoneInfo(os.getenv("KALORIEN_ZEITZONE") or "Europe/Berlin")
ERINNERUNG_STUNDEN = (9, 20)   # nur tagsueber erinnern
STANDARD_TAGE = 2


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _privat():
    if SCHLUESSEL.exists():
        return serialization.load_pem_private_key(SCHLUESSEL.read_bytes(), None)
    k = ec.generate_private_key(ec.SECP256R1())
    SCHLUESSEL.parent.mkdir(parents=True, exist_ok=True)
    SCHLUESSEL.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    try:
        os.chmod(SCHLUESSEL, 0o600)
    except OSError:
        pass
    return k


def _punkt(pub) -> bytes:
    return pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def oeffentlicher_schluessel() -> str:
    return _b64(_punkt(_privat().public_key()))


def verschluesseln(nutzlast: bytes, p256dh: str, auth: str) -> bytes:
    """RFC 8291 (aes128gcm). Rueckgabe: kompletter Body."""
    ua_pub_bytes = _unb64(p256dh)
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_bytes)
    eph = ec.generate_private_key(ec.SECP256R1())
    eph_pub = _punkt(eph.public_key())
    geheim = eph.exchange(ec.ECDH(), ua_pub)
    salz = os.urandom(16)
    prk = HKDF(hashes.SHA256(), 32, _unb64(auth), b"WebPush: info\0" + ua_pub_bytes + eph_pub).derive(geheim)
    cek = HKDF(hashes.SHA256(), 16, salz, b"Content-Encoding: aes128gcm\0").derive(prk)
    nonce = HKDF(hashes.SHA256(), 12, salz, b"Content-Encoding: nonce\0").derive(prk)
    chiffre = AESGCM(cek).encrypt(nonce, nutzlast + b"\x02", None)
    return salz + struct.pack(">I", 4096) + bytes([len(eph_pub)]) + eph_pub + chiffre


def _vapid(endpoint: str) -> str:
    u = urllib.parse.urlparse(endpoint)
    kopf = _b64(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    inhalt = _b64(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": ABSENDER}).encode())
    k = _privat()
    r, s = decode_dss_signature(k.sign(f"{kopf}.{inhalt}".encode(), ec.ECDSA(hashes.SHA256())))
    return f"vapid t={kopf}.{inhalt}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}, k={_b64(_punkt(k.public_key()))}"


def _post(url: str, kopf: dict, body: bytes) -> int:
    req = urllib.request.Request(url, data=body, headers=kopf, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return 0


def senden(c, abo, titel: str, text: str, link: str = "/", zeit: float | None = None) -> bool:
    """Eine Nachricht an ein Geraet. Abgelaufene Abos (404/410) werden geloescht."""
    if not VERFUEGBAR:
        return False
    try:
        body = verschluesseln(json.dumps({"titel": titel, "text": text, "link": link}).encode(), abo["p256dh"], abo["auth"])
        code = _post(abo["endpoint"], {"Authorization": _vapid(abo["endpoint"]), "Content-Encoding": "aes128gcm", "TTL": "86400",
                                      "Content-Type": "application/octet-stream", "Urgency": "normal"}, body)
    except Exception:   # kaputtes Abo (z. B. ungueltiger Schluessel) -> nicht den ganzen Lauf abbrechen
        code = 410
    if code in (404, 410):
        c.execute("DELETE FROM push_abo WHERE id=?", (abo["id"],))
        return False
    if 200 <= code < 300:
        c.execute("UPDATE push_abo SET gesendet=? WHERE id=?", (int(zeit or db.jetzt()), abo["id"]))
        return True
    return False


def abo_speichern(c, nutzer: int, d: dict) -> dict:
    ep, k = str(d.get("endpoint") or ""), d.get("keys") or {}
    p, a = str(k.get("p256dh") or ""), str(k.get("auth") or "")
    if not ep.startswith("https://") or len(ep) > 600 or not p or not a or len(p) > 200 or len(a) > 100:
        raise ValueError("Ungültiges Push-Abo.")
    c.execute("INSERT INTO push_abo(nutzer, endpoint, p256dh, auth, erstellt) VALUES (?,?,?,?,?) "
              "ON CONFLICT(endpoint) DO UPDATE SET nutzer=excluded.nutzer, p256dh=excluded.p256dh, auth=excluded.auth", (nutzer, ep, p, a, db.jetzt()))
    return {"ok": True}


def abo_loeschen(c, nutzer: int, endpoint: str) -> dict:
    c.execute("DELETE FROM push_abo WHERE nutzer=? AND endpoint=?", (nutzer, str(endpoint or "")))
    return {"ok": True}


def test_senden(c, nutzer: int) -> int:
    n = 0
    for abo in c.execute("SELECT * FROM push_abo WHERE nutzer=?", (nutzer,)).fetchall():
        n += senden(c, abo, "Klesro Fit", "Test: Benachrichtigungen funktionieren.")
    return n


def _tage(profil: dict) -> int:
    try:
        return max(0, min(14, int(profil.get("erinnerung_tage", STANDARD_TAGE))))
    except (TypeError, ValueError):
        return STANDARD_TAGE


def erinnern(jetzt: float | None = None) -> int:
    """Wer N Tage nichts gemacht hat (kein App-Aufruf, kein Eintrag) bekommt EINE Erinnerung pro Pause - nur tagsueber. N=0: aus."""
    if not VERFUEGBAR:
        return 0
    jetzt = time.time() if jetzt is None else jetzt
    stunde = datetime.fromtimestamp(jetzt, ZEITZONE).hour
    if not ERINNERUNG_STUNDEN[0] <= stunde < ERINNERUNG_STUNDEN[1]:
        return 0
    c = db.verbinden()
    gesendet = 0
    try:
        for n in c.execute("SELECT DISTINCT n.id, n.profil, n.gesperrt FROM nutzer n JOIN push_abo p ON p.nutzer=n.id").fetchall():
            if n["gesperrt"]:
                continue
            try:
                tage = _tage(json.loads(n["profil"] or "{}"))
            except ValueError:
                tage = STANDARD_TAGE
            if not tage:
                continue
            aktiv = max(c.execute("SELECT COALESCE(MAX(zuletzt),0) FROM zugang WHERE nutzer=?", (n["id"],)).fetchone()[0],
                        c.execute("SELECT COALESCE(MAX(erstellt),0) FROM eintrag WHERE nutzer=?", (n["id"],)).fetchone()[0])
            if jetzt - aktiv < tage * 86400:
                continue
            for abo in c.execute("SELECT * FROM push_abo WHERE nutzer=?", (n["id"],)).fetchall():
                if abo["gesendet"] > aktiv:   # in dieser Pause schon erinnert
                    continue
                gesendet += senden(c, abo, "Klesro Fit", f"Du warst {tage} Tage nicht hier. Trag kurz ein, was du gegessen hast – dein Streak wartet.", zeit=jetzt)
        c.commit()   # sonst gehen "gesendet"-Zeit und geloeschte Abos verloren
        return gesendet
    finally:
        c.close()


def schleife(pause: float = 1800.0) -> None:
    while True:
        try:
            erinnern()
        except Exception as e:
            print(f"[Kalorien] Push: {type(e).__name__}: {e}", flush=True)
        time.sleep(pause)
