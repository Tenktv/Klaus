"""Einstellungen (Nährwerte verfolgen), Push-Abo, Verschlüsselung (Gegenprobe mit eigenem Empfänger-Schlüssel) und Erinnerung bei Inaktivität."""
import base64
import json
import struct
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_kalorien import Basis  # noqa: E402
from kalorien import db, push  # noqa: E402

if push.VERFUEGBAR:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _b(x):
    return base64.urlsafe_b64encode(x).rstrip(b"=").decode()


def empfaenger():
    k = ec.generate_private_key(ec.SECP256R1())
    pub = k.public_key().public_bytes(__import__("cryptography").hazmat.primitives.serialization.Encoding.X962,
                                      __import__("cryptography").hazmat.primitives.serialization.PublicFormat.UncompressedPoint)
    auth = b"0123456789abcdef"
    return k, pub, auth


def entschluesseln(body, k, pub, auth):
    salz, eph = body[:16], body[21:21 + body[20]]
    geheim = k.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), eph))
    prk = HKDF(hashes.SHA256(), 32, auth, b"WebPush: info\0" + pub + eph).derive(geheim)
    cek = HKDF(hashes.SHA256(), 16, salz, b"Content-Encoding: aes128gcm\0").derive(prk)
    nonce = HKDF(hashes.SHA256(), 12, salz, b"Content-Encoding: nonce\0").derive(prk)
    klar = AESGCM(cek).decrypt(nonce, body[21 + body[20]:], None)
    return klar[:-1]


@unittest.skipUnless(push.VERFUEGBAR, "cryptography fehlt")
class TestPush(Basis):
    def setUp(self):
        super().setUp()
        c = db.verbinden(); c.execute("DELETE FROM push_abo"); c.commit(); c.close()    # Tests teilen sich die Datenbank

    def test_verschluesselung_laesst_sich_mit_dem_empfaengerschluessel_lesen(self):
        k, pub, auth = empfaenger()
        body = push.verschluesseln("Grüße ✓".encode(), _b(pub), _b(auth))
        self.assertEqual(struct.unpack(">I", body[16:20])[0], 4096)
        self.assertEqual(entschluesseln(body, k, pub, auth).decode(), "Grüße ✓")

    def test_vapid_kopf_und_schluessel(self):
        key = push.oeffentlicher_schluessel()
        self.assertEqual(len(base64.urlsafe_b64decode(key + "==")), 65)
        kopf = push._vapid("https://web.push.apple.com/abc")
        self.assertTrue(kopf.startswith("vapid t=") and f"k={key}" in kopf)
        jwt = kopf.split("t=")[1].split(",")[0]
        self.assertEqual(len(jwt.split(".")), 3)

    def test_abo_speichern_test_senden_loeschen_und_fremde_abos(self):
        t = self.neu("Push Paula")
        k, pub, auth = empfaenger()
        abo = {"endpoint": "https://push.example/abo1", "keys": {"p256dh": _b(pub), "auth": _b(auth)}}
        self.assertEqual(self.api("GET", "/api/push/schluessel", token=t)[1]["key"], push.oeffentlicher_schluessel())
        self.assertEqual(self.api("POST", "/api/push/abo", abo, t)[0], 200)
        self.assertEqual(self.api("POST", "/api/push/abo", {"endpoint": "http://unsicher", "keys": {}}, t)[0], 400)
        gesehen = {}
        def fake(url, kopf, body):
            gesehen["url"] = url; gesehen["klar"] = json.loads(entschluesseln(body, k, pub, auth)); return 201
        with mock.patch.object(push, "_post", fake):
            self.assertEqual(self.api("POST", "/api/push/test", {}, t)[1]["gesendet"], 1)
        self.assertEqual(gesehen["url"], "https://push.example/abo1")
        self.assertIn("Test", gesehen["klar"]["text"])
        self.assertEqual(self.api("DELETE", "/api/push/abo", {"endpoint": "https://push.example/abo1"}, t)[0], 200)
        with mock.patch.object(push, "_post", fake):
            self.assertEqual(self.api("POST", "/api/push/test", {}, t)[1]["gesendet"], 0)

    def test_abgelaufenes_abo_wird_geloescht(self):
        t = self.neu("Push Paul")
        k, pub, auth = empfaenger()
        self.api("POST", "/api/push/abo", {"endpoint": "https://push.example/alt", "keys": {"p256dh": _b(pub), "auth": _b(auth)}}, t)
        with mock.patch.object(push, "_post", return_value=410):
            self.api("POST", "/api/push/test", {}, t)
        c = db.verbinden()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM push_abo WHERE endpoint='https://push.example/alt'").fetchone()[0], 0)

    def test_erinnerung_bei_inaktivitaet_einmal_pro_pause_nur_tagsueber(self):
        t = self.neu("Push Pia")
        k, pub, auth = empfaenger()
        self.api("POST", "/api/push/abo", {"endpoint": "https://push.example/pia", "keys": {"p256dh": _b(pub), "auth": _b(auth)}}, t)
        c = db.verbinden()
        nid = c.execute("SELECT id FROM nutzer WHERE name='Push Pia'").fetchone()[0]
        c.execute("UPDATE zugang SET zuletzt=? WHERE nutzer=?", (int(time.time()) - 5 * 86400, nid)); c.commit()
        from datetime import datetime
        mittag = datetime(2026, 11, 25, 12, 0, tzinfo=push.ZEITZONE).timestamp()
        nachts = datetime(2026, 11, 25, 3, 0, tzinfo=push.ZEITZONE).timestamp()
        # "jetzt" liegt in der Zukunft, damit Pia als 5+ Tage inaktiv gilt
        c.execute("UPDATE zugang SET zuletzt=? WHERE nutzer=?", (int(mittag) - 5 * 86400, nid)); c.commit()
        with mock.patch.object(push, "_post", return_value=201) as p:
            self.assertEqual(push.erinnern(nachts), 0)           # nachts nicht
            self.assertEqual(push.erinnern(mittag), 1)           # tagsüber: Erinnerung
            self.assertEqual(push.erinnern(mittag + 60), 0)      # nicht nochmal in derselben Pause
        # wieder aktiv -> später neue Pause -> wieder erinnern
        c.execute("UPDATE zugang SET zuletzt=? WHERE nutzer=?", (int(mittag) + 3600, nid)); c.commit()
        with mock.patch.object(push, "_post", return_value=201):
            self.assertEqual(push.erinnern(mittag + 3 * 86400), 1)

    def test_erinnerung_aus_und_aktive_nutzer_bekommen_nichts(self):
        t = self.neu("Push Pit")
        k, pub, auth = empfaenger()
        self.api("POST", "/api/push/abo", {"endpoint": "https://push.example/pit", "keys": {"p256dh": _b(pub), "auth": _b(auth)}}, t)
        from datetime import datetime
        mittag = datetime(2026, 11, 25, 12, 0, tzinfo=push.ZEITZONE).timestamp()
        c = db.verbinden()
        nid = c.execute("SELECT id FROM nutzer WHERE name='Push Pit'").fetchone()[0]
        c.execute("UPDATE zugang SET zuletzt=? WHERE nutzer=?", (int(mittag) - 10 * 86400, nid)); c.commit()
        self.assertEqual(self.api("PUT", "/api/ich", {"erinnerung_tage": 0}, t)[0], 200)
        with mock.patch.object(push, "_post", return_value=201):
            self.assertEqual(push.erinnern(mittag), 0)           # Erinnerung aus
            self.api("PUT", "/api/ich", {"erinnerung_tage": 3}, t)
            c.execute("UPDATE zugang SET zuletzt=? WHERE nutzer=?", (int(mittag) - 3600, nid)); c.commit()
            self.assertEqual(push.erinnern(mittag), 0)           # war gerade erst aktiv
        self.assertEqual(self.api("PUT", "/api/ich", {"erinnerung_tage": "x"}, t)[0], 400)


class TestNaehrwerteAuswahl(Basis):
    def test_auswahl_wird_gespeichert_und_bereinigt(self):
        t = self.neu("Track Tina")
        self.assertEqual(self.api("PUT", "/api/ich", {"mikro_track": ["vitamin_c", "eisen", "quatsch"]}, t)[0], 200)
        self.assertEqual(self.api("GET", "/api/ich", token=t)[1]["profil"]["mikro_track"], ["vitamin_c", "eisen"])
        self.api("PUT", "/api/ich", {"mikro_track": []}, t)
        self.assertEqual(self.api("GET", "/api/ich", token=t)[1]["profil"]["mikro_track"], [])
        self.api("PUT", "/api/ich", {"verbrauch": "halb"}, t)          # andere Einstellungen löschen die Auswahl nicht
        self.assertEqual(self.api("GET", "/api/ich", token=t)[1]["profil"]["mikro_track"], [])

    def test_ziele_berechnen_behaelt_auswahl(self):
        t = self.neu("Track Tom")
        self.api("PUT", "/api/ich", {"mikro_track": ["zink"], "erinnerung_tage": 4}, t)
        self.api("PUT", "/api/ich", {"berechnen": {"geschlecht": "m", "alter": 30, "groesse": 180, "gewicht": 80, "aktivitaet": "leicht", "ziel": "halten"}}, t)
        p = self.api("GET", "/api/ich", token=t)[1]["profil"]
        self.assertEqual((p.get("mikro_track"), p.get("erinnerung_tage")), (["zink"], 4))


if __name__ == "__main__":
    unittest.main()
