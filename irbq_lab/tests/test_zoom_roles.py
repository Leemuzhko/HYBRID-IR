import struct
import unittest
import zlib
from dataclasses import replace

import numpy as np

from irbq.dsp import Model, Biquad, preset_sections, sos_response, sos_array
from irbq.zoom_bank import BankProject, Slot
from irbq.zoom_rbj_bank import pack, validate, controls, bq_count, control_table, legacy_candidates, assign_roles, rbj_parameters, rbj_coefficients, pres_coefficients, GAIN_LUT


class TestZoomRoles(unittest.TestCase):
    def model(self):
        m=Model(44100,np.r_[.5,np.zeros(127)],preset_sections(8))
        b=next(b for b in m.sections if b.control_role=='reso')
        b.f=137.;b.q=1.3;b.gain=-6.
        return m

    def test_trainer_count_reuses_resonance_and_adds_common_presence(self):
        model = Model(44100, np.r_[.5, np.zeros(127)], preset_sections(8))
        bank, report = pack(BankProject(slots=[Slot('TEST', model)]))
        header = struct.unpack_from('<16I', bank)
        count = struct.unpack_from('<B', bank, header[7] + 48 + 2)[0]
        self.assertEqual(count, 9, 'Reuse trained RESO, retain free Presence, add common PRES')
        self.assertFalse(model.sections[-1].locked)
        self.assertEqual(model.sections[-1].control_role,'')

    def test_presence_is_actually_trainable(self):
        from irbq.trainer import Engine, TrainConfig
        model = self.model()
        engine = Engine(model.fir, model, TrainConfig(mode='bq'))
        index = len(model.sections) - 1
        self.assertEqual({key for i, key, _ in engine.variables if i == index},
                         {'f', 'q', 'gain'})
        self.assertEqual(engine.model.sections[1].control_role, 'reso')

    def test_tagged_count_boundary(self):
        from irbq.zoom_bank import validate_model
        model = self.model()
        model.sections += [Biquad() for _ in range(31 - len(model.sections))]
        self.assertEqual(bq_count(model), 32)
        validate_model(model)
        _, receipt = pack(BankProject(slots=[Slot('MAX', model)]))
        self.assertEqual(receipt['max_bq'], 32)
        model.sections.append(Biquad())
        with self.assertRaises(ValueError):
            validate_model(model)

    def test_neutral_curve_and_endpoints_preserve_learned_parameters(self):
        m=self.model();b=controls(m)[0]
        table=control_table(b)
        np.testing.assert_array_equal(table[30],b.coefficients(44100)[[0,1,2,4,5]].astype('f4'))
        for i,delta in ((0,-15),(60,15)):
            np.testing.assert_array_equal(table[i],replace(b,gain=b.gain+delta).coefficients(44100)[[0,1,2,4,5]].astype('f4'))
        bank,_=pack(BankProject(slots=[Slot('TRAIN',m)]))
        h=struct.unpack_from('<16I',bank)
        n,q,flags,fi,qi=struct.unpack_from('<HBBHH',bank,h[7]+48)
        stored=np.frombuffer(bank,dtype='<f4',count=q*5,offset=h[10]+qi*20).reshape(q,5)
        sos=np.insert(stored,3,1,axis=1)
        f=np.geomspace(20,20000,400)
        np.testing.assert_allclose(sos_response(sos,f,44100),sos_response(sos_array(m.sections,44100,True),f,44100),rtol=1e-10,atol=1e-10)

    def test_legacy_is_never_silently_inferred(self):
        m=self.model()
        for b in m.sections:b.control_role=''
        before=m.to_dict()
        self.assertEqual(bq_count(m),10)
        migrated=assign_roles(m,legacy_candidates(m))
        self.assertEqual(bq_count(migrated),9)
        self.assertEqual(m.to_dict(),before)
        np.testing.assert_array_equal(sos_array(m.sections,44100),sos_array(migrated.sections,44100))
        self.assertEqual(Model.from_dict(migrated.to_dict()).to_dict(),migrated.to_dict())
        m.sections[legacy_candidates(m)['reso']].name='Other'
        self.assertEqual(legacy_candidates(m),{})

    def test_invalid_roles_fail_closed(self):
        for mutate in (lambda m:setattr(m.sections[1],'control_role','x'),
                       lambda m:setattr(m.sections[2],'control_role','reso'),
                       lambda m:setattr(m.sections[1],'kind','LowShelf'),
                       lambda m:setattr(m.sections[1],'enabled',False),
                       lambda m:setattr(m.sections[1],'raw',[1,0,0,1,0,0])):
            m=self.model();mutate(m)
            with self.assertRaises(ValueError):controls(m)

    def test_distinct_curves_need_no_extra_tables(self):
        a=self.model();b=a.clone()
        p=BankProject(slots=[Slot('A',a),Slot('B',b)])
        bank,r=pack(p)
        self.assertEqual(r['control_table_bytes'],0)
        b.sections[1].f+=20.
        bank,r2=pack(p)
        self.assertEqual(r2['control_table_bytes'],0)
        self.assertEqual(r2['gain_lut_bytes'],244)
        h=struct.unpack_from('<16I',bank)
        self.assertNotEqual(bank[h[7]+48+16:h[7]+48+28],bank[h[7]+96+16:h[7]+96+28])

    def test_corrupt_v4_parameters_and_flags(self):
        bank,_=pack(BankProject(slots=[Slot('A',self.model())]))
        h=struct.unpack_from('<16I',bank)
        for off,fmt,value in ((0,'I',0),(4,'I',2),(52,'I',h[13]+4),
                              (h[7]+51,'B',255),(h[7]+48+20,'f',-1.),(h[12],'f',float('nan'))):
            data=bytearray(bank);struct.pack_into('<'+fmt,data,off,value)
            struct.pack_into('<I',data,12,zlib.crc32(data[64:]))
            with self.assertRaises(ValueError):validate(data)
        data=bytearray(bank);data[-1]^=1
        with self.assertRaises(ValueError):validate(data)

    def test_interpolated_denominators_are_stable_in_float32(self):
        from irbq.zoom_variable_bank import stable_denominator
        table=control_table(controls(self.model())[0])
        for t in np.linspace(0,1,101,dtype='f4'):
            rows=table[:-1]+t*(table[1:]-table[:-1])
            self.assertTrue(all(stable_denominator(float(a1),float(a2)) for a1,a2 in rows[:,3:]))

    def test_legacy_encoder_rejects_role_metadata(self):
        from irbq.zoom_bank import pack_bank
        with self.assertRaisesRegex(ValueError,'role-aware'):
            pack_bank(BankProject(slots=[Slot('A',self.model())]))

    def test_rbj_float32_matches_parametric_reference(self):
        for section in (controls(self.model())[0],Biquad(f=90,q=.8,gain=4),Biquad(f=220,q=3,gain=-8)):
            params=rbj_parameters(section);ref=control_table(section)
            actual=np.array([rbj_coefficients(params,np.float32(params[2]*a)) for a in GAIN_LUT])
            identity=np.all(ref==[1,0,0,0,0],axis=1)
            np.testing.assert_allclose(actual[~identity],ref[~identity],rtol=3e-6,atol=5e-7)
            # RBJ may express unity as equal numerator/denominator, rather
            # than the reduced identity returned by Biquad.coefficients.
            for row in actual[identity]:
                response=sos_response(np.insert(row,3,1)[None,:],np.geomspace(20,20000,400),44100)
                np.testing.assert_allclose(response,1,rtol=3e-3,atol=3e-3)
        ref=control_table(Biquad(kind='HighShelf',f=3500,q=.8))
        active=np.arange(61)!=30
        np.testing.assert_allclose(np.array([pres_coefficients(a) for a in GAIN_LUT])[active],ref[active],rtol=3e-6,atol=5e-7)

    def test_off_is_standard_reso_and_pres(self):
        bank,_=pack(BankProject(slots=[Slot('A',self.model())]))
        h=struct.unpack_from('<16I',bank)
        d=struct.unpack_from('<HBBHH10f',bank,h[7])
        self.assertEqual(d[0],0);self.assertEqual(d[1],2)
        np.testing.assert_array_equal(d[7:10],rbj_parameters(Biquad(f=110,q=.7)))

    def test_old_presence_role_upgrades_without_coefficient_change(self):
        b=Biquad(kind='HighShelf',gain=3,locked=True,control_role='pres')
        upgraded=Biquad.from_dict(b.to_dict())
        self.assertFalse(upgraded.locked);self.assertEqual(upgraded.control_role,'')
        np.testing.assert_array_equal(b.coefficients(44100),upgraded.coefficients(44100))

    def test_model_roundtrip_and_odd_max_bq(self):
        m=self.model();self.assertEqual(Model.from_dict(m.to_dict()).to_dict(),m.to_dict())
        _,r=pack(BankProject(slots=[Slot('A',m)]))
        self.assertEqual(r['max_bq'],9)


if __name__ == '__main__':
    unittest.main()
