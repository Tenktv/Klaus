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
        self.assertIn("läuft nicht", K.neu_starten(True))
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
        with mock.patch.object(K.subprocess, "run", return_value=mock.Mock(stdout=f"{os.getpid()}\n555\n")):
            self.assertEqual(K._app_prozesse(), [555])


if __name__ == "__main__":
    unittest.main()
