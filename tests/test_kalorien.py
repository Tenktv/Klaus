"""Kalorien-App: Konten, Tagebuch, KI-Antwort lesen, Barcode, Forum, Chat, Datenschutz."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_TMP = tempfile.mkdtemp()
os.environ["KALORIEN_DB"] = str(Path(_TMP) / "k.db")
os.environ["KALORIEN_ADMINS"] = "chef"
from kalorien import ki, nahrung, server  # noqa: E402


class Basis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.starten(port=0)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        server._versuche.clear()

    def api(self, methode, pfad, daten=None, token=None):
        anfrage = urllib.request.Request(self.url + pfad, method=methode, data=json.dumps(daten).encode() if daten is not None else None,
                                         headers={"Authorization": f"Bearer {token}"} if token else {})
        try:
            with urllib.request.urlopen(anfrage) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def neu(self, name):
        s, d = self.api("POST", "/api/registrieren", {"name": name, "passwort": "geheim1234"})
        self.assertEqual(s, 200, d)
        return d["token"]


class TestKonto(Basis):
    def test_registrieren_anmelden_und_doppelter_name(self):
        self.neu("Anna Test")
        self.assertEqual(self.api("POST", "/api/registrieren", {"name": "anna test", "passwort": "geheim1234"})[0], 409)
        self.assertEqual(self.api("POST", "/api/anmelden", {"name": "Anna Test", "passwort": "falsch"})[0], 401)
        self.assertEqual(self.api("POST", "/api/anmelden", {"name": "Anna Test", "passwort": "geheim1234"})[0], 200)

    def test_kurzes_passwort_und_ohne_anmeldung(self):
        self.assertEqual(self.api("POST", "/api/registrieren", {"name": "Kurz", "passwort": "abc"})[0], 400)
        self.assertEqual(self.api("GET", "/api/tag")[0], 401)
        self.assertEqual(self.api("GET", "/api/tag", token="kt_falsch")[0], 401)

    def test_passwort_nicht_im_klartext_gespeichert(self):
        self.neu("Geheim Ben")
        c = server.db.verbinden()
        zeile = c.execute("SELECT pw_hash, salz FROM nutzer WHERE name='Geheim Ben'").fetchone()
        c.close()
        self.assertNotIn("geheim1234", zeile["pw_hash"])
        self.assertTrue(server.db.pw_stimmt("geheim1234", zeile["salz"], zeile["pw_hash"]))

    def test_anmelde_bremse(self):
        codes = [self.api("POST", "/api/anmelden", {"name": "x", "passwort": "y"})[0] for _ in range(12)]
        self.assertIn(429, codes)


class TestTagebuch(Basis):
    def test_eintragen_summe_loeschen(self):
        t = self.neu("Tagebuch Tom")
        s, e = self.api("POST", "/api/eintrag", {"name": "Haferflocken", "kcal": 350, "eiweiss": 12, "kh": 60, "fett": 7, "datum": "2026-01-05"}, t)
        self.assertEqual(s, 200)
        self.api("POST", "/api/eintrag", {"name": "Banane", "kcal": "105,5", "datum": "2026-01-05"}, t)
        s, tag = self.api("GET", "/api/tag?datum=2026-01-05", token=t)
        self.assertEqual(round(tag["summe"]["kcal"], 1), 455.5)
        self.assertEqual(len(tag["eintraege"]), 2)
        self.api("DELETE", f"/api/eintrag/{e['id']}", token=t)
        self.assertEqual(len(self.api("GET", "/api/tag?datum=2026-01-05", token=t)[1]["eintraege"]), 1)

    def test_fremde_eintraege_bleiben_privat(self):
        a, b = self.neu("Privat Pia"), self.neu("Privat Paul")
        _, e = self.api("POST", "/api/eintrag", {"name": "Geheim-Pizza", "kcal": 900, "datum": "2026-01-06"}, a)
        self.api("DELETE", f"/api/eintrag/{e['id']}", token=b)
        self.assertEqual(len(self.api("GET", "/api/tag?datum=2026-01-06", token=a)[1]["eintraege"]), 1)
        self.assertEqual(self.api("GET", "/api/tag?datum=2026-01-06", token=b)[1]["eintraege"], [])

    def test_ungueltige_werte(self):
        t = self.neu("Fehler Fred")
        self.assertEqual(self.api("POST", "/api/eintrag", {"name": "Wasser", "kcal": -5}, t)[0], 400)
        self.assertEqual(self.api("POST", "/api/eintrag", {"name": "Wasser", "kcal": "viel"}, t)[0], 400)
        self.assertEqual(self.api("GET", "/api/tag?datum=gestern", token=t)[0], 400)

    def test_ziele_berechnen(self):
        t = self.neu("Ziel Zoe")
        s, _ = self.api("PUT", "/api/ich", {"berechnen": {"geschlecht": "w", "alter": 30, "groesse": 170, "gewicht": 65,
                                                           "aktivitaet": "leicht", "ziel": "abnehmen"}}, t)
        self.assertEqual(s, 200)
        ziele = self.api("GET", "/api/ich", token=t)[1]["ziele"]
        self.assertTrue(1200 <= ziele["kcal"] < 2000, ziele)
        self.assertEqual(self.api("PUT", "/api/ich", {"berechnen": {"alter": 3, "groesse": 170, "gewicht": 65}}, t)[0], 400)

    def test_woche_hat_sieben_tage(self):
        t = self.neu("Woche Willi")
        self.assertEqual(len(self.api("GET", "/api/woche", token=t)[1]), 7)


class TestKi(Basis):
    def test_antwort_lesen_tolerant(self):
        r = ki.lesen('```json\n{"gerichte":[{"name":"Apfel","menge":"1 Stück","kcal":"95,5","eiweiss":0.5,"kh":25,"fett":0.3}],"hinweis":"grob"}\n```')
        self.assertEqual(r["gerichte"][0]["kcal"], 95.5)
        self.assertEqual(ki.lesen('{"gerichte":[{"name":"X","kcal":999999}]}')["gerichte"][0]["kcal"], 5000)   # Obergrenze
        self.assertEqual(ki.lesen('{"gerichte":[]}')["gerichte"], [])
        with self.assertRaises(ki.KiFehler):
            ki.lesen("das ist kein json")

    def test_ohne_schluessel_klare_meldung(self):
        t = self.neu("Ki Kai")
        with mock.patch.object(ki, "schluessel", return_value=""):
            s, d = self.api("POST", "/api/schaetzen/text", {"text": "Brot"}, t)
        self.assertEqual(s, 503)
        self.assertIn("nicht eingerichtet", d["fehler"])

    def test_text_schaetzung_und_tageslimit(self):
        t = self.neu("Limit Lena")
        fake = {"gerichte": [{"name": "Rührei", "menge": "2 Eier", "kcal": 180, "eiweiss": 12, "kh": 1, "fett": 14}], "hinweis": ""}
        with mock.patch.object(ki, "schluessel", return_value="x"), mock.patch.object(ki, "_aufrufen", return_value=fake), \
                mock.patch.dict(os.environ, {"KALORIEN_KI_PRO_TAG": "2"}):
            self.assertEqual(self.api("POST", "/api/schaetzen/text", {"text": "2 Eier"}, t)[1]["gerichte"][0]["kcal"], 180)
            self.assertEqual(self.api("POST", "/api/schaetzen/text", {"text": "2 Eier"}, t)[0], 200)
            self.assertEqual(self.api("POST", "/api/schaetzen/text", {"text": "2 Eier"}, t)[0], 429)

    def test_bild_wird_geprueft(self):
        import base64
        t = self.neu("Bild Bea")
        with mock.patch.object(ki, "schluessel", return_value="x"), mock.patch.object(ki, "aus_bild", return_value={"gerichte": [], "hinweis": ""}) as m:
            self.assertEqual(self.api("POST", "/api/schaetzen/bild", {"bild": "AAAA"}, t)[0], 400)
            gross = base64.b64encode(b"\xff\xd8" + b"0" * 5000).decode()
            self.assertEqual(self.api("POST", "/api/schaetzen/bild", {"bild": gross, "mime": "image/jpeg"}, t)[0], 200)
            self.assertEqual(m.call_args[0][1], "image/jpeg")


class TestBarcode(Basis):
    def test_open_food_facts_lesen(self):
        antwort = json.dumps({"status": 1, "product": {"product_name": "Nuss-Nougat-Creme", "brands": "Marke, Zwei", "quantity": "400 g",
                                                      "serving_size": "15 g", "nutriments": {"energy-kcal_100g": 539, "proteins_100g": 6.3,
                                                                                             "carbohydrates_100g": 57.5, "fat_100g": 30.9}}})

        class Fake:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return antwort.encode()
        with mock.patch("urllib.request.urlopen", return_value=Fake()):
            p = nahrung.barcode_suchen("3017620422003")
        self.assertEqual(p["pro100"]["kcal"], 539)
        self.assertEqual(p["portion_g"], 15.0)
        self.assertEqual(p["marke"], "Marke")

    def test_ungueltiger_code_und_unbekannt(self):
        with self.assertRaises(ValueError):
            nahrung.barcode_suchen("12")
        t = self.neu("Code Carl")
        self.assertEqual(self.api("GET", "/api/barcode/abc", token=t)[0], 400)
        with mock.patch.object(nahrung, "barcode_suchen", return_value=None):
            self.assertEqual(self.api("GET", "/api/barcode/4000000000000", token=t)[0], 404)


class TestCommunity(Basis):
    def test_forum_beitrag_antwort_und_loeschen(self):
        a, b = self.neu("Forum Fritz"), self.neu("Forum Frida")
        s, th = self.api("POST", "/api/forum", {"titel": "Meal Prep Tipps", "text": "Was kocht ihr vor?"}, a)
        self.assertEqual(s, 200)
        self.assertEqual(self.api("POST", f"/api/forum/{th['id']}/antwort", {"text": "Reis mit Hähnchen"}, b)[0], 200)
        s, voll = self.api("GET", f"/api/forum/{th['id']}", token=a)
        self.assertEqual(voll["antworten"][0]["name"], "Forum Frida")
        self.assertFalse(voll["antworten"][0]["eigen"])
        self.assertEqual(self.api("POST", "/api/loeschen", {"art": "thema", "id": th["id"]}, b)[0], 403)
        self.assertEqual(self.api("POST", "/api/loeschen", {"art": "thema", "id": th["id"]}, a)[0], 200)
        self.assertEqual(self.api("GET", f"/api/forum/{th['id']}", token=a)[0], 404)

    def test_chat_blockieren_und_regeln(self):
        a, b = self.neu("Chat Chris"), self.neu("Chat Clara")
        self.api("POST", "/api/chat", {"text": "Hallo zusammen"}, a)
        self.assertTrue(any(m["text"] == "Hallo zusammen" for m in self.api("GET", "/api/chat", token=b)[1]))
        self.api("POST", "/api/blockieren", {"name": "Chat Chris"}, b)
        self.assertFalse(any(m["name"] == "Chat Chris" for m in self.api("GET", "/api/chat", token=b)[1]))
        self.assertEqual(self.api("POST", "/api/chat", {"text": "bring dich um"}, a)[0], 400)

    def test_chat_bremse_gegen_spam(self):
        a = self.neu("Spam Sam")
        codes = [self.api("POST", "/api/chat", {"text": f"Nachricht {i}"}, a)[0] for i in range(12)]
        self.assertIn(429, codes)

    def test_melden_und_admin(self):
        a, boss = self.neu("Melde Max"), self.neu("Chef")
        self.api("POST", "/api/melden", {"art": "chat", "id": 1, "grund": "Spam"}, a)
        self.assertEqual(self.api("GET", "/api/meldungen", token=a)[0], 404)       # normale Nutzer sehen keine Meldungen
        self.assertEqual(self.api("GET", "/api/meldungen", token=boss)[0], 200)
        self.assertTrue(self.api("GET", "/api/ich", token=boss)[1]["admin"])


class TestSchluesselUndDatenschutz(Basis):
    def test_schnittstellenschluessel_koennen_nicht_selbst_schluessel_machen(self):
        t = self.neu("Api Anna")
        s, z = self.api("POST", "/api/zugang", {"name": "Klaus"}, t)
        self.assertEqual(s, 200)
        self.assertTrue(z["token"].startswith("kt_"))
        self.assertEqual(self.api("GET", "/api/tag", token=z["token"])[0], 200)           # Schluessel funktioniert fuers Tagebuch
        self.assertEqual(self.api("POST", "/api/zugang", {"name": "x"}, z["token"])[0], 403)   # ...aber verwaltet keine Schluessel
        c = server.db.verbinden()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM zugang WHERE hash=?", (z["token"],)).fetchone()[0], 0)   # nur Hash gespeichert
        c.close()

    def test_konto_loeschen_entfernt_alles(self):
        t = self.neu("Weg Walter")
        self.api("POST", "/api/eintrag", {"name": "Kuchen", "kcal": 400}, t)
        self.api("POST", "/api/forum", {"titel": "Abschied", "text": "Tschüss alle"}, t)
        self.assertEqual(self.api("DELETE", "/api/ich", token=t)[0], 200)
        self.assertEqual(self.api("GET", "/api/tag", token=t)[0], 401)
        c = server.db.verbinden()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eintrag").fetchone()[0] >= 0, True)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM nutzer WHERE name='Weg Walter'").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM thema WHERE titel='Abschied'").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eintrag WHERE name='Kuchen'").fetchone()[0], 0)
        c.close()

    def test_export(self):
        t = self.neu("Export Eva")
        self.api("POST", "/api/eintrag", {"name": "Suppe", "kcal": 150}, t)
        d = self.api("GET", "/api/export", token=t)[1]
        self.assertEqual(d["tagebuch"][0]["name"], "Suppe")

    def test_statische_dateien_nicht_ausserhalb(self):
        for pfad in ("/../server.py", "/..%2fdb.py", "/%2e%2e/db.py"):
            anfrage = urllib.request.Request(self.url + pfad)
            with urllib.request.urlopen(anfrage) as r:
                self.assertNotIn(b"CREATE TABLE", r.read())


if __name__ == "__main__":
    unittest.main()
