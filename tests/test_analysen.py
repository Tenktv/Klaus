import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import alpaca_handel as al
import analysen as an
import strategien as st

KONTO = {'equity': '10000', 'cash': '2000'}
POSITIONEN = [
    {'symbol': 'NVDA', 'market_value': '4000', 'unrealized_pl': '500', 'unrealized_plpc': '0.142', 'unrealized_intraday_pl': '-80', 'asset_class': 'us_equity'},
    {'symbol': 'AAPL', 'market_value': '2000', 'unrealized_pl': '-100', 'unrealized_plpc': '-0.047', 'unrealized_intraday_pl': '10', 'asset_class': 'us_equity'},
    {'symbol': 'BTCUSD', 'market_value': '2000', 'unrealized_pl': '300', 'unrealized_plpc': '0.176', 'unrealized_intraday_pl': '5', 'asset_class': 'crypto'},
]


@patch.dict(os.environ, {'ALPACA_API_KEY': 'k', 'ALPACA_SECRET_KEY': 's', 'ALPACA_LIVE': ''})
class AnalysenTests(unittest.TestCase):
    def test_kennzahlen(self):
        k = an.depot_kennzahlen(KONTO, POSITIONEN)
        self.assertAlmostEqual(k['bar_anteil'], 0.2)
        self.assertAlmostEqual(k['krypto_anteil'], 0.2)
        self.assertEqual([p['symbol'] for p in k['klumpen']], ['NVDA'])        # 40 % > 25 %
        self.assertAlmostEqual(k['effektiv'], 1 / (0.5 ** 2 + 0.25 ** 2 + 0.25 ** 2))

    def test_depot_analyse_text(self):
        with patch.object(al, 'konto', lambda: KONTO), patch.object(al, 'positionen', lambda: POSITIONEN), \
                patch.object(an, 'depot_verlauf', lambda p: {'proz': 3.0, 'max_rueckgang': -4.2, 'anfang': 1, 'ende': 1}), \
                patch.object(an, 'markt_veraenderung', lambda *a: 1.5):
            t = an.depot_analyse()
        for teil in ('Klumpenrisiko: NVDA ist 40 %', 'Krypto-Anteil 20 %', 'Bester: BTCUSD', 'Schwächster: AAPL',
                     'zieht NVDA', 'S&P 500 +1,5 %', 'keine Anlageberatung'):
            self.assertIn(teil, t)

    def test_leeres_depot(self):
        with patch.object(al, 'konto', lambda: KONTO), patch.object(al, 'positionen', lambda: []):
            self.assertIn('keine positionen', an.depot_analyse().lower())

    def test_signale(self):
        fallend = list(np.linspace(200, 100, 300))
        self.assertIn('ueberverkauft', an.signale(fallend)['treffer'])
        self.assertIn('tief', an.signale(fallend)['treffer'])
        steigend = list(np.linspace(100, 200, 300))
        self.assertIn('hoch', an.signale(steigend)['treffer'])
        import markt
        voll = np.concatenate([np.linspace(200, 100, 250), np.linspace(100, 160, 60)])
        kreuz = int(np.argmax(markt._sma(voll, 20)[250:] > markt._sma(voll, 50)[250:])) + 250   # erster Tag SMA20 > SMA50
        self.assertIn('trend_auf', an.signale(list(voll[:kreuz + 3]))['treffer'])      # Kreuz vor 2 Tagen
        self.assertNotIn('trend_auf', an.signale(list(voll[:kreuz + 20]))['treffer'])  # zu lange her

    def test_scanner_text(self):
        erg = {'NVDA': {'rsi': 25.0, 'woche': -6.0, 'treffer': ['ueberverkauft']},
               'BTC-USD': {'rsi': 20.0, 'woche': -9.0, 'treffer': ['ueberverkauft', 'tief']},
               'SPY': {'rsi': 55.0, 'woche': 1.0, 'treffer': []}}
        t = an.scanner_text(erg)
        self.assertLess(t.index('BTC'), t.index('NVDA'))     # tiefster RSI zuerst
        self.assertIn('52-Wochen-Tief', t)
        self.assertIn('Gerade keine', an.scanner_text({'SPY': erg['SPY']}))
        self.assertIn('Scanner-Arten', an.scanner_text(erg, 'quatsch'))

    def test_faellig_freitags_nach_boersenschluss_einmal(self):
        fr = dt.datetime(2026, 10, 16, 22, 45)            # Freitag
        woche = f"{fr.isocalendar()[0]}-{fr.isocalendar()[1]}"
        self.assertTrue(an.faellig(fr, ''))
        self.assertFalse(an.faellig(fr, woche))
        self.assertFalse(an.faellig(dt.datetime(2026, 10, 16, 21, 0), ''))
        self.assertFalse(an.faellig(dt.datetime(2026, 10, 15, 23, 0), ''))

    def test_wochenbericht(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        heute = dt.date.today().isoformat()
        s = {'id': 'a1', 'titel': 'NVDA trend', 'aktiv': True, 'symbol': 'NVDA', 'stueck': 2.0, 'einstand': 100.0, 'realisiert': 55.0,
             'historie': [{'datum': heute, 'seite': 'sell', 'menge': 1, 'preis': 130, 'gewinn': 30.0},
                          {'datum': '2000-01-01', 'seite': 'sell', 'menge': 1, 'preis': 125, 'gewinn': 25.0}]}
        with patch.object(st, 'DATEI', Path(tmp.name) / 's.json'):
            st.speichern({'strategien': [s], 'live_gewarnt': ''})
            with patch.object(an, 'depot_verlauf', lambda p: {'proz': 2.0, 'anfang': 10000, 'ende': 10200, 'max_rueckgang': -1}), \
                    patch.object(an, 'markt_veraenderung', lambda *a: 1.0), patch.object(al, 'kurs', lambda sym: 110.0), \
                    patch.object(an, 'scan', lambda: {'AMD': {'rsi': 25, 'woche': -5, 'treffer': ['ueberverkauft']}}):
                t = an.wochenbericht()
        for teil in ('Woche +2,0 %', 'besser als der Markt', '1 Trade,', 'realisiert +30 $', 'gesamt +55 $', 'offen +20 $', 'AMD'):
            self.assertIn(teil, t)


if __name__ == '__main__':
    unittest.main()
