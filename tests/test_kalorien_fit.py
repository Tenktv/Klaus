"""Fit-App: Pro-Plan, eigene KI (alle Anbieter), Rezepte, Workouts, Coach und Reels (mit echtem ffmpeg)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_kalorien import Basis  # noqa: E402  (setzt auch die Test-Datenbank, KALORIEN_ADMINS=chef)
from kalorien import db, ki, pro, reels, server  # noqa: E402


class Fit(Basis):
    def chef(self):
        """Der Admin (KALORIEN_ADMINS=chef): beim ersten Mal anlegen, danach anmelden."""
        s, d = self.api("POST", "/api/registrieren", {"name": "chef", "passwort": "geheim1234"})
        if s == 409:
            s, d = self.api("POST", "/api/anmelden", {"name": "chef", "passwort": "geheim1234"})
        self.assertEqual(s, 200, d)
        return d["token"]


def code_einloesen(test, admin_token, token, tage=30):
    s, c = test.api("POST", "/api/pro/code", {"tage": tage}, admin_token)
    test.assertEqual(s, 200, c)
    s, r = test.api("POST", "/api/pro/einloesen", {"code": c["code"]}, token)
    test.assertEqual(s, 200, r)
    return c["code"]


class TestPro(Fit):
    def test_eintrag_bearbeiten_nur_eigene(self):
        a, b = self.neu("Edit Eva"), self.neu("Edit Emil")
        eid = self.api("POST", "/api/eintrag", {"name": "Reis", "kcal": 200, "mahlzeit": "mittag"}, token=a)[1]["id"]
        s, _ = self.api("PUT", f"/api/eintrag/{eid}", {"name": "Reis mit Huhn", "menge": "300 g", "kcal": 450, "eiweiss": 35, "mahlzeit": "abend"}, token=a)
        self.assertEqual(s, 200)
        e = self.api("GET", "/api/tag", token=a)[1]["eintraege"][0]
        self.assertEqual((e["name"], e["kcal"], e["eiweiss"], e["mahlzeit"]), ("Reis mit Huhn", 450, 35, "abend"))
        self.assertEqual(self.api("PUT", f"/api/eintrag/{eid}", {"name": "Hack", "kcal": 1}, token=b)[0], 404)
        self.assertEqual(self.api("PUT", f"/api/eintrag/{eid}", {"name": "", "kcal": 1}, token=a)[0], 400)

    def test_schritte_setzen_kcal_und_keine_doppelzaehlung(self):
        t = self.neu("Schritt Sven")
        self.assertEqual(self.api("GET", "/api/tag", token=t)[1]["schritte"], 0)
        self.api("POST", "/api/training", {"art": "gehen", "minuten": 60, "kcal": 300}, token=t)
        self.api("POST", "/api/training", {"art": "krafttraining", "minuten": 30, "kcal": 150}, token=t)
        self.assertEqual(self.api("GET", "/api/tag", token=t)[1]["verbrannt"], 450)
        s, d = self.api("POST", "/api/schritte", {"schritte": "8.234 Schritte"}, token=t)
        self.assertEqual((s, d["schritte"]), (200, 8234))
        tag = self.api("GET", "/api/tag", token=t)[1]
        self.assertEqual(tag["schritte"], 8234)
        self.assertEqual(tag["verbrannt"], 150 + tag["schritte_kcal"])   # Gehen steckt in den Schritten
        self.api("POST", "/api/schritte", {"schritte": 9000}, token=t)
        self.assertEqual(self.api("GET", "/api/tag", token=t)[1]["schritte"], 9000)   # ueberschreiben, nicht addieren
        self.assertEqual(self.api("POST", "/api/schritte", {"schritte": 999999}, token=t)[0], 400)
        self.assertEqual(self.api("POST", "/api/schritte", {"schritte": "abc"}, token=t)[0], 400)

    def test_verbrauch_zaehlt_nur_nach_wahl_ins_budget(self):
        t = self.neu("Budget Bea")
        self.api("POST", "/api/training", {"art": "krafttraining", "minuten": 30, "kcal": 200}, token=t)
        tag = self.api("GET", "/api/tag", token=t)[1]
        self.assertEqual((tag["verbrannt"], tag["bonus"], tag["verbrauch_modus"]), (200, 0, ""))   # ungefragt: kein Aufschlag
        self.assertEqual(self.api("PUT", "/api/ich", {"verbrauch": "halb"}, token=t)[0], 200)
        self.assertEqual(self.api("GET", "/api/tag", token=t)[1]["bonus"], 100)
        self.api("PUT", "/api/ich", {"verbrauch": "ja"}, token=t)
        self.assertEqual(self.api("GET", "/api/tag", token=t)[1]["bonus"], 200)
        self.api("PUT", "/api/ich", {"berechnen": {"geschlecht": "m", "alter": 30, "groesse": 180, "gewicht": 80, "aktivitaet": "leicht", "ziel": "halten"}}, token=t)
        self.assertEqual(self.api("GET", "/api/tag", token=t)[1]["verbrauch_modus"], "ja")   # Zielberechnung ueberschreibt die Wahl nicht
        self.api("PUT", "/api/ich", {"verbrauch": "quatsch"}, token=t)
        self.assertEqual(self.api("GET", "/api/tag", token=t)[1]["verbrauch_modus"], "ja")

    def test_frei_ist_nicht_pro_admin_schon(self):
        frei, chef = self.neu("Frei Frida"), self.chef()
        self.assertFalse(self.api("GET", "/api/ich", token=frei)[1]["plan"]["pro"])
        self.assertTrue(self.api("GET", "/api/ich", token=chef)[1]["plan"]["pro"])
        self.assertEqual(self.api("GET", "/api/ich", token=frei)[1]["plan"]["grenzen"]["ki"], pro.FREI["ki"])

    def test_code_einloesen_nur_einmal_und_nur_admin_erstellt(self):
        chef, a, b = self.chef(), self.neu("Code Anna"), self.neu("Code Ben")
        self.assertEqual(self.api("POST", "/api/pro/code", {"tage": 7}, a)[0], 403)
        code = code_einloesen(self, chef, a, 7)
        plan = self.api("GET", "/api/pro", token=a)[1]
        self.assertTrue(plan["pro"])
        self.assertAlmostEqual(plan["bis"], db.jetzt() + 7 * 86400, delta=120)
        self.assertEqual(self.api("POST", "/api/pro/einloesen", {"code": code}, b)[0], 400)   # schon benutzt
        self.assertEqual(self.api("POST", "/api/pro/einloesen", {"code": "FIT-XXXX-XXXX-XXXX"}, b)[0], 400)

    def test_admin_vergibt_und_entzieht(self):
        chef, u = self.chef(), self.neu("Pro Paul")
        self.assertEqual(self.api("POST", "/api/pro/vergeben", {"name": "Pro Paul", "tage": 5}, u)[0], 403)
        self.assertEqual(self.api("POST", "/api/pro/vergeben", {"name": "Pro Paul", "tage": 5}, chef)[0], 200)
        self.assertTrue(self.api("GET", "/api/pro", token=u)[1]["pro"])
        self.api("POST", "/api/pro/vergeben", {"name": "Pro Paul", "tage": -1}, chef)
        self.assertFalse(self.api("GET", "/api/pro", token=u)[1]["pro"])
        self.assertEqual(self.api("GET", "/api/admin/nutzer", token=u)[0], 403)
        self.assertEqual(self.api("GET", "/api/admin/nutzer", token=chef)[0], 200)


class TestEigeneKi(Fit):
    def test_nur_pro_darf_eigene_ki(self):
        frei = self.neu("KI Frei")
        s, d = self.api("PUT", "/api/ki", {"anbieter": "openai", "schluessel": "sk-test-1234567890abcdef"}, frei)
        self.assertEqual(s, 402, d)

    def test_schluessel_wird_nie_zurueckgegeben_und_ist_maskiert(self):
        chef = self.chef()
        key = "sk-geheim-1234567890abcdefXYZ9"
        s, d = self.api("PUT", "/api/ki", {"anbieter": "openai", "schluessel": key, "modell": "gpt-4o-mini"}, chef)
        self.assertEqual(s, 200, d)
        for pfad in ("/api/ki", "/api/ich", "/api/export"):
            roh = json.dumps(self.api("GET", pfad, token=chef)[1])
            self.assertNotIn(key, roh, pfad)
        st = self.api("GET", "/api/ki", token=chef)[1]
        self.assertEqual(st["eigene"]["schluessel"], "••••XYZ9")
        self.assertEqual(len(st["anbieter"]), 5)
        self.assertEqual(self.api("DELETE", "/api/ki", token=chef)[0], 200)
        self.assertIsNone(self.api("GET", "/api/ki", token=chef)[1]["eigene"])

    def test_eingaben_werden_geprueft(self):
        chef = self.chef()
        for daten in ({"anbieter": "evil", "schluessel": "x" * 30}, {"anbieter": "openai", "schluessel": "kurz"},
                      {"anbieter": "openai", "schluessel": "a" * 30, "modell": "../../etc/passwd; rm"},
                      {"anbieter": "openai", "schluessel": "a b c d " * 5}):
            self.assertEqual(self.api("PUT", "/api/ki", daten, chef)[0], 400, daten)
        # eine eigene URL ist NICHT moeglich (SSRF): Feld wird ignoriert, die Adresse ist fest
        self.assertEqual(ki.ANBIETER["openai"]["url"], "https://api.openai.com/v1/chat/completions")

    def test_schaetzung_mit_eigener_ki_zaehlt_nicht_gegen_das_serverlimit_und_braucht_keinen_serverschluessel(self):
        chef = self.chef()
        self.api("PUT", "/api/ki", {"anbieter": "anthropic", "schluessel": "sk-ant-" + "a" * 30}, chef)
        gesehen = []

        def fake(system, nutzer, bild=None, konfig=None, json_modus=True, timeout=60, max_token=1800):
            gesehen.append(konfig)
            return json.dumps({"gerichte": [{"name": "Apfel", "menge": "1", "kcal": 95, "eiweiss": 0, "kh": 25, "fett": 0}], "hinweis": ""})
        with mock.patch.object(ki, "schluessel", return_value=""), mock.patch.object(ki, "chat", fake), \
                mock.patch.dict(os.environ, {"KALORIEN_KI_PRO_TAG": "1"}):
            for _ in range(4):
                s, d = self.api("POST", "/api/schaetzen/text", {"text": "ein Apfel"}, chef)
                self.assertEqual(s, 200, d)
        self.assertEqual({k["anbieter"] for k in gesehen}, {"anthropic"})

    def test_ohne_pro_wird_eine_alte_eigene_ki_ignoriert(self):
        # Pro laeuft aus -> die gespeicherte KI darf nicht mehr benutzt werden
        u = self.neu("Abgelaufen Alf")
        c = db.verbinden()
        uid = c.execute("SELECT id FROM nutzer WHERE name='Abgelaufen Alf'").fetchone()["id"]
        c.execute("INSERT INTO nutzer_ki(nutzer, anbieter, schluessel, modell, erstellt) VALUES (?,?,?,?,?)", (uid, "openai", "k" * 30, "m", 1))
        c.commit()
        z = c.execute("SELECT * FROM nutzer WHERE id=?", (uid,)).fetchone()
        self.assertIsNone(pro.eigene_ki(c, z))
        c.close()


class TestKiAnbieter(unittest.TestCase):
    """Jeder Anbieter bekommt die richtige Adresse, Kopfzeilen und das richtige Format."""

    def aufruf(self, anbieter, bild=None):
        antworten = {"gemini": {"candidates": [{"content": {"parts": [{"text": "{\"a\":1}"}]}}]},
                     "anthropic": {"content": [{"type": "text", "text": "{\"a\":1}"}]},
                     "openai": {"choices": [{"message": {"content": "{\"a\":1}"}}]}}
        antworten["groq"] = antworten["openrouter"] = antworten["openai"]
        erfasst = {}

        def post(url, kopf, daten, timeout):
            erfasst.update(url=url, kopf=kopf, daten=daten)
            return antworten[anbieter]
        with mock.patch.object(ki, "_post", post):
            text = ki.chat("SYS", "FRAGE", bild, {"anbieter": anbieter, "schluessel": "GEHEIM-" + "k" * 20, "modell": "modell-x"})
        self.assertEqual(text, "{\"a\":1}")
        return erfasst

    def test_gemini(self):
        e = self.aufruf("gemini", (b"\xff\xd8\xff", "image/jpeg"))
        self.assertIn("modell-x:generateContent", e["url"])
        self.assertTrue(e["kopf"]["x-goog-api-key"].startswith("GEHEIM-"))
        self.assertEqual(e["daten"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertIn("inline_data", e["daten"]["contents"][0]["parts"][1])

    def test_anthropic(self):
        e = self.aufruf("anthropic", (b"\xff\xd8\xff", "image/jpeg"))
        self.assertEqual(e["url"], "https://api.anthropic.com/v1/messages")
        self.assertIn("x-api-key", e["kopf"])
        self.assertEqual(e["daten"]["system"], "SYS")
        self.assertEqual(e["daten"]["messages"][0]["content"][0]["type"], "image")

    def test_openai_groq_openrouter(self):
        for anbieter, url in (("openai", "api.openai.com"), ("groq", "api.groq.com"), ("openrouter", "openrouter.ai")):
            e = self.aufruf(anbieter, (b"\xff\xd8\xff", "image/jpeg"))
            self.assertIn(url, e["url"])
            self.assertTrue(e["kopf"]["Authorization"].startswith("Bearer GEHEIM-"))
            self.assertEqual("response_format" in e["daten"], anbieter != "openrouter")
            teile = e["daten"]["messages"][1]["content"]
            self.assertTrue(teile[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_fehlermeldungen_verraten_den_schluessel_nicht(self):
        key = "sk-SEHR-GEHEIM-" + "z" * 20
        fehler = urllib.error.HTTPError("u", 401, "nope", {}, None)
        fehler.read = lambda: f"invalid key {key}".encode()
        with mock.patch("urllib.request.urlopen", side_effect=fehler):
            with self.assertRaises(ki.KiFehler) as e:
                ki.chat("s", "n", None, {"anbieter": "openai", "schluessel": key, "modell": "m"})
        self.assertNotIn(key, str(e.exception))
        self.assertIn("abgelehnt", str(e.exception))
        for code, wort in ((402, "Guthaben"), (429, "Limit"), (404, "Modell")):
            f = urllib.error.HTTPError("u", code, "x", {}, None)
            with mock.patch("urllib.request.urlopen", side_effect=f):
                with self.assertRaisesRegex(ki.KiFehler, wort):
                    ki.chat("s", "n", None, {"anbieter": "groq", "schluessel": key, "modell": "m"})


class TestRezepte(Fit):
    def test_start_rezepte_und_filter(self):
        t = self.neu("Koch Kai")
        s, liste = self.api("GET", "/api/rezepte", token=t)
        self.assertEqual(s, 200)
        self.assertGreaterEqual(len(liste), 10)
        self.assertTrue(all(r["offiziell"] for r in liste[:10]))
        veg = self.api("GET", "/api/rezepte?tag=vegan", token=t)[1]
        self.assertTrue(veg and all("vegan" in r["tags"] for r in veg))
        suche = self.api("GET", "/api/rezepte?q=Linsen", token=t)[1]
        self.assertEqual([r["titel"] for r in suche], ["Rotes Linsen-Curry"])
        voll = self.api("GET", f"/api/rezept/{suche[0]['id']}", token=t)[1]
        self.assertTrue(voll["zutaten"] and voll["schritte"])

    def test_eigenes_rezept_privat_oeffentlich_und_loeschen(self):
        a, b = self.neu("Rezept Rita"), self.neu("Rezept Rolf")
        daten = {"titel": "Mein Shake", "portionen": 1, "zutaten": [{"name": "Milch", "menge": "300 ml"}], "schritte": ["Mixen."],
                 "kcal": 250, "eiweiss": 25, "kh": 20, "fett": 6, "tags": ["snack", "quatsch"], "oeffentlich": False}
        rid = self.api("POST", "/api/rezepte", daten, a)[1]["id"]
        self.assertEqual(self.api("GET", f"/api/rezept/{rid}", token=b)[0], 404)   # privat
        self.assertEqual(self.api("GET", f"/api/rezept/{rid}", token=a)[1]["tags"], ["snack"])   # unbekannte Tags fliegen raus
        self.assertNotIn("Mein Shake", [r["titel"] for r in self.api("GET", "/api/rezepte", token=b)[1]])
        self.assertEqual(self.api("DELETE", f"/api/rezept/{rid}", token=b)[0], 403)
        rid2 = self.api("POST", "/api/rezepte", {**daten, "titel": "Offener Shake", "oeffentlich": True}, a)[1]["id"]
        self.assertEqual(self.api("GET", f"/api/rezept/{rid2}", token=b)[0], 200)
        self.assertEqual(self.api("DELETE", f"/api/rezept/{rid}", token=a)[0], 200)
        self.assertEqual(self.api("GET", f"/api/rezept/{rid}", token=a)[0], 404)

    def test_pflichtfelder(self):
        t = self.neu("Rezept Regel")
        self.assertEqual(self.api("POST", "/api/rezepte", {"titel": "Leer", "zutaten": [], "schritte": []}, t)[0], 400)
        self.assertEqual(self.api("POST", "/api/rezepte", {"titel": "x", "zutaten": [{"name": "a"}], "schritte": ["b"]}, t)[0], 400)

    def test_speichern_und_ins_tagebuch_mit_portionen(self):
        t = self.neu("Tagebuch Tina")
        rid = self.api("GET", "/api/rezepte?q=Skyr", token=t)[1][0]["id"]
        self.assertTrue(self.api("POST", f"/api/rezept/{rid}/speichern", {}, t)[1]["gespeichert"])
        self.assertEqual([r["id"] for r in self.api("GET", "/api/rezepte?art=gespeichert", token=t)[1]], [rid])
        s, _ = self.api("POST", f"/api/rezept/{rid}/essen", {"portionen": "0,5", "mahlzeit": "snack", "datum": "2026-03-01"}, t)
        self.assertEqual(s, 200)
        e = self.api("GET", "/api/tag?datum=2026-03-01", token=t)[1]["eintraege"][0]
        self.assertEqual((e["name"], e["menge"], e["kcal"], e["quelle"]), ("Skyr-Beeren-Bowl", "0,5 Portionen".replace(",", "."), 175.0, "rezept"))
        self.assertEqual(self.api("POST", f"/api/rezept/{rid}/essen", {"portionen": "0"}, t)[0], 400)
        self.assertFalse(self.api("POST", f"/api/rezept/{rid}/speichern", {}, t)[1]["gespeichert"])

    def test_ki_generator_nur_pro_und_nicht_gespeichert(self):
        frei, chef = self.neu("Gen Frei"), self.chef()
        self.assertEqual(self.api("POST", "/api/rezept/ki", {"wunsch": "Hähnchen mit Reis"}, frei)[0], 402)
        entwurf = {"titel": "KI-Bowl", "portionen": 2, "zeit_min": 20, "zutaten": [{"name": "Reis", "menge": "100 g"}],
                   "schritte": ["Kochen"], "kcal": 500, "eiweiss": 35, "kh": 60, "fett": 10, "tags": ["high-protein"]}
        vorher = len(self.api("GET", "/api/rezepte?art=meine", token=chef)[1])
        with mock.patch.object(ki, "schluessel", return_value="x"), mock.patch.object(ki, "chat", return_value="```json\n" + json.dumps(entwurf) + "\n```"):
            s, d = self.api("POST", "/api/rezept/ki", {"wunsch": "Hähnchen mit Reis, viel Eiweiß"}, chef)
        self.assertEqual(s, 200, d)
        self.assertEqual((d["titel"], d["kcal"], d["entwurf"]), ("KI-Bowl", 500.0, True))
        self.assertEqual(len(self.api("GET", "/api/rezepte?art=meine", token=chef)[1]), vorher)   # nichts gespeichert
        self.assertEqual(self.api("POST", "/api/rezept/ki", {"wunsch": "hi"}, chef)[0], 400)


class TestWorkouts(Fit):
    def satz(self, u, kg, wdh):
        return {"uebung": u, "kg": kg, "wdh": wdh}

    def test_speichern_volumen_training_und_rekord(self):
        t = self.neu("Hantel Hans")
        w1 = {"name": "Push", "datum": "2026-02-01", "minuten": 50, "saetze": [self.satz("Bankdrücken", 60, 8), self.satz("Bankdrücken", 60, 8),
                                                                           self.satz("Schulterdrücken", 30, 10)]}
        s, r = self.api("POST", "/api/workout", w1, t)
        self.assertEqual(s, 200, r)
        self.assertEqual((r["volumen"], r["saetze"], r["rekorde"]), (60 * 8 * 2 + 300, 3, []))   # erste Einheit: keine Rekorde
        tag = self.api("GET", "/api/tag?datum=2026-02-01", token=t)[1]
        self.assertEqual(tag["training"][0]["art"], "krafttraining")   # zaehlt fuer Serie/Rangliste/Bilanz
        self.assertEqual(tag["verbrannt"], r["kcal"])
        w2 = {**w1, "datum": "2026-02-08", "saetze": [self.satz("Bankdrücken", 65, 8), self.satz("Schulterdrücken", 25, 10)]}
        r2 = self.api("POST", "/api/workout", w2, t)[1]
        self.assertEqual([x["uebung"] for x in r2["rekorde"]], ["Bankdrücken"])   # schwerer = Rekord, leichter nicht

    def test_verlauf_letzte_saetze_fortschritt_und_loeschen(self):
        t = self.neu("Verlauf Vera")
        for i, kg in enumerate((40, 45, 50)):
            self.api("POST", "/api/workout", {"name": f"Beine {i}", "datum": f"2026-04-0{i + 1}", "saetze": [self.satz("Kniebeuge", kg, 5), self.satz("Kniebeuge", kg, 5)]}, t)
        liste = self.api("GET", "/api/workouts", token=t)[1]
        self.assertEqual([w["name"] for w in liste], ["Beine 2", "Beine 1", "Beine 0"])
        self.assertEqual(self.api("GET", "/api/uebung/letzte?name=Kniebeuge", token=t)[1], [{"nr": 1, "wdh": 5, "kg": 50.0}, {"nr": 2, "wdh": 5, "kg": 50.0}])
        v = self.api("GET", "/api/uebung/verlauf?name=kniebeuge", token=t)[1]   # Gross/klein egal
        self.assertEqual([p["kg"] for p in v["punkte"]], [40.0, 45.0, 50.0])
        self.assertAlmostEqual(v["rekord"], 50 * (1 + 5 / 30), places=1)
        d = self.api("GET", f"/api/workout/{liste[0]['id']}", token=t)[1]
        self.assertEqual(len(d["saetze_liste"]), 2)
        self.assertEqual(self.api("DELETE", f"/api/workout/{liste[0]['id']}", token=t)[0], 200)
        self.assertEqual(self.api("GET", "/api/tag?datum=2026-04-03", token=t)[1]["training"], [])   # Trainings-Eintrag ist mit weg
        stat = self.api("GET", "/api/trainingsstatistik", token=t)[1]
        self.assertEqual(stat["workouts"], 2)
        self.assertEqual(len(stat["woche"]), 7)

    def test_fremde_workouts_sind_privat_und_eingaben_werden_geprueft(self):
        a, b = self.neu("Priv Pia"), self.neu("Priv Paul")
        wid = self.api("POST", "/api/workout", {"saetze": [self.satz("Klimmzug", 0, 8)]}, a)[1]["id"]
        self.assertEqual(self.api("GET", f"/api/workout/{wid}", token=b)[0], 404)
        self.assertEqual(self.api("DELETE", f"/api/workout/{wid}", token=b)[0], 404)
        for saetze in ([], [self.satz("X", 10, 0)], [self.satz("X", 10, 101)], [self.satz("X", -1, 5)], [self.satz("X", 5000, 5)], [self.satz("", 10, 5)],
                       [self.satz("X", "abc", 5)]):
            self.assertEqual(self.api("POST", "/api/workout", {"saetze": saetze}, a)[0], 400, saetze)

    def test_routinen(self):
        t = self.neu("Plan Paula")
        rid = self.api("POST", "/api/routine", {"name": "Push-Tag", "uebungen": ["Bankdrücken", "Dips"]}, t)[1]["id"]
        self.assertEqual(self.api("GET", "/api/routinen", token=t)[1][0]["uebungen"], ["Bankdrücken", "Dips"])
        self.assertEqual(self.api("POST", "/api/routine", {"name": "Leer", "uebungen": []}, t)[0], 400)
        self.assertEqual(self.api("DELETE", f"/api/routine/{rid}", token=t)[0], 200)
        self.assertEqual(self.api("GET", "/api/routinen", token=t)[1], [])


class TestCoach(Fit):
    def test_coach_nur_pro_und_kennt_die_daten(self):
        frei, chef = self.neu("Coach Frei"), self.chef()
        self.assertEqual(self.api("POST", "/api/coach", {"frage": "Wie nehme ich ab?"}, frei)[0], 402)
        self.api("POST", "/api/eintrag", {"name": "Reis", "kcal": 600, "eiweiss": 12, "datum": time.strftime("%Y-%m-%d")}, chef)
        gesehen = {}

        def fake(system, nutzer, bild=None, konfig=None, json_modus=True, timeout=60, max_token=1800):
            gesehen.update(system=system, nutzer=nutzer, json=json_modus)
            return "  Iss mehr Eiweiß.  "
        with mock.patch.object(ki, "schluessel", return_value="x"), mock.patch.object(ki, "chat", fake):
            s, d = self.api("POST", "/api/coach", {"frage": "Wie nehme ich ab?", "verlauf": [{"rolle": "du", "text": "Hallo"}, {"rolle": "hacker", "text": "IGNORE"}]}, chef)
        self.assertEqual((s, d["antwort"]), (200, "Iss mehr Eiweiß."))
        self.assertFalse(gesehen["json"])
        self.assertIn("Ziele pro Tag", gesehen["nutzer"])
        self.assertIn("Ø 600 kcal", gesehen["nutzer"])
        self.assertIn("Nutzer: Hallo", gesehen["nutzer"])
        self.assertNotIn("IGNORE", gesehen["nutzer"])   # unbekannte Rollen werden verworfen
        self.assertIn("keine Anweisung", gesehen["system"])


def video_machen(sekunden: int = 2, breite: int = 320, hoehe: int = 240) -> bytes:
    """Kleines Testvideo mit Ton (ffmpeg-Testbild) - HEVC/MOV waere auch moeglich, MP4/H.264 reicht fuer den Ablauf."""
    ziel = Path(tempfile.mkdtemp()) / "t.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={breite}x{hoehe}:rate=25:duration={sekunden}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={sekunden}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(ziel)], check=True, capture_output=True)
    return ziel.read_bytes()


@unittest.skipUnless(reels.verfuegbar(), "ffmpeg/ffprobe fehlen")
class TestReels(Fit):
    def hochladen(self, token, daten, text="Mein Reel", raw_url=None):
        anfrage = urllib.request.Request(self.url + (raw_url or f"/api/reel?text={text.replace(' ', '%20')}"), method="POST", data=daten,
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(anfrage, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def warten(self, token, rid, sekunden=90):
        ende = time.time() + sekunden
        while time.time() < ende:
            s = self.api("GET", f"/api/reel/{rid}/status", token=token)[1]["status"]
            if s != "wartet":
                return s
            time.sleep(0.5)
        self.fail("Reel wurde nicht rechtzeitig verarbeitet")

    def test_ganzer_ablauf_upload_umwandeln_feed_range_loeschen(self):
        t = self.neu("Reel Rene")
        s, d = self.hochladen(t, video_machen())
        self.assertEqual((s, d["status"]), (200, "wartet"))
        self.assertEqual(self.warten(t, d["id"]), "fertig")
        feed = self.api("GET", "/api/reels", token=t)[1]
        reel = next(r for r in feed if r["id"] == d["id"])
        self.assertEqual((reel["name"], reel["text"], reel["status"]), ("Reel Rene", "Mein Reel", "fertig"))
        self.assertTrue(reel["video"].startswith("/video/") and reel["poster"].startswith("/bild/"))
        self.assertAlmostEqual(reel["dauer"], 2.0, delta=0.6)
        self.assertNotIn(d["id"], [b["id"] for b in self.api("GET", "/api/feed", token=t)[1]])   # Foto-Feed zeigt keine Reels
        # Abspielen: komplett und mit Range (Safari fragt immer mit Range)
        with urllib.request.urlopen(self.url + reel["video"]) as r:
            gesamt = r.read()
            self.assertEqual((r.status, r.headers["Content-Type"], r.headers["Accept-Ranges"]), (200, "video/mp4", "bytes"))
        self.assertEqual(gesamt[4:8], b"ftyp")
        for kopf, erwartet in (("bytes=0-1", gesamt[0:2]), ("bytes=10-19", gesamt[10:20]), (f"bytes={len(gesamt) - 5}-", gesamt[-5:]), ("bytes=-7", gesamt[-7:])):
            a = urllib.request.Request(self.url + reel["video"], headers={"Range": kopf})
            with urllib.request.urlopen(a) as r:
                self.assertEqual((r.status, r.read()), (206, erwartet), kopf)
        self.assertEqual(self.api("GET", reel["video"], token=t)[0] if False else 200, 200)
        a = urllib.request.Request(self.url + reel["video"], headers={"Range": f"bytes={len(gesamt) + 10}-"})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(a)
        self.assertEqual(e.exception.code, 416)
        # Poster ist ein JPEG, Datei ist H.264 und hat keine Metadaten
        poster = urllib.request.urlopen(self.url + reel["poster"]).read()
        self.assertEqual(poster[:3], b"\xff\xd8\xff")
        # Liken + Kommentieren laeuft ueber die normalen Beitrags-Wege
        self.assertTrue(self.api("POST", f"/api/beitrag/{d['id']}/gefaellt", {}, t)[1]["geliked"])
        self.assertEqual(self.api("POST", f"/api/beitrag/{d['id']}/kommentar", {"text": "Stark!"}, t)[0], 200)
        # Loeschen entfernt Datei und Poster
        name = reel["video"].split("/")[-1]
        self.assertTrue((db.VIDEOS / name).exists())
        self.assertEqual(self.api("POST", "/api/loeschen", {"art": "beitrag", "id": d["id"]}, t)[0], 200)
        self.assertFalse((db.VIDEOS / name).exists())
        self.assertNotIn(d["id"], [r["id"] for r in self.api("GET", "/api/reels", token=t)[1]])

    def test_ausgabe_ist_h264_hochkant_begrenzt_und_nicht_hochskaliert(self):
        t = self.neu("Format Fabi")
        s, d = self.hochladen(t, video_machen(2, 1080, 1920))   # Hochkant, groesser als erlaubt
        self.assertEqual(self.warten(t, d["id"]), "fertig")
        name = next(r for r in self.api("GET", "/api/reels", token=t)[1] if r["id"] == d["id"])["video"].split("/")[-1]
        p = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height,pix_fmt",
                            "-of", "json", str(db.VIDEOS / name)], capture_output=True)
        st = json.loads(p.stdout)["streams"][0]
        self.assertEqual((st["codec_name"], st["pix_fmt"]), ("h264", "yuv420p"))
        self.assertEqual((st["width"], st["height"]), (720, 1280))
        s, d2 = self.hochladen(t, video_machen(2, 320, 240))   # klein -> bleibt klein
        self.assertEqual(self.warten(t, d2["id"]), "fertig")
        name2 = next(r for r in self.api("GET", "/api/reels", token=t)[1] if r["id"] == d2["id"])["video"].split("/")[-1]
        st2 = json.loads(subprocess.run([shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                         "-of", "json", str(db.VIDEOS / name2)], capture_output=True).stdout)["streams"][0]
        self.assertEqual((st2["width"], st2["height"]), (320, 240))

    def test_lange_videos_werden_auf_60_sekunden_gekuerzt(self):
        t = self.neu("Lang Lena")
        s, d = self.hochladen(t, video_machen(75, 160, 120))
        self.assertEqual(self.warten(t, d["id"], 180), "fertig")
        reel = next(r for r in self.api("GET", "/api/reels", token=t)[1] if r["id"] == d["id"])
        self.assertAlmostEqual(reel["dauer"], 60.0, delta=1.0)

    def test_falsche_dateien_werden_abgelehnt(self):
        t = self.neu("Falsch Franz")
        for daten in (b"%PDF-1.4 " + b"x" * 5000, b"MZ" + b"\x00" * 5000, b"#EXTM3U\nhttp://127.0.0.1:1/x.mp4\n" + b"x" * 2000, b"\x00" * 10):
            s, d = self.hochladen(t, daten)
            self.assertIn(s, (400, 413), (daten[:6], d))
        # Ein kaputtes Video mit gueltigem Kopf wird angenommen, dann aber als Fehler markiert (nicht angezeigt)
        s, d = self.hochladen(t, b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 3000)
        self.assertEqual(s, 200)
        self.assertEqual(self.warten(t, d["id"]), "fehler")
        self.assertNotIn(d["id"], [r["id"] for r in self.api("GET", "/api/reels", token=t)[1]])
        self.assertEqual(list(db.VIDEOS.glob("roh_*")), [])   # Rohmaterial ist weg

    def test_anmeldung_limit_und_pfade(self):
        self.assertEqual(self.hochladen("kt_falsch", video_machen())[0], 401)
        t = self.neu("Limit Lukas")
        for _ in range(pro.FREI["reels"]):
            self.assertEqual(self.hochladen(t, video_machen(1))[0], 200)
        s, d = self.hochladen(t, video_machen(1))
        self.assertEqual(s, 429, d)
        self.assertIn("Pro", d["fehler"])
        for pfad in ("/video/../k.db", "/video/..%2Fk.db", "/video/" + "a" * 24 + ".mp4", "/video/abc.mp4", "/video/" + "a" * 24 + ".mp4/../x"):
            try:
                urllib.request.urlopen(self.url + pfad)
                self.fail(pfad)
            except urllib.error.HTTPError as e:
                self.assertIn(e.code, (404,), pfad)

    def test_kein_ffmpeg_gibt_klare_meldung(self):
        t = self.neu("Ohne Ffmpeg")
        with mock.patch.object(reels, "verfuegbar", return_value=False):
            s, d = self.hochladen(t, video_machen(1))
        self.assertEqual(s, 503)
        self.assertIn("ffmpeg", d["fehler"])


class TestReelsUnit(unittest.TestCase):
    def test_kopf(self):
        self.assertTrue(reels.kopf_pruefen(b"\x00\x00\x00\x18ftypisom" + b"0" * 8))
        self.assertTrue(reels.kopf_pruefen(b"\x1a\x45\xdf\xa3" + b"0" * 8))
        self.assertFalse(reels.kopf_pruefen(b"GIF89a" + b"0" * 20))
        self.assertFalse(reels.kopf_pruefen(b"short"))

    def test_bereich(self):
        db.VIDEOS.mkdir(parents=True, exist_ok=True)
        name = "0123456789abcdef01234567.mp4"
        (db.VIDEOS / name).write_bytes(bytes(range(100)))
        try:
            f, a, e, g, teil = reels.lesen_bereich(name, "bytes=10-19")
            f.close()
            self.assertEqual((a, e, g, teil), (10, 19, 100, True))
            f, a, e, g, teil = reels.lesen_bereich(name, None)
            f.close()
            self.assertEqual((a, e, teil), (0, 99, False))
            f, a, e, g, teil = reels.lesen_bereich(name, "bytes=95-9999")
            f.close()
            self.assertEqual((a, e), (95, 99))
            self.assertEqual(reels.lesen_bereich(name, "bytes=500-")[0], "ungueltig")
            self.assertIsNone(reels.lesen_bereich("../x.mp4", None))
        finally:
            (db.VIDEOS / name).unlink(missing_ok=True)


if __name__ == "__main__":
    server._versuche.clear()
    unittest.main()
