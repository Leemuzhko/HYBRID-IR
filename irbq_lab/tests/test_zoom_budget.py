import unittest
import numpy as np
from irbq.dsp import Model
from irbq.zoom_bank import BankProject, Slot, pack_bank
from irbq.zoom_budget import bank_usage, const_bytes


class TestBudget(unittest.TestCase):
    def model(self, n=64, index=0):
        h = np.zeros(n); h[0] = .5; h[1] = .01 * index
        return Model(44100, h, [])

    def test_measured_layout(self):
        self.assertEqual(const_bytes(7612, 848), 9272)
        self.assertEqual(const_bytes(13788, 848), 15448)
        self.assertEqual(const_bytes(19900, 848), 21560)

    def test_empty_and_partial_identity(self):
        p = BankProject(name='', filename='', fxid='typing')
        u = bank_usage(p)
        self.assertEqual(u['active_slots'], 0)
        self.assertTrue(u['template_fits'])
        p.slots = [Slot('A', self.model())]
        self.assertEqual(bank_usage(p)['active_slots'], 1)
        self.assertEqual(p.name, '')

    def test_dedup_and_template_limits(self):
        p = BankProject(slots=[Slot(str(i), self.model()) for i in range(4)])
        u = bank_usage(p)
        self.assertEqual(u['fir_pool_samples'], 64)
        self.assertTrue(u['template_fits'])
        p.slots.append(Slot('EXTRA', self.model()))
        u = bank_usage(p)
        self.assertFalse(u['template_fits'])
        self.assertGreater(u['remaining_bytes'], 0)

    def test_long_and_unique_banks(self):
        p = BankProject(slots=[Slot(str(i), self.model(2048, i)) for i in range(4)])
        u = bank_usage(p)
        self.assertEqual(u['fir_pool_samples'], 8192)
        self.assertFalse(u['template_fits'])
        self.assertEqual(u['const_bytes'], 21080)
        self.assertEqual(pack_bank(p)[1]['estimated_const_bytes'], u['const_bytes'])

    def test_bad_artwork(self):
        with self.assertRaises(FileNotFoundError):bank_usage(BankProject(image='missing.png'))
