import io
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from numpy.testing import assert_allclose, assert_array_equal
from scipy import signal
from irbq.dsp import *
from irbq.trainer import *
from irbq.project import *
from irbq.audio import render_ab

class TestDSP(unittest.TestCase):
    def test_mpt_magnitude(self):
        rng=np.random.default_rng(2)
        x=np.r_[np.zeros(17),rng.normal(size=64)*np.exp(-np.arange(64)/7)]
        h=minimum_phase_ir(x,65536)
        assert_allclose(abs(np.fft.rfft(h)),abs(np.fft.rfft(x,65536)),rtol=1e-9,atol=1e-10)

    def test_bq_identity(self):
        for kind in ['Peak','LowShelf','HighShelf']:
            b=Biquad(kind,f=120,q=.7,gain=0)
            assert_array_equal(b.coefficients(44100),IDENTITY)

    def test_bq_inverse(self):
        f=np.geomspace(1,22000,2048)
        a=Biquad('Peak',f=750,q=3,gain=11)
        b=Biquad('Peak',f=750,q=3,gain=-11)
        H=sos_response(sos_array([a,b],44100),f,44100)
        assert_allclose(H,1,atol=1e-11)

    def test_allpass(self):
        b=Biquad('AllPass',f=780,q=2)
        H=sos_response([b.coefficients(44100)],frequency_grid(44100),44100)
        assert_allclose(abs(H),1,atol=1e-12)

    def test_all_kinds_stable(self):
        for kind in KINDS[:-1]:
            b=Biquad(kind,f=110,q=.7,gain=13)
            self.assertLess(sos_stability([b.coefficients(44100)]),1.)
            self.assertLess(sos_stability([b.coefficients(44100).astype(np.float32)]),1.)

    def test_bad_sos(self):
        with self.assertRaises(ValueError):Biquad('SOS',raw=[1,0,0,1,0,1.1]).coefficients(44100)

    def test_trim(self):
        x=np.r_[np.zeros(100),1.,np.zeros(100)]
        t,b,log=prepare(x,44100,PrepConfig(minimum_phase=False,preroll_ms=0,trim_end=True,postroll_ms=0))
        assert_array_equal(t,[1.])

    def test_silence_rejected(self):
        with self.assertRaises(ValueError):prepare(np.zeros(100),44100,PrepConfig())

    def test_resample_response(self):
        x=np.zeros(1000);x[100]=1
        y,guard=resample_ir(x,48000,44100,True)
        self.assertAlmostEqual(np.sum(y),1,places=4)
        self.assertAlmostEqual(np.argmax(abs(y)),100*44100/48000+guard,delta=1)

    def test_peak_normalization(self):
        cfg=PrepConfig(fs=48000,trim_start=False,minimum_phase=False,normalization='peak',level_db=-6)
        t,b,_=prepare([.2,1,.2],48000,cfg)
        self.assertAlmostEqual(np.max(abs(t)),10**(-6/20))

    def test_render_frequency(self):
        m=Model(44100,np.array([.3,.5,-.1]),[Biquad('Peak',f=200,q=1,gain=7)])
        impulse=m.render(length=20000)
        f=frequency_grid(m.fs,2000)
        assert_allclose(fir_response(impulse,f,m.fs),m.response(f),atol=2e-10)

    def test_q15(self):
        h=np.array([2.3,-1.7,.4,.02]);q,g=quantize_fir(h)
        self.assertLess(np.max(abs(q)),32767)
        assert_allclose(h,q/32768*g,atol=g/65536)

    def test_locked_sos_import(self):
        d={'rate':44100,'fir_q15':[16384,0], 'fir_gain':1.2,'sos':[IDENTITY.tolist()]}
        m=model_from_runtime(d)
        assert_allclose(m.fir,[.6,0]);assert_array_equal(sos_array(m.sections,44100),[IDENTITY])

    def test_phase_not_detrended_in_main_metric(self):
        f=frequency_grid(44100,4000);T=np.ones(len(f),complex);H=np.exp(-2j*np.pi*f/44100*3)
        r=response_metrics(T,H,f,44100)
        self.assertGreater(r[0]['phase_rms_deg'],1.)
        d=phase_diagnostics(T,H,f,44100)
        self.assertAlmostEqual(d['delay_samples'],3.,places=10)
        self.assertLess(d['ripple_deg'],1e-10)

    def test_project_and_export(self):
        s=Session(source=np.array([0,1,.1]),source_fs=44100,config=PrepConfig(minimum_phase=False))
        s.preprocess();s.model=Model(44100,np.array([.8,.2]),[Biquad('Peak',f=200,q=1,gain=3)],'Demo')
        s.snapshots=[s.model.clone()]
        with tempfile.TemporaryDirectory() as p:
            project=Path(p)/'demo.irbq';s.save(project);s2=Session.load(project)
            assert_array_equal(s.model.fir,s2.model.fir)
            reports=export_model(Path(p)/'export',s2)
            imported=import_models(Path(p)/'export/model.json')[0]
            f=frequency_grid(44100,2000)
            assert_allclose(imported.response(f),s.model.response(f),atol=1e-12)
            self.assertTrue((Path(p)/'export/model_data.h').exists())
            self.assertLess(reports['max_pole_radius'],1.)

    def test_export_fir_bypass_flag(self):
        s=Session(source=np.array([0.,1.,.1]),source_fs=44100,config=PrepConfig(minimum_phase=False))
        s.preprocess();s.model=Model(44100,np.array([.7,.2]),[Biquad('Peak',f=900,q=1,gain=2)],'Bypass export',fir_enabled=False)
        with tempfile.TemporaryDirectory() as d:
            export_model(Path(d),s)
            data=json.loads((Path(d)/'model.json').read_text())
            self.assertFalse(data['model']['fir_enabled'])
            self.assertFalse(data['report']['fir_enabled'])
            header=(Path(d)/'model_data.h').read_text()
            self.assertIn('#define IRBQ_FIR_ENABLED 0',header)

    def test_gj64cmp_exact_import(self):
        path=Path(__file__).resolve().parents[1]/'examples/GJ64CMP_model_8.json'
        if not path.exists():self.skipTest('Example not bundled')
        data=json.loads(path.read_text())
        m=import_models(path)[0]
        f=frequency_grid(m.fs,1500)
        h=np.asarray(data['fir_q15'])/32768*data['fir_gain']
        ref=signal.freqz(h,worN=f,fs=m.fs)[1]*signal.sosfreqz(data['sos'],worN=f,fs=m.fs)[1]
        assert_allclose(m.response(f),ref,atol=1e-11)


    def test_fir_bypass_response_and_project_roundtrip(self):
        m=Model(44100,np.array([.2,.3,.1]),[Biquad('Peak',f=900,q=1.2,gain=3)],'Bypass',fir_enabled=False)
        f=frequency_grid(44100,1200)
        expected=sos_response(sos_array(m.sections,44100),f,44100)
        assert_allclose(m.response(f),expected,atol=1e-12)
        s=Session(source=np.array([0.,1.,.1]),source_fs=44100,config=PrepConfig(minimum_phase=False))
        s.preprocess();s.model=m
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bypass.irbq';s.save(path);loaded=Session.load(path)
            self.assertFalse(loaded.model.fir_enabled)
            assert_array_equal(loaded.model.fir,m.fir)

    def test_audio_bypass_ignores_stored_fir(self):
        m=Model(22050,np.array([.25,.25]),[],fir_enabled=False)
        data,fs,report=render_ab(np.array([1.]),m)
        assert_allclose(data['D'],0,atol=1e-12)

    def test_audio_null(self):
        m=Model(22050,np.array([1.]),[])
        data,fs,report=render_ab(np.array([1.]),m)
        assert_allclose(data['D'],0,atol=1e-12)
        self.assertLessEqual(max(abs(data['A'].ravel())),.500001)


    def test_overall_gain_response_render_and_roundtrip(self):
        m=Model(44100,np.array([1.,.2]),[Biquad('Peak',f=900,q=1.1,gain=2)],'Gain',output_gain_db=-7.25)
        f=frequency_grid(44100,700)
        no_gain=Model(44100,m.fir.copy(),[Biquad.from_dict(b.to_dict()) for b in m.sections])
        assert_allclose(m.response(f),no_gain.response(f)*10**(-7.25/20),atol=1e-12)
        assert_allclose(fir_response(m.render(20000),f,m.fs),m.response(f),atol=2e-10)
        s=Session(source=np.array([1.,.1]),source_fs=44100,config=PrepConfig(minimum_phase=False,trim_start=False))
        s.preprocess();s.model=m
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'gain.irbq';s.save(path);loaded=Session.load(path)
            self.assertAlmostEqual(loaded.model.output_gain_db,-7.25)
            export_model(Path(d)/'export',loaded)
            data=json.loads((Path(d)/'export/model.json').read_text())
            self.assertAlmostEqual(data['model']['output_gain_db'],-7.25)
            self.assertTrue((Path(d)/'export/overall_gain.txt').exists())

class TestTrainer(unittest.TestCase):
    def setUp(self):
        self.target=signal.sosfilt(sos_array([Biquad('Peak',f=800,q=1.4,gain=4)],44100),np.r_[.6,np.zeros(2047)])
        self.model=Model(44100,np.r_[.5,np.zeros(31)],[Biquad('Peak',f=700,q=1,gain=2,fmin=300,fmax=3000)])

    def test_gradient(self):
        e=Engine(self.target,self.model,TrainConfig(initialize=False))
        v,g=e.evaluate(e.x0)
        for i in range(len(g)):
            step=1e-5;xp=e.x0.copy();xm=xp.copy();xp[i]+=step;xm[i]-=step
            approx=(e.evaluate(xp,False)[0]-e.evaluate(xm,False)[0])/(2*step)
            assert_allclose(g[i],approx,rtol=.002,atol=1e-6)

    def test_solver_matches_qr(self):
        e=Engine(self.target,self.model,TrainConfig(initialize=False))
        _,_,H=e.response_sections(e.x0)
        h=e.solve(H)
        B=e.E*(H*e.s)[:,None];y=e.T*e.s
        A=np.vstack((B.real,B.imag,np.sqrt(e.lam)*np.eye(e.n)))
        rhs=np.r_[y.real,y.imag,np.zeros(e.n)]
        hqr=np.linalg.lstsq(A,rhs,rcond=None)[0]
        assert_allclose(h,hqr,atol=1e-9)

    def test_training_nonregression(self):
        cfg=TrainConfig(mode='joint',initialize=False,iterations=15)
        e=Engine(self.target,self.model,cfg);initial=e.evaluate(e.x0,False)[0]
        m=train(self.target,self.model,cfg)
        self.assertLessEqual(m.training['objective'],initial+1e-12)

    def test_lock_and_fir_mode(self):
        self.model.sections[0].locked=True
        m=train(self.target,self.model,TrainConfig(mode='fir'))
        self.assertEqual(m.sections[0].to_dict(),self.model.sections[0].to_dict())

    def test_fir_only_unlocked_exact_sos(self):
        b=self.model.sections[0]
        b.raw=b.coefficients(44100).astype(np.float32).astype(float).tolist()
        before=b.to_dict()
        m=train(self.target,self.model,TrainConfig(mode='fir'))
        self.assertEqual(m.sections[0].to_dict(),before)

    def test_bq_only_keeps_fir(self):
        m=train(self.target,self.model,TrainConfig(mode='bq',iterations=4,initialize=False))
        assert_array_equal(m.fir,self.model.fir)


    def test_bq_only_with_fir_bypass_keeps_stored_fir(self):
        self.model.fir_enabled=False
        original=self.model.fir.copy()
        m=train(self.target,self.model,TrainConfig(mode='bq',iterations=4,initialize=False))
        self.assertFalse(m.fir_enabled)
        assert_array_equal(m.fir,original)
        f=frequency_grid(44100,600)
        expected=(10**(m.output_gain_db/20))*sos_response(sos_array(m.sections,44100),f,44100)
        assert_allclose(m.response(f),expected,atol=1e-12)

    def test_fir_refit_after_reenable(self):
        self.model.fir_enabled=True
        m=train(self.target,self.model,TrainConfig(mode='fir',initialize=False))
        self.assertTrue(m.fir_enabled)
        self.assertEqual(len(m.fir),len(self.model.fir))

    def test_bq_magnitude_auto_fits_gain_and_ignores_phase(self):
        target_gain_db=-11.0
        target_sections=[Biquad('Peak',f=850,q=1.3,gain=5.5)]
        impulse=signal.sosfilt(sos_array(target_sections,44100),np.r_[10**(target_gain_db/20),np.zeros(2047)])
        # Add pure delay: same magnitude, very different phase.
        delayed=np.r_[np.zeros(37),impulse[:-37]]
        m=Model(44100,np.r_[1.,np.zeros(31)],[Biquad('Peak',f=700,q=1,gain=0,fmin=300,fmax=3000)],fir_enabled=False)
        cfg=TrainConfig(mode='bq',objective='auto',fit_gain=True,iterations=35,initialize=True,magnitude_delta_db=6)
        r=train(delayed,m,cfg)
        self.assertEqual(r.training['objective_kind'],'magnitude')
        self.assertAlmostEqual(r.output_gain_db,target_gain_db,delta=1.5)
        f=frequency_grid(44100,1000);T=fir_response(delayed,f,44100)
        row=next(x for x in response_metrics(T,r.response(f),f,44100) if x['band']=='guitar')
        self.assertLess(row['mag_rms_db'],1.5)

    def test_complex_mode_preserves_existing_gain_and_old_objective(self):
        self.model.output_gain_db=-3.0
        cfg=TrainConfig(mode='joint',objective='complex',initialize=False,iterations=3)
        e=Engine(self.target,self.model,cfg);self.assertEqual(e.objective_kind,'complex')
        r=train(self.target,self.model,cfg)
        self.assertAlmostEqual(r.output_gain_db,-3.0)
        self.assertEqual(r.training['objective_kind'],'complex')

    def test_cancel(self):
        with self.assertRaises(Cancelled):train(self.target,self.model,TrainConfig(),cancel=lambda:True)

    def test_large_fft_solver(self):
        n=2048;h=np.zeros(n);h[0]=1;h[17]=.2
        m=Model(44100,np.zeros(n),[])
        r=train(h,m,TrainConfig(mode='fir',ridge=1e-9))
        f=frequency_grid(44100,800)
        assert_allclose(r.response(f),fir_response(h,f,44100),atol=.006)

if __name__=='__main__':unittest.main(verbosity=2)
