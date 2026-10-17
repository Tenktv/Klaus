import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import alpaca_handel as al
import freigabe


def falsche_api(konto=None, positionen=None, asset=True, preis=100.0):
    """Ersetzt _api: liefert feste Antworten und merkt sich gesendete Orders."""
    gesendet = []

    def api(methode, pfad, basis=None, **kw):
        if pfad.startswith('/v2/assets/'):
            return {'symbol': 'BTC/USD' if 'BTCUSD' in pfad else pfad.rsplit('/', 1)[1], 'tradable': True} if asset else None
        if pfad == '/v2/account':
            return konto or {'equity': '10000', 'last_equity': '9900', 'cash': '5000', 'buying_power': '5000'}
        if pfad.startswith('/v2/positions/'):
            return (positionen or {}).get(pfad.rsplit('/', 1)[1])
        if pfad == '/v2/positions':
            return []
        if pfad == '/v2/orders' and methode == 'GET':
            return [{'id': 'abcdef12-3456', 'symbol': 'NVDA', 'side': 'buy', 'qty': '1', 'status': 'new'}]
        if 'latest/trades' in pfad or 'trades/latest' in pfad:
            return {'trade': {'p': preis}, 'trades': {'BTC/USD': {'p': preis}}}
        if pfad == '/v2/orders' and methode == 'POST':
            gesendet.append(kw['json'])
            return {'id': 'neu12345', 'status': 'accepted', 'qty': kw['json'].get('qty'), 'notional': kw['json'].get('notional')}
        if methode == 'DELETE':
            gesendet.append(('storno', pfad))
            return {}
        raise AssertionError(pfad)
    return api, gesendet


def token():
    t = 'test-token'
    freigabe._tokens[t] = (al.ART, __import__('time').time())
    return t


@patch.dict(os.environ, {'ALPACA_API_KEY': 'k', 'ALPACA_SECRET_KEY': 's', 'ALPACA_LIVE': '', 'ALPACA_MAX_ORDER_USD': '1000'})
class AlpacaTests(unittest.TestCase):
    def test_papier_ist_standard(self):
        self.assertFalse(al.live())
        self.assertIn('paper-api', al.TRADING[al.live()])
        with patch.dict(os.environ, {'ALPACA_LIVE': '1'}):
            self.assertTrue(al.live())

    def test_ohne_freigabe_wird_nichts_gesendet(self):
        api, gesendet = falsche_api()
        with patch.object(al, '_api', api):
            auftrag = al.vorbereiten('kaufen', 'NVDA', stueck=2)
            with self.assertRaises(PermissionError):
                al.ausfuehren(None, auftrag)
            with self.assertRaises(PermissionError):
                al.ausfuehren('erfunden', auftrag)
        self.assertEqual(gesendet, [])

    def test_kauf_mit_freigabe(self):
        api, gesendet = falsche_api()
        with patch.object(al, '_api', api):
            auftrag = al.vorbereiten('kaufen', 'NVDA', stueck=2)
            self.assertIn('Papier-Konto', auftrag.text)
            text = al.ausfuehren(token(), auftrag)
        self.assertEqual(gesendet[0]['side'], 'buy')
        self.assertEqual(gesendet[0]['qty'], '2')
        self.assertEqual(gesendet[0]['type'], 'market')
        self.assertIn('Papier', text)

    def test_papier_direkt_ohne_freigabe_echtgeld_nie(self):
        api, gesendet = falsche_api()
        with patch.object(al, '_api', api):
            auftrag = al.vorbereiten('kaufen', 'NVDA', stueck=1)
            self.assertIn('Papier', al.papier_direkt(auftrag))
            self.assertIn('storniert', al.papier_direkt(al.vorbereiten('stornieren', order_nr='abcdef12')))
            with patch.dict(os.environ, {'ALPACA_LIVE': '1'}):
                with self.assertRaises(al.HandelFehler):
                    al.papier_direkt(al.vorbereiten('kaufen', 'NVDA', stueck=1))
            auftrag_alt = al.vorbereiten('kaufen', 'NVDA', stueck=1)
            with patch.dict(os.environ, {'ALPACA_LIVE': '1'}), self.assertRaises(al.HandelFehler):
                al.papier_direkt(auftrag_alt)          # vor dem Umschalten vorbereitet: trotzdem nicht
        self.assertEqual(len(gesendet), 2)

    def test_token_nur_einmal(self):
        api, gesendet = falsche_api()
        with patch.object(al, '_api', api):
            auftrag = al.vorbereiten('kaufen', 'NVDA', stueck=1)
            t = token()
            al.ausfuehren(t, auftrag)
            with self.assertRaises(PermissionError):
                al.ausfuehren(t, auftrag)
        self.assertEqual(len(gesendet), 1)

    def test_grenze_je_order(self):
        api, _ = falsche_api(preis=600.0)
        with patch.object(al, '_api', api), self.assertRaises(al.HandelFehler):
            al.vorbereiten('kaufen', 'NVDA', stueck=2)

    def test_ohne_grenze_nur_kaufkraft(self):
        api, _ = falsche_api(preis=600.0)
        with patch.dict(os.environ, {'ALPACA_MAX_ORDER_USD': ''}), patch.object(al, '_api', api):
            self.assertIsNone(al.max_order_usd())
            self.assertEqual(al.vorbereiten('kaufen', 'NVDA', stueck=8).stueck, 8)   # 4.800 $ ohne Grenze ok
            with self.assertRaises(al.HandelFehler):
                al.vorbereiten('kaufen', 'NVDA', stueck=9)                           # 5.400 $ > Kaufkraft 5.000 $

    def test_50k_mit_hebel(self):
        api, _ = falsche_api(konto={'equity': '100000', 'last_equity': '100000', 'cash': '100000', 'buying_power': '200000'})
        with patch.dict(os.environ, {'ALPACA_MAX_ORDER_USD': ''}), patch.object(al, '_api', api):
            self.assertEqual(al.vorbereiten('kaufen', 'NVDA', betrag_usd=50000).betrag_usd, 50000)
            self.assertEqual(al.vorbereiten('kaufen', 'NVDA', betrag_usd=150000).betrag_usd, 150000)   # 1,5x mit Margin
            with self.assertRaises(al.HandelFehler):
                al.vorbereiten('kaufen', 'NVDA', betrag_usd=250000)                                      # ueber Kaufkraft

    def test_hebel_setzen_nur_papier(self):
        aufrufe = []

        def api(methode, pfad, **kw):
            aufrufe.append((methode, pfad, kw.get('json')))
            return {'equity': '100000', 'buying_power': '200000'}
        with patch.object(al, '_api', api):
            self.assertIn('2x', al.hebel_setzen(2))
            self.assertIn('nur 1-, 2- oder 4-fach', al.hebel_setzen(10))
            with patch.dict(os.environ, {'ALPACA_LIVE': '1'}):
                self.assertIn('selbst', al.hebel_setzen(4))
        self.assertEqual([a for a in aufrufe if a[0] == 'PATCH'],
                         [('PATCH', '/v2/account/configurations', {'max_margin_multiplier': '2'})])

    def test_kein_leerverkauf(self):
        api, _ = falsche_api()
        with patch.object(al, '_api', api), self.assertRaises(al.HandelFehler):
            al.vorbereiten('verkaufen', 'NVDA', stueck=1)
        api, _ = falsche_api(positionen={'NVDA': {'qty': '1', 'qty_available': '1'}})
        with patch.object(al, '_api', api), self.assertRaises(al.HandelFehler):
            al.vorbereiten('verkaufen', 'NVDA', stueck=3)
        with patch.object(al, '_api', api):
            self.assertEqual(al.vorbereiten('verkaufen', 'NVDA', stueck=1).seite, 'sell')

    def test_moduswechsel_nach_freigabe_blockiert(self):
        api, gesendet = falsche_api()
        with patch.object(al, '_api', api):
            auftrag = al.vorbereiten('kaufen', 'NVDA', stueck=1)
            with patch.dict(os.environ, {'ALPACA_LIVE': '1'}), self.assertRaises(al.HandelFehler):
                al.ausfuehren(token(), auftrag)
        self.assertEqual(gesendet, [])

    def test_live_warnt_deutlich(self):
        api, _ = falsche_api()
        with patch.dict(os.environ, {'ALPACA_LIVE': '1'}), patch.object(al, '_api', api):
            self.assertIn('ECHTGELD', al.vorbereiten('kaufen', 'NVDA', stueck=1).text)

    def test_limit_mit_betrag_wird_ganze_stuecke(self):
        api, _ = falsche_api()
        with patch.object(al, '_api', api):
            auftrag = al.vorbereiten('kaufen', 'NVDA', betrag_usd=450, limit=100)
        self.assertEqual(auftrag.stueck, 4)
        self.assertEqual(auftrag.daten()['type'], 'limit')
        self.assertNotIn('notional', auftrag.daten())

    def test_krypto(self):
        api, _ = falsche_api()
        with patch.object(al, '_api', api):
            auftrag = al.vorbereiten('kaufen', 'Bitcoin', betrag_usd=50)
        self.assertEqual(auftrag.symbol, 'BTC/USD')
        self.assertEqual(auftrag.daten()['time_in_force'], 'gtc')
        self.assertEqual(auftrag.daten()['notional'], '50.00')

    def test_storno_braucht_eindeutige_nummer(self):
        api, gesendet = falsche_api()
        with patch.object(al, '_api', api):
            with self.assertRaises(al.HandelFehler):
                al.vorbereiten('stornieren', order_nr='ffffff')
            auftrag = al.vorbereiten('stornieren', order_nr='abcdef12')
            al.ausfuehren(token(), auftrag)
        self.assertEqual(gesendet, [('storno', '/v2/orders/abcdef12-3456')])

    def test_ungueltige_eingaben(self):
        api, _ = falsche_api()
        with patch.object(al, '_api', api):
            for kw in ({}, {'stueck': 1, 'betrag_usd': 10}, {'stueck': -1}):
                with self.assertRaises(al.HandelFehler):
                    al.vorbereiten('kaufen', 'NVDA', **kw)
            with self.assertRaises(al.HandelFehler):
                al.vorbereiten('halten', 'NVDA', stueck=1)

    def test_ohne_schluessel_klare_meldung(self):
        with patch.dict(os.environ, {'ALPACA_API_KEY': ''}):
            with self.assertRaises(al.HandelFehler) as f:
                al.konto_text()
        self.assertIn('ALPACA_API_KEY', str(f.exception))

    def test_schluessel_per_telegram_nur_papier_und_geprueft(self):
        gespeichert = {}
        speichern = gespeichert.__setitem__
        paper, secret = 'PK' + 'A1' * 9, 'x' * 40
        self.assertIn('So:', al.schluessel_setzen('/alpaca_schluessel nurEins', speichern))
        self.assertIn('Paper', al.schluessel_setzen(f'/alpaca_schluessel AK{"B2" * 9} {secret}', speichern))
        with patch.dict(os.environ, {'ALPACA_LIVE': '1'}):
            self.assertIn('ALPACA_LIVE=1', al.schluessel_setzen(f'/alpaca_schluessel {paper} {secret}', speichern))
        with patch.object(al.requests, 'get', return_value=type('R', (), {'status_code': 401})()):
            self.assertIn('nichts gespeichert', al.schluessel_setzen(f'/alpaca_schluessel {paper} {secret}', speichern))
        self.assertEqual(gespeichert, {})
        api, _ = falsche_api()
        with patch.object(al.requests, 'get', return_value=type('R', (), {'status_code': 200})()), patch.object(al, '_api', api):
            text = al.schluessel_setzen(f'/alpaca_schluessel {paper} {secret}', speichern)
        self.assertIn('gespeichert', text)
        self.assertEqual(gespeichert, {'ALPACA_API_KEY': paper, 'ALPACA_SECRET_KEY': secret})


if __name__ == '__main__':
    unittest.main()
