"""KI kurz ueberlastet (503): erst nochmal, dann Ersatzmodell - aber nur beim Server-Schluessel."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kalorien import ki  # noqa: E402

os.environ.pop("GROQ_API_KEY", None)   # die Ausfall-Tests pruefen Gemini allein; Groq-Ersatz hat eigene Tests unten

OK = {"candidates": [{"content": {"parts": [{"text": '{"gerichte":[]}'}]}}]}


def fehler(code):
    return ki.KiFehler(f"x ({code})", code)


class TestKiAusfall(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(ki, "schluessel", return_value="k"), mock.patch.object(ki, "MODELL_ERSATZ", "ersatz-modell"),
                  mock.patch.object(ki.time, "sleep")):
            p.start()
            self.addCleanup(p.stop)

    def modelle(self, post):
        return [c.args[0].split("/models/")[1].split(":")[0] for c in post.call_args_list]

    def test_zweiter_versuch_klappt(self):
        with mock.patch.object(ki, "_post", side_effect=[fehler(503), OK]) as post:
            self.assertEqual(ki.chat("s", "n"), '{"gerichte":[]}')
        self.assertEqual(self.modelle(post), [ki.MODELL, ki.MODELL])

    def test_hauptmodell_dauerhaft_503_dann_ersatzmodell(self):
        with mock.patch.object(ki, "_post", side_effect=[fehler(503), fehler(503), OK]) as post:
            ki.chat("s", "n")
        self.assertEqual(self.modelle(post), [ki.MODELL, ki.MODELL, "ersatz-modell"])

    def test_modell_gibt_es_nicht_springt_gleich_zum_ersatz(self):
        with mock.patch.object(ki, "_post", side_effect=[fehler(404), OK]) as post:
            ki.chat("s", "n")
        self.assertEqual(self.modelle(post), [ki.MODELL, "ersatz-modell"])

    def test_alles_ausgefallen_gibt_klare_meldung(self):
        with mock.patch.object(ki, "_post", side_effect=fehler(503)) as post, self.assertRaises(ki.KiFehler) as ctx:
            ki.chat("s", "n")
        self.assertEqual(ctx.exception.code, 503)
        self.assertEqual(post.call_count, 3)
        self.assertIn("Ersatzmodell", str(ctx.exception))   # so sieht man in der App, dass der neue Code gelaufen ist

    def test_falscher_schluessel_wird_nicht_wiederholt(self):
        with mock.patch.object(ki, "_post", side_effect=fehler(403)) as post, self.assertRaises(ki.KiFehler):
            ki.chat("s", "n")
        self.assertEqual(post.call_count, 1)

    def test_eigene_ki_des_nutzers_bekommt_kein_ersatzmodell(self):
        konfig = {"anbieter": "gemini", "schluessel": "eigener", "modell": "mein-modell"}
        with mock.patch.object(ki, "_post", side_effect=fehler(503)) as post, self.assertRaises(ki.KiFehler):
            ki.chat("s", "n", konfig=konfig)
        self.assertEqual(self.modelle(post), ["mein-modell", "mein-modell"])


if __name__ == "__main__":
    unittest.main()


class TestAntwortLesen(unittest.TestCase):
    def test_abgeschnittene_antwort_behaelt_fertige_gerichte(self):
        text = ('{"gerichte":[{"name":"Brot","menge":"3 Scheiben","kcal":315,"eiweiss":10,"kh":60,"fett":2},'
                '{"name":"Butter","menge":"8 g","kcal":60,"eiweiss":0,"kh":0,"fett":6.6},{"name":"Gurke","menge":"90 g","kc')
        r = ki.lesen(text)
        self.assertEqual([g["name"] for g in r["gerichte"]], ["Brot", "Butter"])
        self.assertIn("unvollständig", r["hinweis"])

    def test_json_mit_text_drumherum(self):
        r = ki.lesen('Klar, hier ist die Schätzung:\n{"gerichte":[{"name":"Apfel","kcal":95}],"hinweis":"ok"}\nGuten Appetit!')
        self.assertEqual(r["gerichte"][0]["name"], "Apfel")

    def test_unlesbar_bleibt_fehler(self):
        with self.assertRaises(ki.KiFehler):
            ki.lesen("Das kann ich leider nicht.")

    def test_unleserlich_wird_einmal_neu_gefragt_und_hat_viel_platz(self):
        gut = '{"gerichte":[{"name":"Brot","kcal":100}]}'
        with mock.patch.object(ki, "schluessel", return_value="k"), mock.patch.object(ki, "chat", side_effect=["kaputt", gut]) as chat:
            self.assertEqual(ki.aus_text("Brot")["gerichte"][0]["name"], "Brot")
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(chat.call_args.kwargs["max_token"], 4096)

    def test_zweimal_unleserlich_gibt_fehler(self):
        with mock.patch.object(ki, "chat", return_value="kaputt") as chat, self.assertRaises(ki.KiFehler):
            ki.aus_text("Brot")
        self.assertEqual(chat.call_count, 2)


class TestLimit(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(ki, "schluessel", return_value="k"), mock.patch.object(ki, "MODELL_ERSATZ", "ersatz-modell"),
                  mock.patch.object(ki.time, "sleep")):
            p.start()
            self.addCleanup(p.stop)

    def test_limit_beim_hauptmodell_geht_gleich_zum_ersatzmodell(self):
        with mock.patch.object(ki, "_post", side_effect=[fehler(429), OK]) as post:
            ki.chat("s", "n")
        self.assertEqual([c.args[0].split("/models/")[1].split(":")[0] for c in post.call_args_list], [ki.MODELL, "ersatz-modell"])

    def test_beide_modelle_am_limit_gibt_freundliche_meldung(self):
        with mock.patch.object(ki, "_post", side_effect=fehler(429)), self.assertRaises(ki.KiFehler) as ctx:
            ki.chat("s", "n")
        self.assertIn("ausgelastet", str(ctx.exception))
        self.assertEqual(ctx.exception.code, 429)

    def test_eigene_ki_behaelt_meldung_des_anbieters_und_probiert_kein_ersatzmodell(self):
        konfig = {"anbieter": "gemini", "schluessel": "eigener", "modell": "mein-modell"}
        with mock.patch.object(ki, "_post", side_effect=ki.KiFehler("Dein KI-Anbieter sagt: Limit erreicht.", 429)) as post, \
                self.assertRaises(ki.KiFehler) as ctx:
            ki.chat("s", "n", konfig=konfig)
        self.assertIn("Limit erreicht", str(ctx.exception))
        self.assertEqual(post.call_count, 1)


class TestGroqErsatz(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(ki, "MODELL_ERSATZ", "ersatz-modell"), mock.patch.object(ki.time, "sleep"),
                  mock.patch.dict(os.environ, {"GROQ_API_KEY": "g" * 20})):
            p.start()
            self.addCleanup(p.stop)

    def test_gemini_am_limit_dann_groq(self):
        def post(url, kopf, daten, timeout):
            if "groq.com" in url:
                return {"choices": [{"message": {"content": '{"gerichte":[{"name":"Brot","kcal":100}]}'}}]}
            raise fehler(429)
        with mock.patch.object(ki, "schluessel", return_value="k"), mock.patch.object(ki, "_post", side_effect=post) as p:
            self.assertEqual(ki.aus_text("Brot")["gerichte"][0]["name"], "Brot")
        urls = [c.args[0] for c in p.call_args_list]
        self.assertIn("groq.com", urls[-1])
        self.assertEqual(p.call_args_list[-1].args[1]["Authorization"], "Bearer " + "g" * 20)
        self.assertEqual(p.call_args_list[-1].args[2]["model"], ki.ANBIETER["groq"]["modell"])

    def test_foto_geht_an_groq_mit_bild(self):
        def post(url, kopf, daten, timeout):
            if "groq.com" in url:
                bild = daten["messages"][1]["content"][1]["image_url"]["url"]
                self.assertTrue(bild.startswith("data:image/jpeg;base64,"))
                return {"choices": [{"message": {"content": '{"gerichte":[{"name":"Apfel","kcal":95}]}'}}]}
            raise fehler(503)
        with mock.patch.object(ki, "schluessel", return_value="k"), mock.patch.object(ki, "_post", side_effect=post):
            self.assertEqual(ki.aus_bild(b"\xff\xd8\xff" + b"0" * 2000, "image/jpeg")["gerichte"][0]["name"], "Apfel")

    def test_ganz_ohne_gemini_schluessel_nur_groq(self):
        with mock.patch.object(ki, "schluessel", return_value=""), mock.patch.object(ki, "_post", return_value={
                "choices": [{"message": {"content": '{"gerichte":[{"name":"Reis","kcal":200}]}'}}]}) as p:
            self.assertTrue(ki.verfuegbar())
            self.assertEqual(ki.aus_text("Reis")["gerichte"][0]["name"], "Reis")
        self.assertIn("groq.com", p.call_args.args[0])

    def test_falscher_gemini_schluessel_geht_nicht_an_groq(self):
        with mock.patch.object(ki, "schluessel", return_value="k"), mock.patch.object(ki, "_post", side_effect=fehler(403)) as p, \
                self.assertRaises(ki.KiFehler):
            ki.chat("s", "n")
        self.assertEqual(p.call_count, 1)

    def test_beides_am_limit_gibt_gemini_meldung(self):
        with mock.patch.object(ki, "schluessel", return_value="k"), mock.patch.object(ki, "_post", side_effect=fehler(429)), \
                self.assertRaises(ki.KiFehler) as ctx:
            ki.chat("s", "n")
        self.assertIn("ausgelastet", str(ctx.exception))

    def test_eigene_ki_nutzt_nie_den_server_groq_schluessel(self):
        konfig = {"anbieter": "gemini", "schluessel": "eigener", "modell": "m"}
        with mock.patch.object(ki, "_post", side_effect=fehler(429)) as p, self.assertRaises(ki.KiFehler):
            ki.chat("s", "n", konfig=konfig)
        self.assertTrue(all("groq.com" not in c.args[0] for c in p.call_args_list))
