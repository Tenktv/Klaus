import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import identitaet as I


class WeckwortUnscharfTests(unittest.TestCase):
    def test_eigener_name_mit_hoerfehlern(self):
        with patch.object(I, 'NAME', 'Lumine'):
            self.assertEqual(I.weckwort_unscharf('Lumine, wie wird das Wetter?'), 'wie wird das Wetter')
            self.assertEqual(I.weckwort_unscharf('Hey Lumina, öffne Steam'), 'öffne Steam')
            self.assertEqual(I.weckwort_unscharf('Lu Mine mach den Chat auf'), 'mach den Chat auf')
            self.assertEqual(I.weckwort_unscharf('Hallo Lumin!'), '')
            self.assertEqual(I.weckwort_unscharf('wie spät ist es Luminé'), 'wie spät ist es')

    def test_kein_fehlalarm(self):
        with patch.object(I, 'NAME', 'Lumine'):
            for t in ('ich gehe jetzt einkaufen', 'Lumen sind eine Einheit', 'Hallo Klaus!', 'das Licht ist an'):
                self.assertIsNone(I.weckwort_unscharf(t), t)

    def test_klaus_und_kurze_namen_bleiben_exakt(self):
        with patch.object(I, 'NAME', 'Klaus'):
            self.assertIsNone(I.weckwort_unscharf('Klaas, wie spät'))
        with patch.object(I, 'NAME', 'Mia'):
            self.assertIsNone(I.weckwort_unscharf('mir ist kalt'))


if __name__ == '__main__':
    unittest.main()
