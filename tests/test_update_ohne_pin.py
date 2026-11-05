"""Update per Telegram ohne Knopf + PIN; die Pruefungen vor dem Uebernehmen bleiben, andere Freigaben bleiben."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import freigabe  # noqa: E402
import selbst_update  # noqa: E402


class TestUpdateOhnePin(unittest.TestCase):
    def test_sofort_einspielen_braucht_keinen_token_und_nutzt_die_gleiche_pruefung(self):
        with mock.patch.object(selbst_update, "_uebernehmen", return_value="Update a → b getestet und übernommen.") as u, \
                mock.patch.object(freigabe, "pruefe") as pruefe:
            self.assertIn("übernommen", selbst_update.sofort_einspielen())
        u.assert_called_once()
        pruefe.assert_not_called()   # kein Freigabe-Token noetig

    def test_der_alte_weg_mit_token_bleibt_geschuetzt(self):
        with self.assertRaises(PermissionError):
            selbst_update.einspielen(None)   # ohne gueltiges Token passiert nichts

    def test_uebernehmen_bricht_bei_lokalen_aenderungen_ab(self):
        def git(*args, frist=120):
            return " M src/x.py" if args[0] == "status" else "abc1234"
        with mock.patch.object(selbst_update, "_git", side_effect=git):
            self.assertIn("lokale Änderungen", selbst_update.sofort_einspielen())

    def test_telegram_update_werkzeug_fragt_nicht_mehr_nach_freigabe(self):
        quelle = (Path(__file__).resolve().parent.parent / "src" / "server_gehirn.py").read_text(encoding="utf-8")
        self.assertIn("selbst_update.sofort_einspielen()", quelle)
        self.assertNotIn('a._mit_freigabe("update"', quelle)


if __name__ == "__main__":
    unittest.main()
