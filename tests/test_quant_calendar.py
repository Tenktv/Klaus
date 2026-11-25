"""Boersenkalender: Handelstage, Feiertage, verkuerzte Tage, Handelszeiten, unterschiedliche Boersen."""
import datetime as dt
import unittest

import pandas as pd

from tests import _quant_helpers  # noqa: F401  (sys.path)
from quant.calendar import CalendarError, MarketCalendar


class TestKalender(unittest.TestCase):
    def setUp(self):
        self.nyse, self.xetra, self.lse, self.tse, self.crypto = (MarketCalendar(n) for n in ("NYSE", "XETRA", "LSE", "TSE", "CRYPTO"))

    def test_nyse_feiertage_und_wochenenden(self):
        for tag in ("2024-11-28", "2024-12-25", "2024-07-04", "2024-11-30", "2024-12-01"):    # Thanksgiving, Weihnachten, 4. Juli, Sa, So
            self.assertFalse(self.nyse.is_session(tag), tag)
        self.assertTrue(self.nyse.is_session("2024-11-29"))
        self.assertEqual(self.nyse.holidays("2024-11-01", "2024-11-30"), [pd.Timestamp("2024-11-28")])

    def test_verkuerzte_handelstage(self):
        self.assertTrue(self.nyse.is_early_close("2024-11-29"))            # Tag nach Thanksgiving
        self.assertTrue(self.nyse.is_early_close("2024-12-24"))
        self.assertFalse(self.nyse.is_early_close("2024-11-27"))
        self.assertEqual(self.nyse.local_hours("2024-11-29"), (dt.time(9, 30), dt.time(13, 0)))
        self.assertEqual(self.nyse.local_hours("2024-11-27"), (dt.time(9, 30), dt.time(16, 0)))
        self.assertEqual(self.nyse.hours("2024-11-29")[1], pd.Timestamp("2024-11-29 18:00", tz="UTC"))    # 13:00 EST = 18:00 UTC

    def test_unterschiedliche_boersen_haben_unterschiedliche_kalender_und_zeiten(self):
        self.assertTrue(self.nyse.is_session("2024-12-24") and not self.xetra.is_session("2024-12-24"))    # Xetra geschlossen
        self.assertTrue(self.nyse.is_session("2024-08-26") and not self.lse.is_session("2024-08-26"))      # UK Bank Holiday
        self.assertFalse(self.tse.is_session("2024-05-03"))                                                # Golden Week
        self.assertEqual(self.xetra.local_hours("2024-06-03"), (dt.time(9, 0), dt.time(17, 30)))
        self.assertEqual(self.lse.local_hours("2024-06-03"), (dt.time(8, 0), dt.time(16, 30)))
        self.assertEqual(self.tse.local_hours("2024-06-03"), (dt.time(9, 0), dt.time(15, 0)))
        self.assertEqual(self.nyse.timezone, "America/New_York")
        self.assertEqual(self.xetra.timezone, "Europe/Berlin")

    def test_krypto_24_7(self):
        self.assertTrue(self.crypto.is_session("2024-12-25") and self.crypto.is_session("2024-11-30"))
        self.assertEqual(self.crypto.hours("2024-11-30"), (pd.Timestamp("2024-11-30", tz="UTC"), pd.Timestamp("2024-12-01", tz="UTC")))
        self.assertEqual(self.crypto.holidays("2024-01-01", "2024-12-31"), [])

    def test_naechster_und_vorheriger_handelstag_sessions_zaehlen(self):
        self.assertEqual(self.nyse.next_session("2024-11-01"), pd.Timestamp("2024-11-04"))      # Freitag -> Montag
        self.assertEqual(self.nyse.previous_session("2024-11-29"), pd.Timestamp("2024-11-27"))  # Thanksgiving uebersprungen
        self.assertEqual(self.nyse.sessions_between("2024-11-26", "2024-11-29"), 2)             # 27. und 29.
        self.assertEqual(self.nyse.sessions_between("2024-11-29", "2024-11-29"), 0)
        s = self.nyse.sessions("2024-11-25", "2024-11-29")
        self.assertEqual([str(d.date()) for d in s], ["2024-11-25", "2024-11-26", "2024-11-27", "2024-11-29"])

    def test_fehler(self):
        with self.assertRaises(CalendarError):
            MarketCalendar("MARS")
        with self.assertRaises(CalendarError):
            self.nyse.is_session("1990-01-02")                        # ausserhalb des Kalenderbereichs
        with self.assertRaises(CalendarError):
            self.nyse.hours("2024-11-28")                             # kein Handelstag


if __name__ == "__main__":
    unittest.main()
