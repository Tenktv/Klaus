import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import cfd_demo as cfd


class Antwort:
    def __init__(self, code=200, daten=None, kopf=None):
        self.status_code, self._d, self.headers = code, daten or {}, kopf or {}
        self.content = b'x'
        self.text = json.dumps(self._d)

    def json(self):
        return self._d


class FalscherBroker:
    """Spielt die Capital.com-Demo-API nach (nur was Klaus benutzt)."""

    def __init__(self, kurse):
        self.kurse, self.offen, self.aufrufe, self.n = list(kurse), {}, [], 0

    def post(self, url, **kw):
        self.aufrufe.append(('POST', url))
        assert url.startswith(cfd.DEMO)
        return Antwort(200, {}, {'CST': 'c', 'X-SECURITY-TOKEN': 's'})

    def request(self, methode, url, **kw):
        assert url.startswith(cfd.DEMO), url
        pfad = url[len(cfd.DEMO):]
        self.aufrufe.append((methode, pfad, kw.get('json')))
        if methode == 'GET' and pfad == '/positions':
            return Antwort(200, {'positions': [{'position': {'dealId': d, 'direction': r, 'size': 1, 'level': 1, 'upl': 0},
                                                'market': {'epic': 'GOLD', 'instrumentName': 'Gold'}} for d, r in self.offen.items()]})
        if methode == 'GET' and pfad.startswith('/markets/'):
            return Antwort(200, {'snapshot': {'marketStatus': 'TRADEABLE'}})
        if methode == 'GET' and pfad.startswith('/prices/'):
            return Antwort(200, {'prices': [{'closePrice': {'bid': k, 'ask': k}} for k in self.kurse]})
        if methode == 'POST' and pfad == '/positions':
            self.n += 1
            self.letzte = f'd{self.n}'
            self.offen[self.letzte] = kw['json']['direction']
            return Antwort(200, {'dealReference': f'o_{self.n}'})
        if methode == 'GET' and pfad.startswith('/confirms/'):
            return Antwort(200, {'dealStatus': 'ACCEPTED', 'affectedDeals': [{'dealId': self.letzte}]})
        if methode == 'DELETE' and pfad.startswith('/positions/'):
            self.offen.pop(pfad.split('/')[-1], None)
            return Antwort(200, {'dealReference': 'x'})
        if methode == 'GET' and pfad == '/accounts':
            return Antwort(200, {'accounts': [{'preferred': True, 'currency': 'EUR', 'balance': {'balance': 10000, 'profitLoss': 0, 'available': 9000}}]})
        return Antwort(404, {'fehler': pfad})


class CfdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, wert in (('DATEI', Path(self.tmp.name) / 'cfd.json'),):
            p = patch.object(cfd, name, wert)
            p.start()
            self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'CAPITAL_API_KEY': 'k' * 16, 'CAPITAL_LOGIN': 'a@b.de', 'CAPITAL_PASSWORT': 'x'})
        p.start()
        self.addCleanup(p.stop)
        cfd.S.kopf = {}
        self.meldungen = []

    def broker(self, kurse):
        b = FalscherBroker(kurse)
        for name in ('post', 'request'):
            p = patch.object(cfd.requests, name, getattr(b, name))
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(cfd.time, 'sleep', lambda s: None)
        p.start()
        self.addCleanup(p.stop)
        return b

    def test_nur_demo_adresse_im_modul(self):
        quelle = Path(cfd.__file__).read_text(encoding='utf-8')
        self.assertIn('demo-api-capital', cfd.DEMO)
        self.assertNotIn('://api-capital', quelle)

    def test_signale(self):
        auf = np.linspace(100, 200, 120)
        self.assertEqual(cfd.signale('trend', auf, {'kurz': 5, 'lang': 20})[-1], 1)
        self.assertEqual(cfd.signale('trend', auf[::-1], {'kurz': 5, 'lang': 20})[-1], -1)
        self.assertEqual(cfd.signale('trend', auf[::-1], {'kurz': 5, 'lang': 20}, 'long')[-1], 0)
        self.assertEqual(cfd.signale('ausbruch', np.r_[np.full(30, 100.0), 110.0], {'fenster': 20})[-1], 1)
        r = cfd.backtest('trend', np.r_[np.linspace(100, 150, 80), np.linspace(150, 90, 80)], {'kurz': 5, 'lang': 20}, 'beide', 3, 6)
        self.assertGreater(r['trades'], 0)

    def test_autonom_long_dann_short(self):
        b = self.broker(np.linspace(100, 200, 300))
        cfd.anlegen('trend', 'GOLD', {'kurz': 5, 'lang': 20}, 1, sl_proz=2, tp_proz=4)
        cfd.runde(self.meldungen.append)
        self.assertEqual(list(b.offen.values()), ['BUY'])
        auftrag = [a for a in b.aufrufe if a[0] == 'POST' and len(a) > 2 and a[2]][0][2]
        self.assertGreater(auftrag['stopDistance'], 0)
        self.assertGreater(auftrag['profitDistance'], auftrag['stopDistance'])
        cfd.runde(self.meldungen.append)                      # gleiches Signal: nichts Neues
        self.assertEqual(b.n, 1)
        b.kurse = list(np.linspace(200, 100, 300))            # Trend dreht
        cfd.runde(self.meldungen.append)
        self.assertEqual(list(b.offen.values()), ['SELL'])
        self.assertTrue(any('SHORT' in m for m in self.meldungen))

    def test_nach_stop_nicht_sofort_wieder_rein(self):
        b = self.broker(np.linspace(100, 200, 300))
        cfd.anlegen('trend', 'GOLD', {'kurz': 5, 'lang': 20}, 1)
        cfd.runde(self.meldungen.append)
        b.offen.clear()                                       # Broker schliesst per Stop-Loss
        cfd.runde(self.meldungen.append)
        self.assertEqual(b.n, 1)
        self.assertTrue(any('Stop-Loss' in m for m in self.meldungen))

    def test_stop_und_schliessen(self):
        b = self.broker(np.linspace(100, 200, 300))
        cfd.anlegen('trend', 'GOLD', {'kurz': 5, 'lang': 20}, 1)
        cfd.runde(self.meldungen.append)
        self.assertIn('angehalten', cfd.alle_stoppen())
        cfd.runde(self.meldungen.append)
        self.assertEqual(b.n, 1)
        self.assertIn('1 Demo-Position', cfd.alles_schliessen())
        self.assertEqual(b.offen, {})

    def test_schluessel_befehl(self):
        gespeichert = {}
        self.assertIn('So:', cfd.schluessel_setzen('/cfd_schluessel abc', gespeichert.__setitem__))
        self.broker([100.0] * 50)
        r = cfd.schluessel_setzen('/cfd_schluessel ABCDEFGH12345678 a@b.de geheim', gespeichert.__setitem__)
        self.assertIn('verbunden', r)
        self.assertEqual(gespeichert['CAPITAL_LOGIN'], 'a@b.de')


if __name__ == '__main__':
    unittest.main()
