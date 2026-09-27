import struct
import unittest
import zlib

import numpy as np
from irbq.dsp import Model
from irbq.zoom_bank import BankProject, Slot, pack_bank
from irbq.zoom_variable_bank import HEADER, from_legacy, validate, pack, stable_denominator
from irbq.zoom_variable_repack import layout, repack


class TestVariableBank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = BankProject(slots=[Slot('TEST', Model(44100, np.r_[.5, np.zeros(63)], []))])
        cls.legacy = pack_bank(cls.project, binary=True)[0]
        cls.bank = from_legacy(cls.legacy)

    def test_exact_coefficient_preservation(self):
        self.assertEqual(self.bank[64:], self.legacy[32:])
        self.assertEqual(len(self.bank), len(self.legacy)+32)
        self.assertEqual(validate(self.bank)['max_fir'], 64)

    def test_report_does_not_reuse_old_layout_estimates(self):
        bank, report = pack(self.project)
        self.assertEqual(bank, self.bank)
        self.assertEqual(report['bank_bytes'], len(bank))
        self.assertNotIn('estimated_state_bytes', report)
        self.assertNotIn('estimated_const_bytes', report)

    def test_header_and_region_corruptions(self):
        for offset, value in ((0,0),(4,1),(8,0),(16,10),(20,8192),(24,33),
                              (28,68),(32,64),(36,0xfffffffc),(56,65535)):
            with self.subTest(offset=offset):
                raw = bytearray(self.bank)
                struct.pack_into('<I', raw, offset, value)
                with self.assertRaises(ValueError): validate(raw)

    def test_body_corruption_with_valid_crc(self):
        h = HEADER.unpack_from(self.bank)
        for offset, fmt, value in ((64+48,'H',8192), (64+50,'B',33), (64+51,'B',1),
                                   (64+52,'H',65534), (64+54,'H',65535),
                                   (64+56,'I',0x7fc00000), (h[10],'I',0x7f800000),
                                   (h[8],'B',0)):
            with self.subTest(offset=offset):
                raw = bytearray(self.bank)
                struct.pack_into('<'+fmt, raw, offset, value)
                struct.pack_into('<I', raw, 12, zlib.crc32(raw[64:]))
                with self.assertRaises(ValueError): validate(raw)

    def test_crc_and_length(self):
        raw = bytearray(self.bank); raw[-1] ^= 1
        for data in (raw, self.bank[:-1], self.bank+b'\0', b'', b'\0'*32769):
            with self.assertRaises(ValueError): validate(data)

    def test_finite_unstable_denominators_with_valid_crc(self):
        h = HEADER.unpack_from(self.bank)
        for start in (h[10], h[12], h[13]):
            for a1, a2 in ((0,2), (3,0), (-3,0), (0,-1), (0,1), (1,0)):
                raw = bytearray(self.bank)
                struct.pack_into('<2f', raw, start+12, a1, a2)
                struct.pack_into('<I', raw, 12, zlib.crc32(raw[64:]))
                with self.assertRaisesRegex(ValueError, 'denominator'): validate(raw)
        self.assertTrue(stable_denominator(-1.8, .9))
        self.assertTrue(stable_denominator(0, 0))

    def test_legacy_abi_is_not_guessed(self):
        for data in (b'', self.legacy[:-1], self.legacy+b'\0', b'ABCD'+self.legacy[4:]):
            with self.assertRaises(ValueError): from_legacy(data)

    def test_slot_cap_and_exact_deduplication(self):
        project = BankProject(slots=[Slot('C'+str(i), self.project.slots[0].model) for i in range(8)])
        bank, report = pack(project)
        self.assertEqual(report['entry_count'], 9)
        self.assertEqual(report['fir_pool_samples'], 64)
        self.assertEqual(len(bank)-len(self.bank), 7*56)
        project.slots.append(Slot('MORE', self.project.slots[0].model))
        with self.assertRaises(ValueError): pack(project)

    def test_repack_rejects_untrusted_template(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            repack(b'not a ZDL', self.bank, expected_sha256='0'*64)
        for data in (b'', b'\0'*128):
            with self.assertRaises(ValueError): layout(data)


if __name__ == '__main__': unittest.main()
