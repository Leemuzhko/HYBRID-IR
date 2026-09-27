"""Actual HVB4 C core: coefficients, 9-BQ state, routing and serial fades.

Native host execution only. Does not establish C674 timing or pedal acceptance.
"""
import ctypes as C
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

import numpy as np
from scipy import signal
from irbq.dsp import Model,Biquad,preset_sections,sos_array
from irbq.zoom_bank import BankProject,Slot
from irbq.zoom_rbj_bank import pack,validate,control_table

ROOT=Path(__file__).resolve().parents[2]
FP=C.POINTER(C.c_float)


class TestRbjRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != 'nt' or importlib.util.find_spec('ziglang') is None:
            raise unittest.SkipTest('Windows native test needs optional development dependency ziglang')
        cls.tmp=tempfile.TemporaryDirectory(prefix='hybrid-rbj-')
        folder=Path(cls.tmp.name)
        source=folder/'source'
        shutil.copytree(ROOT/'hybridir_sdk/src/custom/hybridir_roles',source)
        sys.path.insert(0,str(ROOT/'scripts'))
        from build_hvb4_rbj_template import bank_header
        bank,_=pack(BankProject(slots=[Slot('UNIT',Model(44100,np.r_[.5,np.zeros(31)],[]))]))
        (source/'generated/bank_u1.h').write_text(bank_header(bank),encoding='utf-8')
        (source/'host.c').write_text('''#define GJ_HOST_BANK
#include "effect.c"
__declspec(dllexport) void bank_set(void*p,unsigned n,unsigned inverse){gj_bank=(const uint32_t*)p;gj_bank_meta[0]=0x344d4248u;gj_bank_meta[1]=n;gj_bank_meta[2]=inverse;}
__declspec(dllexport) unsigned need(void){return gj_state_required();}
__declspec(dllexport) int valid(void){return gj_v2_valid();}
__declspec(dllexport) void coeff(unsigned slot,float raw,float*r,float*p){gj_reso_coeff(gj_eq_position(raw),&GJ_V2_DESC[slot],r);gj_pres_coeff(gj_eq_position(raw),p);}
__declspec(dllexport) void run(void*p,unsigned n,float*x,const float*params){GjState*s=gj_bind_state(p,n);if(s)gj_process_params(s,x,params);}
__declspec(dllexport) unsigned phase(void*p){return ((GjState*)p)->switch_phase;}
__declspec(dllexport) unsigned selection(void*p){return ((GjState*)p)->selected_l;}
''',encoding='utf-8')
        dll=folder/'rbj.dll'
        env={**os.environ,'ZIG_GLOBAL_CACHE_DIR':str(ROOT/'.test-cache/zig-global'),
             'ZIG_LOCAL_CACHE_DIR':str(folder/'zig-local')}
        subprocess.run([sys.executable,'-m','ziglang','cc','-O2','-std=c99','-ffp-contract=off',
                        '-fno-fast-math','-shared','-I',str(ROOT/'hybridir_sdk/sdk/include'),
                        str(source/'host.c'),'-o',str(dll)],env=env,check=True)
        cls.lib=C.CDLL(str(dll))
        cls.lib.bank_set.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
        cls.lib.need.restype=C.c_uint
        cls.lib.coeff.argtypes=[C.c_uint,C.c_float,FP,FP]
        cls.lib.run.argtypes=[C.c_void_p,C.c_uint,FP,FP]
        cls.lib.phase.argtypes=[C.c_void_p];cls.lib.selection.argtypes=[C.c_void_p]

    @classmethod
    def tearDownClass(cls):
        import _ctypes
        _ctypes.FreeLibrary(cls.lib._handle);del cls.lib;cls.tmp.cleanup()

    def bind(self,bank,size=None,shift=0):
        self.storage=C.create_string_buffer(bytes(bank)+b'\0'*16)
        count=struct.unpack_from('<I',bank,16)[0] if len(bank)>=64 else 2
        inverse=struct.unpack('<I',struct.pack('<f',1/max(1,count-1)))[0]
        self.lib.bank_set(C.addressof(self.storage)+shift,len(bank) if size is None else size,inverse)

    def arena(self):
        n=self.lib.need();a=C.create_string_buffer(n+32)
        C.memset(C.addressof(a),0xa5,16);C.memset(C.addressof(a)+16+n,0xa5,16)
        return a,n,C.addressof(a)+16

    def params(self,mode=0,left=1,right=1):
        p=np.zeros(14,dtype='f4');p[0]=1;p[5]=p[7]=1
        p[6]=mode*.01;p[9]=left*.01;p[12]=right*.01
        p[8]=p[10]=p[11]=p[13]=.3
        return p

    def process(self,ptr,n,p,x=None):
        x=np.full(16,.02,dtype='f4') if x is None else x.copy().astype('f4')
        self.lib.run(ptr,n,x.ctypes.data_as(FP),p.ctypes.data_as(FP));return x

    def test_all_positions_and_exact_neutral(self):
        sections=[Biquad(f=f,q=q,gain=g,control_role='reso')
                  for f,q,g in ((90,.8,-5),(137,1.3,-6),(180,2,4),(220,3,-8))]
        bank,_=pack(BankProject(slots=[Slot('C'+str(i),Model(44100,np.r_[.5,np.zeros(31)],[b])) for i,b in enumerate(sections)]))
        self.bind(bank);self.assertEqual(self.lib.valid(),1)
        for slot,b in enumerate([Biquad(f=110,q=.7)]+sections):
            ref=control_table(b)
            pref=control_table(Biquad(kind='HighShelf',f=3500,q=.8))
            for ui in range(61):
                r=np.zeros(5,dtype='f4');p=r.copy()
                self.lib.coeff(slot,ui/100,r.ctypes.data_as(FP),p.ctypes.data_as(FP))
                if ui==30:
                    np.testing.assert_array_equal(r,ref[30]);np.testing.assert_array_equal(p,pref[30])
                elif np.all(ref[ui]==[1,0,0,0,0]):
                    actual=signal.sosfreqz(np.insert(r,3,1)[None,:],worN=np.geomspace(20,20000,200),fs=44100)[1]
                    np.testing.assert_allclose(actual,1,rtol=.003,atol=.003)
                else:np.testing.assert_allclose(r,ref[ui],rtol=3e-6,atol=5e-7)
                np.testing.assert_allclose(p,pref[ui],rtol=3e-6,atol=5e-7)

    def test_nine_bq_neutral_audio_matches_quantized_model(self):
        m=Model(44100,np.r_[.5,np.zeros(127)],preset_sections(8))
        m.sections[1].gain=-6.;m.sections[-1].gain=2.
        bank,r=pack(BankProject(slots=[Slot('TRAIN',m)]));self.assertEqual(r['max_bq'],9)
        self.bind(bank);a,n,ptr=self.arena();p=self.params()
        for _ in range(40):self.process(ptr,n,p,np.zeros(16))
        x=np.random.default_rng(42).normal(0,.01,(300,16)).astype('f4')
        actual=np.vstack([self.process(ptr,n,p,b) for b in x])
        expected=np.empty_like(x)
        for c in (0,8):
            expected[:,c:c+8]=signal.sosfilt(sos_array(m.sections,44100,True),x[:,c:c+8].flatten()*.5).reshape(-1,8)
        np.testing.assert_allclose(actual,expected,rtol=3e-4,atol=3e-6)
        self.assertEqual(a.raw[:16],a.raw[-16:]);self.assertEqual(a.raw[:16],b'\xa5'*16)

    def test_switch_fades_out_before_changing_selection(self):
        bank,_=pack(BankProject(slots=[Slot('POS',Model(44100,np.r_[.5,np.zeros(31)],[])),
                                           Slot('NEG',Model(44100,np.r_[-.5,np.zeros(31)],[]))]))
        self.bind(bank);a,n,ptr=self.arena();p=self.params()
        for _ in range(40):self.process(ptr,n,p)
        p[9]=p[12]=.02
        fade=np.concatenate([self.process(ptr,n,p)[:8] for _ in range(8)])
        self.assertEqual(self.lib.selection(ptr),1)
        np.testing.assert_allclose(fade,.01*(1-np.arange(1,65)/64),rtol=1e-5,atol=1e-7)
        self.assertEqual(fade[-1],0)
        resumed=np.concatenate([self.process(ptr,n,p)[:8] for _ in range(16)])
        self.assertEqual(self.lib.selection(ptr),2);self.assertEqual(self.lib.phase(ptr),0)
        self.assertTrue(np.all(resumed<0));self.assertLess(abs(resumed[0]),1e-5)
        self.assertAlmostEqual(resumed[-1],-.01,places=7)
        self.assertEqual(a.raw[:16],a.raw[-16:])

    def test_mode_rapid_changes_and_invalid_arena(self):
        bank,_=pack(BankProject(slots=[Slot('POS',Model(44100,np.r_[.5,np.zeros(63)],[]))]))
        self.bind(bank);a,n,ptr=self.arena();p=self.params()
        x=np.r_[np.full(8,.02),np.full(8,-.01)].astype('f4')
        for mode in (0,1,2,3):
            p[6]=mode*.01
            for _ in range(40):out=self.process(ptr,n,p,x)
            expected=np.r_[np.full(8,.01),np.full(8,-.005)] if mode==0 else np.full(16,.0025)
            np.testing.assert_allclose(out,expected,rtol=1e-5,atol=1e-7)
        for i in range(1000):
            p[6]=(i%4)*.01;p[9]=(i%2)*.01;p[12]=((i//2)%2)*.01
            self.assertTrue(np.isfinite(self.process(ptr,n,p,x)).all())
        self.assertEqual(a.raw[:16],a.raw[-16:])
        before=a.raw
        for pointer,length in ((ptr,n-1),(ptr+1,n),(0,n)):
            np.testing.assert_array_equal(self.process(pointer,length,p,x),x)
            self.assertEqual(a.raw,before)

    def test_malformed_banks_fail_closed(self):
        bank,_=pack(BankProject(slots=[Slot('POS',Model(44100,np.r_[.5,np.zeros(31)],[]))]))
        h=struct.unpack_from('<16I',bank)
        for off,fmt,val in ((0,'I',0),(4,'I',3),(20,'I',8192),(52,'I',0),
                            (h[7]+51,'B',1),(h[7]+20,'f',-1.),(h[10]+16,'f',2.),(h[12],'f',0.)):
            raw=bytearray(bank);struct.pack_into('<'+fmt,raw,off,val)
            struct.pack_into('<I',raw,12,zlib.crc32(raw[64:]))
            self.bind(raw);self.assertEqual(self.lib.valid(),0)
            with self.assertRaises(ValueError):validate(raw)
        for length in (0,1,63,len(bank)-1):
            self.bind(bank[:length],size=length);self.assertEqual(self.lib.valid(),0)
        self.bind(bank,shift=1);self.assertEqual(self.lib.valid(),0)


if __name__=='__main__':unittest.main()
