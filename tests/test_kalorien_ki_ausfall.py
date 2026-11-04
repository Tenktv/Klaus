"""KI kurz ueberlastet (503): erst nochmal, dann Ersatzmodell - aber nur beim Server-Schluessel."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kalorien import ki  # noqa: E402

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
