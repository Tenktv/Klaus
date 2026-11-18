"""Klaus startet die Kalorien-App nach einem Update neu - nur wenn veraltet und nur unter systemd."""
import os
import signal
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import kalorien_klaus as K  # noqa: E402


class TestNeustart(unittest.TestCase):
    def patches(self, pids, systemd=True, prozess_start=1000.0, code=2000.0):
        ps = [mock.patch.object(K, "_app_prozesse", return_value=pids), mock.patch.object(K, "_unter_systemd", return_value=systemd),
              mock.patch.object(K, "_code_stand", return_value=code),
              mock.patch.object(K.os, "stat", return_value=mock.Mock(st_ctime=prozess_start)), mock.patch.object(K.os, "kill")]
        return ps

    def lauf(self, *args, **kw):
        ps = self.patches(*args)
        mocks = [p.start() for p in ps]
        self.addCleanup(lambda: [p.stop() for p in ps])
        return mocks[-1]   # os.kill

    def test_veraltete_app_wird_beendet(self):
        kill = self.lauf([4711])
        self.assertIn("neu gestartet", K.neu_starten(True))
        kill.assert_called_once_with(4711, signal.SIGTERM)

    def test_aktuelle_app_bleibt(self):
        kill = self.lauf([4711], True, 3000.0, 2000.0)
        self.assertIn("neuesten Code", K.neu_starten(True))
        kill.assert_not_called()

    def test_befehl_startet_auch_aktuelle_app_neu(self):
        kill = self.lauf([4711], True, 3000.0, 2000.0)
        K.neu_starten(False)
        kill.assert_called_once()

    def test_ohne_systemd_wird_nichts_gekillt(self):
        kill = self.lauf([4711], False)
        self.assertIn("systemd", K.neu_starten(True))
        kill.assert_not_called()

    def test_keine_app_laeuft(self):
        kill = self.lauf([])
        with mock.patch.object(K, "_diagnose", return_value="DIAG"):
            self.assertIn("nicht", K.neu_starten(True))
        kill.assert_not_called()

    def test_befehl_ist_angemeldet(self):
        class TG:
            befehle, geheime_befehle = {}, set()
        tg = TG()
        K.befehle_einrichten(tg)
        self.assertIn("/fit_neustart", tg.befehle)

    def test_systemd_erkennung_liest_elternprozess(self):
        mit_init = "123 (python) S 1 123 123 0 -1"
        with mock.patch.object(K.Path, "read_text", return_value=mit_init):
            self.assertTrue(K._unter_systemd(123))
        with mock.patch.object(K.Path, "read_text", return_value="123 (python) S 999 123 123 0 -1"):
            self.assertFalse(K._unter_systemd(123))
        with mock.patch.object(K.Path, "read_text", return_value="123 (py (thon)) S 1 1 1"):
            self.assertTrue(K._unter_systemd(123))   # Klammern im Namen stoeren nicht

    def test_eigener_prozess_wird_nie_gelistet_und_pgrep_fehler_ist_leer(self):
        with mock.patch.object(K.subprocess, "run", side_effect=OSError):
            self.assertEqual(K._app_prozesse(), [])
        with mock.patch.object(K.subprocess, "run", return_value=mock.Mock(stdout=f"{os.getpid()}\n555\n")) as run:
            self.assertEqual(K._app_prozesse(), [555])
        args = run.call_args.args[0]
        self.assertEqual(args[args.index("--") + 1], r"-m kalorien\.server")   # Muster mit fuehrendem "-" nur nach "--"

    def test_pgrep_findet_echten_prozess_mit_dem_muster(self):
        """Echter pgrep-Lauf (wenn vorhanden): ein Prozess mit '-m kalorien.server' in der Kommandozeile wird gefunden."""
        import shutil
        import subprocess
        import time
        if not shutil.which("pgrep"):
            self.skipTest("pgrep fehlt")
        kind = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "-m", "kalorien.server"])
        try:
            time.sleep(0.5)
            self.assertIn(kind.pid, K._app_prozesse())
        finally:
            kind.kill()
            kind.wait()


if __name__ == "__main__":
    unittest.main()


class TestDiagnose(unittest.TestCase):
    def test_diagnose_zeigt_gefundene_prozesse_und_benutzer(self):
        ps = ("USER PID PPID COMMAND\nroot 812 1 /home/klaus/klaus/.venv/bin/python -m kalorien.server\n"
              "klaus 900 1 /usr/bin/python3 src/server_gehirn.py\n")
        with mock.patch.object(K.subprocess, "run", return_value=mock.Mock(stdout=ps)):
            text = K._diagnose()
        self.assertIn("root 812", text)
        self.assertNotIn("server_gehirn", text)

    def test_diagnose_ohne_treffer_und_ohne_ps(self):
        with mock.patch.object(K.subprocess, "run", return_value=mock.Mock(stdout="USER PID PPID COMMAND\n")):
            self.assertIn("Kein Prozess", K._diagnose())
        with mock.patch.object(K.subprocess, "run", side_effect=OSError):
            self.assertIn("nicht lesbar", K._diagnose())

    def test_neustart_ohne_prozess_enthaelt_diagnose(self):
        with mock.patch.object(K, "_app_prozesse", return_value=[]), mock.patch.object(K, "_diagnose", return_value="DIAG"):
            self.assertIn("DIAG", K.neu_starten(True))


class TestGroqSchluesselBefehl(unittest.TestCase):
    KEY = "gsk_" + "A1b2C3d4E5" * 5

    def lauf(self, text, vorher=""):
        gespeichert = {}
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": vorher}), mock.patch.object(K, "neu_starten", return_value="App startet neu.") as neu:
            antwort = K.groq_schluessel_setzen(text, lambda n, w: gespeichert.__setitem__(n, w))
        return antwort, gespeichert, neu

    def test_gueltiger_schluessel_wird_gespeichert_und_nie_zurueckgesendet(self):
        antwort, gespeichert, neu = self.lauf(f"/fit_groq {self.KEY}")
        self.assertEqual(gespeichert, {"GROQ_API_KEY": self.KEY})
        self.assertNotIn(self.KEY, antwort)
        self.assertNotIn("A1b2C3d4E5", antwort)
        neu.assert_called_once_with(False)   # Kalorien-App neu starten, damit sie den Schluessel liest

    def test_falsche_eingaben_speichern_nichts(self):
        for text in ("/fit_groq sk-ant-irgendwas", "/fit_groq gsk_kurz", "/fit_groq gsk_" + "x" * 20 + "!!", "/fit_groq a b c"):
            antwort, gespeichert, neu = self.lauf(text)
            self.assertEqual(gespeichert, {}, text)
            neu.assert_not_called()

    def test_stand_ohne_argument_zeigt_nie_den_wert(self):
        antwort, gespeichert, _ = self.lauf("/fit_groq", vorher=self.KEY)
        self.assertIn("✅", antwort)
        self.assertNotIn(self.KEY, antwort)
        self.assertIn("nicht eingetragen", self.lauf("/fit_groq", vorher="")[0])
        self.assertEqual(gespeichert, {})

    def test_weg_loescht_den_schluessel(self):
        antwort, gespeichert, neu = self.lauf("/fit_groq weg", vorher=self.KEY)
        self.assertEqual(gespeichert, {"GROQ_API_KEY": ""})
        neu.assert_called_once()

    def test_befehl_ist_geheim_und_nur_mit_env_setzen_angemeldet(self):
        class TG:
            def __init__(self):
                self.befehle, self.geheime_befehle = {}, set()
        ohne, mit = TG(), TG()
        K.befehle_einrichten(ohne)
        K.befehle_einrichten(mit, lambda n, w: None)
        self.assertNotIn("/fit_groq", ohne.befehle)
        self.assertIn("/fit_groq", mit.befehle)
        self.assertIn("/fit_groq", mit.geheime_befehle)   # Nachricht wird im Chat geloescht


class TestKiTestBefehl(unittest.TestCase):
    def lauf(self, gemini_key="k", groq_key="g" * 20, chat=None):
        from kalorien import ki
        with mock.patch.object(ki, "schluessel", return_value=gemini_key), mock.patch.dict(os.environ, {"GROQ_API_KEY": groq_key}), \
                mock.patch.object(ki, "chat", side_effect=chat or (lambda *a, **k: '{"ok": true}')) as c:
            return K.ki_test(), c

    def test_zeigt_alle_drei_proben_mit_zeit(self):
        text, c = self.lauf()
        self.assertEqual(c.call_count, 3)               # Gemini Haupt, Gemini Ersatz, Groq
        self.assertEqual(text.count("✅"), 3)
        self.assertIn("Groq", text)

    def test_timeout_limit_und_fehlender_schluessel_werden_unterschieden(self):
        from kalorien import ki
        antworten = iter([ki.KiFehler("zu lange", 599), ki.KiFehler("ausgelastet", 429), '{"ok": true}'])

        def chat(*a, **k):
            x = next(antworten)
            if isinstance(x, Exception):
                raise x
            return x
        text, _ = self.lauf(chat=chat)
        self.assertIn("⏱", text)
        self.assertIn("❌", text)
        self.assertIn("✅", text)
        ohne, c = self.lauf(gemini_key="", groq_key="")
        self.assertEqual(ohne.count("kein Schlüssel eingetragen"), 2)
        c.assert_not_called()

    def test_schluessel_tauchen_nie_im_text_auf(self):
        from kalorien import ki
        geheim = "gsk_" + "Z9y8X7w6V5" * 3
        text, _ = self.lauf(gemini_key="AIzaGeheimerGeminiKey123", groq_key=geheim,
                            chat=lambda *a, **k: (_ for _ in ()).throw(RuntimeError(f"kaputt {geheim}")))
        self.assertNotIn(geheim, text)
        self.assertNotIn("AIzaGeheimerGeminiKey123", text)

    def test_befehl_ist_angemeldet(self):
        class TG:
            befehle, geheime_befehle = {}, set()
        tg = TG()
        K.befehle_einrichten(tg)
        self.assertIn("/fit_ki_test", tg.befehle)
