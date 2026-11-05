"""Eigene KI: verfuegbare Modelle anzeigen, Modell aendern ohne Schluessel neu einzugeben."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.test_kalorien import Basis  # noqa: E402  (setzt die Test-Datenbank und KALORIEN_ADMINS=chef)
from kalorien import ki  # noqa: E402

GROQ_MODELLE = {"data": [{"id": "meta-llama/llama-4-scout-17b-16e-instruct"}, {"id": "openai/gpt-oss-120b"}, {"id": "whisper-large-v3"},
                         {"id": "playai-tts"}, {"id": "llama-3.3-70b-versatile"}, {"id": "meta-llama/llama-guard-4-12b"}]}


class TestModelleListe(unittest.TestCase):
    def test_groq_liste_filtert_nicht_chat_modelle_und_markiert_bildmodelle(self):
        with mock.patch.object(ki, "_post", return_value=GROQ_MODELLE) as post:
            r = ki.modelle_liste({"anbieter": "groq", "schluessel": "g" * 20})
        self.assertEqual(post.call_args.args[0], "https://api.groq.com/openai/v1/models")
        self.assertIsNone(post.call_args.args[2])   # GET
        ids = [m["id"] for m in r]
        self.assertEqual(ids[0], "meta-llama/llama-4-scout-17b-16e-instruct")   # Bildmodelle zuerst
        self.assertIn("openai/gpt-oss-120b", ids)
        self.assertNotIn("whisper-large-v3", ids)
        self.assertNotIn("playai-tts", ids)
        self.assertNotIn("meta-llama/llama-guard-4-12b", ids)
        self.assertEqual({m["id"]: m["bild"] for m in r}["openai/gpt-oss-120b"], False)

    def test_gemini_liste_nur_chat_faehige(self):
        antwort = {"models": [{"name": "models/gemini-3.5-flash", "supportedGenerationMethods": ["generateContent"]},
                              {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}]}
        with mock.patch.object(ki, "_post", return_value=antwort):
            self.assertEqual([m["id"] for m in ki.modelle_liste({"anbieter": "gemini", "schluessel": "k" * 20})], ["gemini-3.5-flash"])

    def test_get_anfrage_hat_keinen_body(self):
        gesehen = {}

        class Antwort:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return b"{}"

        def fake(anfrage, timeout=0):
            gesehen["data"], gesehen["methode"] = anfrage.data, anfrage.get_method()
            return Antwort()
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            ki._post("https://api.groq.com/openai/v1/models", {}, None, 5)
        self.assertIsNone(gesehen["data"])
        self.assertEqual(gesehen["methode"], "GET")


class TestModelleApi(Basis):
    def chef(self):
        """Admin (= Pro). Der Name ist in tests/test_kalorien.py als Admin eingetragen; Konto beim ersten Mal anlegen, danach anmelden."""
        s, d = self.api("POST", "/api/anmelden", {"name": "Chef", "passwort": "geheim1234"})
        return d["token"] if s == 200 else self.neu("Chef")

    def test_ohne_eigene_ki_klare_meldung(self):
        normal = self.neu("Modell Mia")
        s, d = self.api("GET", "/api/ki/modelle", token=normal)
        self.assertEqual(s, 400)
        self.assertIn("noch keine eigene KI", d["fehler"])

    def test_liste_und_modell_aendern_ohne_schluessel_neu_einzugeben(self):
        boss = self.chef()
        self.api("PUT", "/api/ki", {"anbieter": "groq", "schluessel": "gsk_" + "a" * 40, "modell": "openai/gpt-oss-120b"}, boss)
        with mock.patch.object(ki, "_post", return_value=GROQ_MODELLE):
            s, d = self.api("GET", "/api/ki/modelle", token=boss)
        self.assertEqual(s, 200)
        self.assertEqual(d["modelle"][0]["id"], "meta-llama/llama-4-scout-17b-16e-instruct")
        s, _ = self.api("PUT", "/api/ki", {"anbieter": "groq", "schluessel": "", "modell": "meta-llama/llama-4-scout-17b-16e-instruct"}, boss)
        self.assertEqual(s, 200)
        status = self.api("GET", "/api/ki", token=boss)[1]["eigene"]
        self.assertEqual(status["modell"], "meta-llama/llama-4-scout-17b-16e-instruct")
        self.assertTrue(status["schluessel"].endswith("aaaa"))                    # der alte Schluessel blieb erhalten
        self.assertEqual(self.api("PUT", "/api/ki", {"anbieter": "openai", "schluessel": "", "modell": ""}, boss)[0], 400)   # anderer Anbieter: neuer Schluessel noetig

    def test_anbieterfehler_wird_als_502_gemeldet(self):
        boss = self.chef()
        self.api("PUT", "/api/ki", {"anbieter": "groq", "schluessel": "gsk_" + "b" * 40, "modell": ""}, boss)
        with mock.patch.object(ki, "_post", side_effect=ki.KiFehler("Der Anbieter hat den API-Schlüssel abgelehnt.", 401)):
            s, d = self.api("GET", "/api/ki/modelle", token=boss)
        self.assertEqual(s, 502)
        self.assertIn("abgelehnt", d["fehler"])


if __name__ == "__main__":
    unittest.main()
