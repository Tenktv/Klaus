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


class TestAnfrageKopf(unittest.TestCase):
    def test_eigene_kennung_statt_python_urllib(self):
        gesehen = {}

        class Antwort:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return b"{}"

        def fake(anfrage, timeout=0):
            gesehen["ua"] = anfrage.get_header("User-agent")
            return Antwort()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            ki._post("https://api.groq.com/openai/v1/chat/completions", {"Authorization": "Bearer x"}, {}, 5)
        self.assertEqual(gesehen["ua"], "KlesroFit/1.0")

    def test_schutzdienst_sperre_wird_nicht_als_schluesselfehler_gemeldet(self):
        import io
        import urllib.error
        err = urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO(b"error code: 1010"))
        with mock.patch("urllib.request.urlopen", side_effect=err), self.assertRaises(ki.KiFehler) as ctx:
            ki._post("https://api.groq.com/x", {}, {}, 5)
        self.assertIn("Schutzdienst", str(ctx.exception))
        self.assertNotIn("Schlüssel abgelehnt", str(ctx.exception))

    def test_echter_schluesselfehler_bleibt_schluesselfehler(self):
        import io
        import urllib.error
        body = b'{"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}'
        err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(body))
        with mock.patch("urllib.request.urlopen", side_effect=err), self.assertRaises(ki.KiFehler) as ctx:
            ki._post("https://api.groq.com/x", {}, {}, 5)
        self.assertIn("Schlüssel", str(ctx.exception))


class TestFotoMitTextModell(unittest.TestCase):
    def test_eigene_ki_400_beim_foto_gibt_klare_modell_meldung(self):
        konfig = {"anbieter": "groq", "schluessel": "g" * 20, "modell": "openai/gpt-oss-120b"}
        with mock.patch.object(ki, "_post", side_effect=ki.KiFehler("Der KI-Anbieter antwortet gerade nicht (400).", 400)), \
                self.assertRaises(ki.KiFehler) as ctx:
            ki.aus_bild(b"\xff\xd8\xff" + b"0" * 2000, "image/jpeg", konfig=konfig)
        self.assertIn("keine Fotos", str(ctx.exception))
        self.assertIn("qwen3.8-27b", str(ctx.exception))

    def test_text_mit_400_bleibt_unveraendert(self):
        konfig = {"anbieter": "groq", "schluessel": "g" * 20, "modell": "openai/gpt-oss-120b"}
        with mock.patch.object(ki, "_post", side_effect=ki.KiFehler("Der KI-Anbieter antwortet gerade nicht (400).", 400)), \
                self.assertRaises(ki.KiFehler) as ctx:
            ki.aus_text("Nudeln", konfig=konfig)
        self.assertNotIn("keine Fotos", str(ctx.exception))


class TestGroqModelle(unittest.TestCase):
    def test_standard_je_nach_text_oder_foto(self):
        self.assertEqual(ki.modell_waehlen("groq", "", False), "openai/gpt-oss-120b")
        self.assertEqual(ki.modell_waehlen("groq", "", True), "qwen/qwen3.8-27b")
        self.assertEqual(ki.modell_waehlen("groq", "mein/modell", True), "mein/modell")          # eigene Wahl bleibt
        self.assertEqual(ki.modell_waehlen("gemini", "", True), ki.ANBIETER["gemini"]["modell"])  # ohne eigenen Bild-Standard: normaler Standard

    def test_abgeschaltetes_modell_wird_automatisch_ersetzt(self):
        self.assertEqual(ki.modell_waehlen("groq", "meta-llama/llama-4-scout-17b-16e-instruct", True), "qwen/qwen3.8-27b")
        self.assertEqual(ki.modell_waehlen("groq", "meta-llama/llama-4-scout-17b-16e-instruct", False), "openai/gpt-oss-120b")

    def test_gespeichertes_scout_geht_beim_foto_an_das_neue_bildmodell(self):
        konfig = {"anbieter": "groq", "schluessel": "g" * 20, "modell": "meta-llama/llama-4-scout-17b-16e-instruct"}
        with mock.patch.object(ki, "_post", return_value={"choices": [{"message": {"content": '{"gerichte":[{"name":"Apfel","kcal":95}]}'}}]}) as post:
            ki.aus_bild(b"\xff\xd8\xff" + b"0" * 2000, "image/jpeg", konfig=konfig)
        self.assertEqual(post.call_args.args[2]["model"], "qwen/qwen3.8-27b")

    def test_speichern_ohne_modell_laesst_das_feld_leer(self):
        self.assertEqual(ki.konfig_pruefen("groq", "g" * 20, "")["modell"], "")

    def test_server_groq_nimmt_bild_standard_bei_foto_und_env_ueberschreibt(self):
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "g" * 20, "KALORIEN_GROQ_BILD_MODELL": "x/bild", "KALORIEN_GROQ_MODELL": "x/text"}):
            self.assertEqual(ki.groq_konfig(True)["modell"], "x/bild")
            self.assertEqual(ki.groq_konfig(False)["modell"], "x/text")

    def test_abgeschaltetes_modell_bekommt_klare_meldung(self):
        import io
        import urllib.error
        body = b'{"error":{"message":"The model `x` has been decommissioned and is no longer supported.","code":"model_decommissioned"}}'
        err = urllib.error.HTTPError("u", 400, "Bad Request", {}, io.BytesIO(body))
        with mock.patch("urllib.request.urlopen", side_effect=err), self.assertRaises(ki.KiFehler) as ctx:
            ki._post("https://api.groq.com/x", {}, {}, 5)
        self.assertIn("nicht mehr", str(ctx.exception))
        self.assertEqual(ctx.exception.code, 404)
