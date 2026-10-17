import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import alpaca_handel as al
import freigabe
import strategien as st


def token():
    t = 'tok-' + str(time.time())
    freigabe._tokens[t] = (st.ART, time.time())
    return t


def tage(n):
    return [f"d{i}" for i in range(n)]


AUF = np.linspace(100, 200, 300)                                     # stetig steigend
AB_AUF = np.concatenate([np.linspace(200, 100, 150), np.linspace(100, 220, 150)])


@patch.dict(os.environ, {'ALPACA_API_KEY': 'k', 'ALPACA_SECRET_KEY': 's', 'ALPACA_LIVE': '', 'ALPACA_MAX_ORDER_USD': '1000',
                         'STRATEGIE_GESAMT_USD': '5000', 'STRATEGIE_MAX_ORDERS_TAG': '4', 'STRATEGIE_MAX_AKTIV': ''})
class StrategieTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(st, 'DATEI', Path(self.tmp.name) / 'strategien.json')
        p.start()
        self.addCleanup(p.stop)
        self.gesendet, self.orders = [], []
        self.senden = self.gesendet.append

    # ---------------------------------------------------------- Regeln + Backtest
    def test_regeln_pruefen(self):
        self.assertEqual(st.regeln_pruefen('trend', {})['kurz'], 20)
        for typ, p in (('trend', {'kurz': 50, 'lang': 20}), ('rsi', {'unter': 80, 'ueber': 70}), ('sparplan', {'tage': 500}),
                       ('magie', {}), ('trend', {'sl_proz': 95})):
            with self.assertRaises(st.StrategieFehler):
                st.regeln_pruefen(typ, p)

    def test_backtest_trend_steigt_mit(self):
        p = st.regeln_pruefen('trend', {'kurz': 10, 'lang': 30})
        b = st.backtest('trend', 'X', p, 1000, 1000, tage(len(AB_AUF)), AB_AUF)
        self.assertGreater(b['rendite'], 0)
        self.assertGreaterEqual(b['trades'], 1)
        self.assertLessEqual(b['max_verlust'], 0)

    def test_backtest_kein_blick_in_die_zukunft(self):
        # Signal an Tag i darf nicht schon zum Kurs von Tag i kaufen: bei einem Sprung am letzten Tag kein Gewinn daraus
        kurse = np.concatenate([np.full(120, 100.0), [100.0, 300.0]])
        p = st.regeln_pruefen('rsi', {'unter': 30, 'ueber': 70})
        b = st.backtest('rsi', 'X', p, 1000, 1000, tage(len(kurse)), kurse)
        self.assertAlmostEqual(b['rendite'], 0.0, places=6)

    def test_sparplan_respektiert_budget(self):
        p = st.regeln_pruefen('sparplan', {'tage': 5})
        b = st.backtest('sparplan', 'X', p, 100, 500, tage(len(AUF)), AUF)
        self.assertEqual(b['trades'], 5)

    # ---------------------------------------------------------- Anlegen nur mit Freigabe, nur Papier
    def _entwurf(self, **kw):
        with patch.object(al, 'symbol', lambda n: n), patch.object(st, 'tageskurse', lambda s, b='2y': (tage(300), AUF)):
            return st.vorbereiten(kw.get('typ', 'trend'), kw.get('name', 'NVDA'), {}, kw.get('betrag', 500), kw.get('budget'))

    def test_anlegen_ohne_freigabe(self):
        st.anlegen(self._entwurf())
        self.assertTrue(st.laden()['strategien'][0]['aktiv'])

    def test_nie_mit_echtgeld(self):
        with patch.dict(os.environ, {'ALPACA_LIVE': '1'}), self.assertRaises(st.StrategieFehler):
            self._entwurf()
        e = self._entwurf()
        with patch.dict(os.environ, {'ALPACA_LIVE': '1'}), self.assertRaises(st.StrategieFehler):
            st.anlegen(e)
        with patch.dict(os.environ, {'ALPACA_LIVE': '1'}), self.assertRaises(al.HandelFehler):
            al.papier_automatisch(al.Auftrag('buy', 'NVDA', 1))

    def test_grenzen(self):
        with self.assertRaises(st.StrategieFehler):
            self._entwurf(betrag=5000)                      # ueber ALPACA_MAX_ORDER_USD
        st.anlegen(self._entwurf(name='NVDA', betrag=1000, budget=4000))
        with self.assertRaises(st.StrategieFehler):
            self._entwurf(name='NVDA')                      # je Wert nur eine
        with self.assertRaises(st.StrategieFehler):
            self._entwurf(name='AAPL', betrag=1000, budget=2000)   # Gesamtbudget 5000 ueberschritten

    def test_pausieren_fortsetzen_stop(self):
        st.anlegen(self._entwurf())
        sid = st.laden()['strategien'][0]['id']
        st.pausieren(sid)
        self.assertFalse(st.laden()['strategien'][0]['aktiv'])
        with patch.dict(os.environ, {'ALPACA_LIVE': '1'}), self.assertRaises(st.StrategieFehler):
            st.fortsetzen(sid)                          # nie mit Echtgeld
        st.fortsetzen(sid)
        self.assertTrue(st.laden()['strategien'][0]['aktiv'])
        self.assertIn('1', st.befehl('/strategien stop'))
        self.assertFalse(st.laden()['strategien'][0]['aktiv'])

    def test_ohne_env_keine_grenzen(self):
        with patch.dict(os.environ, {'STRATEGIE_GESAMT_USD': '', 'STRATEGIE_MAX_ORDERS_TAG': '', 'ALPACA_MAX_ORDER_USD': ''}):
            self.assertEqual((st.gesamt_usd(), st.max_aktiv(), st.max_orders_tag()), (None, None, None))
            for i, sym in enumerate(['NVDA', 'AAPL', 'MSFT', 'TSLA', 'AMD', 'META', 'SPY']):   # mehr als frueher 5
                st.anlegen(self._entwurf(name=sym, betrag=50000, budget=50000))
            self.assertEqual(len(st.laden()['strategien']), 7)

    # ---------------------------------------------------------- Hintergrund-Schritte
    def _strategie(self, typ='trend', **kw):
        s = {'id': 'abc123', 'titel': 'Test', 'symbol': 'NVDA', 'typ': typ, 'p': st.regeln_pruefen(typ, kw.pop('p', {})),
             'betrag_usd': 500.0, 'budget_usd': 500.0, 'aktiv': True, 'stueck': 0.0, 'investiert': 0.0, 'einstand': 0.0,
             'offen': None, 'gesperrt': False, 'letzte_sparrate': '', 'orders_tag': ['', 0], 'protokoll': []}
        s.update(kw)
        return s

    def _lauf(self, s, kurse, preis=150.0, markt_offen=True):
        def vorbereiten(aktion, name, stueck=None, betrag_usd=None, **k):
            a = al.Auftrag('buy' if aktion == 'kaufen' else 'sell', name, stueck, betrag_usd)
            a.text = f'{aktion} {name}'
            return a

        def papier(auftrag):
            self.orders.append((auftrag.seite, auftrag.stueck, auftrag.betrag_usd))
            return {'id': f'o{len(self.orders)}'}
        with patch.object(st, 'tageskurse', lambda sym, b='1y': (tage(len(kurse)), kurse)), \
                patch.object(al, 'vorbereiten', vorbereiten), patch.object(al, 'papier_automatisch', papier), \
                patch.object(al, 'kurs', lambda sym: preis):
            st.schritt(s, self.senden, markt_offen)

    def test_trend_kauft_bei_signal_und_meldet(self):
        s = self._strategie()
        self._lauf(s, AUF)
        self.assertEqual(self.orders, [('buy', None, 500.0)])
        self.assertEqual(s['offen']['seite'], 'buy')
        self.assertTrue(self.gesendet and 'Kaufsignal' in self.gesendet[0])

    def test_boerse_zu_kein_handel_ausser_krypto(self):
        s = self._strategie()
        self._lauf(s, AUF, markt_offen=False)
        self.assertEqual(self.orders, [])
        s = self._strategie(symbol='BTC/USD')
        self._lauf(s, AUF, markt_offen=False)
        self.assertEqual(len(self.orders), 1)

    def test_verkauf_und_stopp(self):
        s = self._strategie(stueck=3.0, einstand=150.0, investiert=450.0)
        self._lauf(s, AUF[::-1].copy())                  # Trend dreht nach unten
        self.assertEqual(self.orders, [('sell', 3.0, None)])
        self.orders.clear()
        s = self._strategie(p={'sl_proz': 10}, stueck=2.0, einstand=200.0)
        self._lauf(s, AUF, preis=170.0)                  # -15 % -> Stopp, danach gesperrt bis neues Signal
        self.assertEqual(self.orders, [('sell', 2.0, None)])
        self.assertTrue(s['gesperrt'])

    def test_hoechstens_vier_orders_am_tag(self):
        s = self._strategie()
        for _ in range(6):
            s['offen'] = None
            self._lauf(s, AUF)
        self.assertEqual(len(self.orders), 4)

    def test_fehlgeschlagene_order_pausiert_eine_stunde(self):
        s = self._strategie()

        def kaputt(*a, **k):
            raise al.HandelFehler('Nicht genug Kaufkraft')
        with patch.object(st, 'tageskurse', lambda sym, b='1y': (tage(len(AUF)), AUF)), patch.object(al, 'vorbereiten', kaputt):
            st.schritt(s, self.senden, True)
            st.schritt(s, self.senden, True)           # gleich danach: Pause, keine zweite Meldung
        self.assertEqual(len(self.gesendet), 1)
        self.assertIn('in einer Stunde', self.gesendet[0])
        s['pause_bis'] = 0
        self._lauf(s, AUF)
        self.assertEqual(len(self.orders), 1)

    def test_sparplan_takt_und_budget(self):
        s = self._strategie('sparplan', p={'tage': 7}, betrag_usd=100.0, budget_usd=150.0)
        self._lauf(s, AUF)
        s['offen'] = None
        self._lauf(s, AUF)                               # gleicher Tag: keine zweite Rate
        self.assertEqual(self.orders, [('buy', None, 100.0)])
        s.update(letzte_sparrate='2000-01-01', investiert=100.0)
        self._lauf(s, AUF)
        self.assertEqual(self.orders[-1], ('buy', None, 50.0))   # nur noch der Rest des Budgets

    def test_ausgefuehrte_order_wird_verbucht(self):
        s = self._strategie(offen={'id': 'o1', 'seite': 'buy'})
        with patch.object(al, 'order', lambda i: {'status': 'filled', 'filled_qty': '2', 'filled_avg_price': '150'}):
            st._offene_order_abgleichen(s, self.senden)
        self.assertEqual((s['stueck'], s['einstand'], s['offen']), (2.0, 150.0, None))

    def test_pruefen_ruht_bei_echtgeld(self):
        st.anlegen(self._entwurf())
        with patch.dict(os.environ, {'ALPACA_LIVE': '1'}), patch.object(st, 'schritt') as schritt:
            st.pruefen(self.senden)
            st.pruefen(self.senden)
        schritt.assert_not_called()
        self.assertEqual(len(self.gesendet), 1)          # nur eine Warnung am Tag


if __name__ == '__main__':
    unittest.main()
