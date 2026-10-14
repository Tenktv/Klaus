"""Kontrollzentrum: echte Slots mit Attrappen, ohne Mikrofon, Netz oder zweite App."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
with patch("dotenv.load_dotenv", return_value=False):
    from fenster import WebBruecke
    import freigabe
    import pc_zugriff
    import spiel_coach


class DesignBridgeTests(unittest.TestCase):
    def setUp(self):
        self.a = SimpleNamespace(pausiert=True, ist_stumm=False, protokoll=None, eingabe=lambda text: None)
        self.b = WebBruecke(self.a, lambda: None)

    def tearDown(self):
        WebBruecke.alle.remove(self.b)

    def test_status_idle_and_recording(self):
        with patch("pc_zugriff.status", return_value={"aktiv": False}), patch("spiel_coach.laeuft", return_value=False), patch("freigabe.offen", return_value=False):
            status = json.loads(self.b.ladeBetrieb())
            self.assertTrue(status["mikroAus"])
            self.assertFalse(status["protokoll"]["aktiv"])
            self.a.protokoll = SimpleNamespace(laeuft=True, titel="Seminar", dauer=lambda: 65.7, saetze=[(1, "Text")])
            status = json.loads(self.b.ladeBetrieb())
            self.assertEqual(status["protokoll"], {"aktiv": True, "titel": "Seminar", "sekunden": 65, "zeilen": 1, "gesundheit": {}})

    def test_timer_validation_and_off(self):
        with patch("pc_zugriff.timer", return_value="OK") as timer, patch("fenster.threading.Thread", side_effect=lambda target, **kw: SimpleNamespace(start=target)):
            self.b.pcTimer(-1)
            self.b.pcTimer(241)
            timer.assert_not_called()
            self.b.pcTimer(15)
            timer.assert_called_with(15)
            self.b.pcTimer(0)
            timer.assert_called_with(None)

    def test_commands_use_existing_queue(self):
        with patch.object(self.a, "eingabe") as queue:
            self.b.eingabe("  ")
            queue.assert_not_called()
            self.b.eingabe("  Kalender heute  ")
            queue.assert_called_once_with("Kalender heute")


if __name__ == "__main__":
    unittest.main()
